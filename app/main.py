"""FastAPI entrypoint for chat ordering and Agent visualization APIs."""
from datetime import datetime
from typing import Any, Optional

from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import (
    AgentProfile,
    CoffeeKB,
    EvomapConsumer,
    Order,
    SkillOrderLedger,
    User,
    VisualizationEvent,
)
from app.domain_constants import (
    IDENTITY_STATUS_ACTIVE,
    ORDER_SOURCE_SKILL,
    ORDER_SOURCE_WEB_DIALOG,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PAYMENT_FAILED,
    PAYMENT_STATUS_PAYMENT_PENDING,
)
from app.llm import client as llm
from app.memory.chat_history import (
    add_message,
    clear_pending_order,
    get_history,
    get_pending_order,
    set_pending_order,
)
from app.services.chat_service import extract_price, handle_message, match_by_price
from app.rag.keywords import extract_keywords
from app.rag.retrieval import retrieve
from app.services.order_service import (
    InsufficientBalanceError,
    place_orders,
)
from app.services.skill_order_service import (
    SkillOrderError,
    SkillPaymentRequired,
    ensure_consumer,
    process_skill_order,
)
from app.services.visualization_service import (
    VALID_AGENT_ACTIONS,
    VALID_AGENT_ROLES,
    create_visualization_event,
    decode_json,
    encode_json,
    event_to_message,
    generate_agent_token,
    hash_agent_token,
    make_sprite_seed,
    visualization_hub,
)

app = FastAPI(title="智能咖啡馆 AI 店长")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

_PRESENCE_CLIENT_EVENTS = {
    "presence.join": "presence.customer_joined",
    "presence.move": "presence.customer_moved",
    "presence.leave": "presence.customer_left",
}


def _resolve_coffees_from_history(db, history, max_messages=1):
    """【任务三·第3步】从 Redis 历史消息中提取被推荐过的咖啡名。

    对应面试题：用户说"就买你刚才推荐的那杯"→ 需要从对话历史解析出具体咖啡名。

    max_messages=1：只看最近1条assistant消息（默认，避免前面聊过5杯就全选）
    max_messages=3：看最近3条（用户说"这两杯了"时用，跨多轮提取）
    """
    all_coffees = [c.coffee_name for c in db.query(CoffeeKB).all()]
    found = []
    msg_count = 0
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            msg_count += 1
            if msg_count > max_messages:
                break
            for name in all_coffees:
                if name in msg.get("content", "") and name not in found:
                    found.append(name)
    return found


def _lookup_price_from_kb(db, coffee_name):
    """从知识库查价格，查不到返回 0"""
    kb = db.query(CoffeeKB).filter(CoffeeKB.coffee_name == coffee_name).first()
    return float(kb.price) if kb else 0.0


# 待确认订单时，用户确认的触发词。分两组使用：
# - _CONFIRM_STRONG：可安全出现在长句任意位置（如「就买「确认」，从我余额里扣钱吧」），
#   因为这些词（确认/下单/扣钱/从余额…）即便夹在句中也表示“同意下单”；
# - _CONFIRM_WEAK：单字或短词（好/对/行/买…），仅在“纯短句”里按 startswith 兜底，
#   避免它们在长句中被误命中（如“还行吧”不应被“行”误判为确认）。
# 另用否定/修改/疑问词守门，防止把“换一杯”“不要了”“下单流程是怎样的”误判为确认。
_CONFIRM_STRONG = (
    "确认", "下单", "结账", "扣钱", "扣款", "付款", "买单", "从余额", "余额扣",
)

_CONFIRM_WEAK = (
    "好的", "好", "对", "是的", "没错", "可以", "行", "买",
    "就下单", "下单吧", "没错下单", "对了下单",
)

# 否定 / 修改 / 观望 / 疑问信号：出现即视为“不是在确认”（优先级最高）。
# 这样既能放行长句确认，又不会把修改订单或提问误判为确认（曾导致反复要求确认的死循环）。
_CONFIRM_NEGATIVE_WORDS = (
    "不", "别", "换", "改", "取消", "退", "再想想", "太贵", "算了",
    "别的", "另外", "改主意",
    # 疑问类：用户在提问而非确认
    "怎么", "如何", "什么", "是否", "能不能", "可不可以",
)
_CONFIRM_QUESTION_MARKS = ("吗", "？", "?")


def _is_confirming(user_msg):
    """判断用户是否在确认待支付订单。

    既要接住带支付措辞的长句确认（「就买「确认」，从我余额里扣钱吧」），
    又要避免把修改订单（「换一杯」「不要了」「太贵换一个」）或提问
    （「下单流程是怎样的」）误判为确认，否则会陷入“反复要求确认”的死循环。

    判定优先级：
      1) 含否定/修改/疑问词 → 不是确认；
      2) 含强确认词（确认/下单/扣钱/从余额等，长句也算）→ 是确认；
      3) 纯短句以弱确认词开头（“好”/“对”/“行”等）→ 是确认；
      4) 其余（如纯咖啡名“美式咖啡”、闲聊）→ 不是确认，落入下方重新处理。
    """
    msg = user_msg.strip()
    if not msg:
        return False
    # 1) 否定/修改/疑问优先：含这些词一律不按确认处理
    if any(w in msg for w in _CONFIRM_NEGATIVE_WORDS):
        return False
    if any(w in msg for w in _CONFIRM_QUESTION_MARKS):
        return False
    # 2) 强确认词：长句中出现也算确认（“确认”/“下单”/“扣钱”/“从余额”等）
    if any(w in msg for w in _CONFIRM_STRONG):
        return True
    # 3) 弱确认词：仅当消息是纯短句时按 startswith 兜底
    if len(msg) <= 6 and any(msg.startswith(w) for w in _CONFIRM_WEAK):
        return True
    return False


# 查看订单意图触发词：必须同时含「订单」+ 查看/历史类词。
# 「下单/结账/扣钱」等下单词不含「订单」，天然不会误判为下单。
_ORDER_VIEW_HINTS = (
    "看", "查看", "查一下", "查询", "最近", "我的", "列表", "记录", "历史", "情况",
)


def _is_order_view_query(user_msg: str) -> bool:
    """判断用户是否想查看历史订单（与「下单」严格区分）。"""
    msg = user_msg.strip()
    if "订单" not in msg:
        return False
    return any(hint in msg for hint in _ORDER_VIEW_HINTS)


def _format_order_history_reply(db: Session, user_id: int) -> str:
    """返回最近订单的对话式摘要，供 /chat 直接回复，避免落入推荐 RAG。"""
    rows = (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )
    if not rows:
        return "您还没有订单哦~ 想喝点什么？告诉我喜欢的口味，我来帮您推荐。"
    lines = []
    total = 0.0
    for o in rows:
        total += float(o.amount)
        lines.append(
            f"  • {o.coffee_name}  ¥{float(o.amount):.2f}  ·  "
            f"{o.created_at.strftime('%m-%d %H:%M')}  ·  #{o.order_id}"
        )
    return (
        "您最近的订单：\n"
        + "\n".join(lines)
        + f"\n最近 {len(rows)} 单合计 ¥{total:.2f}。\n想再来一杯吗？我可以帮您推荐或下单。"
    )


def _normalize_consumer_url(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="consumer_url must be an absolute http(s) URL")
    return text[:512]


class ChatRequest(BaseModel):
    user_id: int
    message: str
    request_id: Optional[str] = None  # 可选，下单幂等键
    consumer_url: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    order_id: Optional[int] = None


class AgentRegisterRequest(BaseModel):
    tool_name: str
    display_name: str
    role_type: str = "waiter"
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRegisterResponse(BaseModel):
    agent_id: int
    api_token: str
    role_type: str
    sprite_seed: int


class AgentActionRequest(BaseModel):
    action_type: str
    target: Optional[str] = None
    message: Optional[str] = None
    correlation_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentActionResponse(BaseModel):
    ok: bool
    event_id: int


class SkillRegisterRequest(BaseModel):
    tool_name: str = "codex"
    display_name: str = "A2A Consumer"
    evomap_node_id: str
    evomap_did: Optional[str] = None
    role_type: str = "customer"
    capabilities: list[str] = Field(default_factory=lambda: ["a2a_super_order"])
    metadata: dict[str, Any] = Field(default_factory=dict)
    evomap_capability_status: str = "unknown"


class SkillRegisterResponse(BaseModel):
    consumer_id: int
    agent_id: int
    api_token: str
    role_type: str
    sprite_seed: int
    free_orders_remaining: int
    evomap_node_id: str


class SkillOrderRequest(BaseModel):
    consumer_id: int
    agent_id: int
    message: str
    request_id: Optional[str] = None
    auto_confirm: bool = True
    evomap_node_secret: Optional[str] = None
    payment_proof: Optional[dict[str, Any]] = None


class SkillOrderResponse(BaseModel):
    ok: bool
    status: str
    reply: str
    request_id: str
    consumer_id: int
    ledger_id: Optional[int] = None
    order_ids: list[int] = Field(default_factory=list)
    coffee_names: list[str] = Field(default_factory=list)
    amount_credits: Optional[int] = None
    payment_status: Optional[str] = None
    free_orders_remaining: int = 0
    evomap_order_id: Optional[str] = None
    payment_request: Optional[dict[str, Any]] = None
    service_order_request: Optional[dict[str, Any]] = None


def _publish_visualization_event(
    db: Session,
    event_type: str,
    payload: dict[str, Any],
    agent_id: int | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    message = create_visualization_event(
        db,
        event_type=event_type,
        payload=payload,
        agent_id=agent_id,
        correlation_id=correlation_id,
    )
    visualization_hub.broadcast_from_sync(message)
    return message


def _try_publish_visualization_event(
    db: Session,
    event_type: str,
    payload: dict[str, Any],
    agent_id: int | None = None,
    correlation_id: str | None = None,
) -> None:
    try:
        _publish_visualization_event(db, event_type, payload, agent_id, correlation_id)
    except Exception:
        db.rollback()
        visualization_hub.broadcast_from_sync(
            {
                "event_id": None,
                "type": event_type,
                "agent_id": agent_id,
                "payload": payload,
                "correlation_id": correlation_id,
                "created_at": datetime.utcnow().isoformat(),
            }
        )


def _web_restaurant_payload(
    req: ChatRequest,
    *,
    state: str,
    consumer_url: str | None,
    coffees: list[dict[str, Any]] | None = None,
    coffee_names: list[str] | None = None,
    total: float | int | None = None,
    payment_status: str | None = None,
    order_ids: list[int] | None = None,
    message: str | None = None,
    reason: str | None = None,
    stage: str | None = None,
    patience: int | None = None,
    satisfaction: int | None = None,
) -> dict[str, Any]:
    public_coffees = [
        {"name": item["name"], "price": float(item["price"])}
        for item in (coffees or [])
        if item.get("name") is not None
    ]
    names = coffee_names or [item["name"] for item in public_coffees]
    return {
        "version": 1,
        "state": state,
        "source_type": ORDER_SOURCE_WEB_DIALOG,
        "consumer_url": consumer_url,
        "customer": {
            "kind": "web",
            "user_id": req.user_id,
            "display_name": f"Web 用户 {req.user_id}",
        },
        "user_id": req.user_id,
        "coffees": public_coffees,
        "coffee_names": names,
        "total": float(total) if total is not None else None,
        "payment_status": payment_status,
        "order_ids": order_ids or [],
        "message": message,
        "reason": reason,
        "stage": stage,
        "patience": patience,
        "satisfaction": satisfaction,
    }


def _publish_web_restaurant_event(
    db: Session,
    event_type: str,
    *,
    req: ChatRequest,
    consumer_url: str | None,
    state: str,
    coffees: list[dict[str, Any]] | None = None,
    coffee_names: list[str] | None = None,
    total: float | int | None = None,
    payment_status: str | None = None,
    order_ids: list[int] | None = None,
    message: str | None = None,
    reason: str | None = None,
    stage: str | None = None,
    patience: int | None = None,
    satisfaction: int | None = None,
) -> None:
    _try_publish_visualization_event(
        db,
        event_type,
        _web_restaurant_payload(
            req,
            state=state,
            consumer_url=consumer_url,
            coffees=coffees,
            coffee_names=coffee_names,
            total=total,
            payment_status=payment_status,
            order_ids=order_ids,
            message=message,
            reason=reason,
            stage=stage,
            patience=patience,
            satisfaction=satisfaction,
        ),
        correlation_id=req.request_id,
    )


def _publish_web_completion_flow(
    db: Session,
    *,
    req: ChatRequest,
    consumer_url: str | None,
    orders: list[Order],
) -> None:
    coffees = [{"name": order.coffee_name, "price": float(order.amount)} for order in orders]
    coffee_names = [order.coffee_name for order in orders]
    order_ids = [order.order_id for order in orders]
    total = float(sum(order.amount for order in orders))
    common = {
        "req": req,
        "consumer_url": consumer_url,
        "coffees": coffees,
        "coffee_names": coffee_names,
        "total": total,
        "payment_status": PAYMENT_STATUS_PAID,
        "order_ids": order_ids,
    }
    _publish_web_restaurant_event(
        db,
        "restaurant.payment_completed",
        state="payment_completed",
        patience=82,
        satisfaction=88,
        **common,
    )
    for stage, label, patience in (
        ("grinding", "grinding beans", 78),
        ("brewing", "brewing coffee", 72),
        ("plating", "plating order", 68),
    ):
        _publish_web_restaurant_event(
            db,
            "restaurant.preparation_progress",
            state="making",
            stage=stage,
            message=label,
            patience=patience,
            satisfaction=90,
            **common,
        )
    _publish_web_restaurant_event(db, "restaurant.order_ready", state="ready", patience=70, satisfaction=92, **common)
    _publish_web_restaurant_event(db, "restaurant.order_delivered", state="delivered", patience=74, satisfaction=94, **common)
    _publish_web_restaurant_event(
        db,
        "restaurant.customer_reviewed",
        state="reviewed",
        message="顾客评价：出餐顺利",
        patience=76,
        satisfaction=96,
        **common,
    )
    _publish_web_restaurant_event(db, "restaurant.customer_left", state="left", patience=80, satisfaction=96, **common)


def _extract_agent_token(authorization: str | None, x_agent_token: str | None) -> str:
    if x_agent_token:
        return x_agent_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    raise HTTPException(status_code=401, detail="缺少 Agent API token")


def _require_agent(
    db: Session,
    agent_id: int,
    authorization: str | None,
    x_agent_token: str | None,
) -> AgentProfile:
    token = _extract_agent_token(authorization, x_agent_token)
    agent = db.query(AgentProfile).filter(AgentProfile.agent_id == agent_id).first()
    if not agent or agent.status != IDENTITY_STATUS_ACTIVE:
        raise HTTPException(status_code=404, detail="Agent 不存在或已停用")
    if agent.api_token_hash != hash_agent_token(token):
        raise HTTPException(status_code=401, detail="Agent API token 无效")
    return agent


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """Handle chat, recommendation, pending confirmation, and paid order flows."""
    consumer_url = _normalize_consumer_url(req.consumer_url)
    web_source_payload = {
        "source_type": ORDER_SOURCE_WEB_DIALOG,
        "payment_status": PAYMENT_STATUS_PAID,
        "consumer_url": consumer_url,
        "correlation_id": req.request_id,
    }
    _publish_web_restaurant_event(
        db,
        "restaurant.customer_entered",
        req=req,
        consumer_url=consumer_url,
        state="entered",
        message=req.message,
        patience=100,
        satisfaction=80,
    )
    _try_publish_visualization_event(
        db,
        "message.received",
       {"user_id": req.user_id, "message": req.message, **web_source_payload},
       correlation_id=req.request_id,
   )
    # ===== 查看订单意图：直接返回订单列表，避免被当成「求推荐」走 RAG =====
    # 放在 pending 检查之前，这样查看订单不会清掉待确认订单。
    if _is_order_view_query(req.message):
        reply = _format_order_history_reply(db, req.user_id)
        add_message(req.user_id, "user", req.message)
        add_message(req.user_id, "assistant", reply)
        _try_publish_visualization_event(
            db,
            "order.reply",
            {"user_id": req.user_id, "intent": "view_orders", **web_source_payload},
            correlation_id=req.request_id,
        )
        return ChatResponse(reply=reply)

    # ===== 第1步：读 Redis 上下文（短期记忆，最近5轮对话）=====
    history = get_history(req.user_id)

    # ===== 第0步：检查 Redis 是否有待确认订单（两段式下单）=====
    pending = get_pending_order(req.user_id)

    if pending:
        # --- 有待确认订单：判断用户是确认还是修改 ---
        if _is_confirming(req.message):
            # 用户明确回复了确认词（"确认"/"下单"/"好"等）→ 执行扣款
            try:
                items = [(item["name"], req.request_id if i == 0 else None)
                         for i, item in enumerate(pending["coffees"])]
                orders = place_orders(
                    db,
                    req.user_id,
                    items,
                    source_type=ORDER_SOURCE_WEB_DIALOG,
                    payment_status=PAYMENT_STATUS_PAID,
                    consumer_url=consumer_url,
                    correlation_id=req.request_id,
                )
            except (InsufficientBalanceError, ValueError) as e:
                # InsufficientBalanceError：余额不足；
                # ValueError：place_orders 对「用户不存在/参数非法」抛出，
                # 不捕获会变成 HTTP 500，这里统一降级为友好提示。
                clear_pending_order(req.user_id)
                reply = f"下单失败：{e}。请稍后重试或联系店长~"
                add_message(req.user_id, "user", req.message)
                add_message(req.user_id, "assistant", reply)
                _publish_web_restaurant_event(
                    db,
                    "restaurant.payment_failed",
                    req=req,
                    consumer_url=consumer_url,
                    state="failed",
                    coffees=pending.get("coffees", []),
                    total=pending.get("total"),
                    payment_status=PAYMENT_STATUS_PAYMENT_FAILED,
                    reason=str(e),
                    stage="payment",
                    patience=28,
                    satisfaction=35,
                )
                _publish_web_restaurant_event(
                    db,
                    "restaurant.order_failed",
                    req=req,
                    consumer_url=consumer_url,
                    state="failed",
                    coffees=pending.get("coffees", []),
                    total=pending.get("total"),
                    payment_status=PAYMENT_STATUS_PAYMENT_FAILED,
                    reason=str(e),
                    stage=ORDER_SOURCE_WEB_DIALOG,
                    patience=24,
                    satisfaction=30,
                )
                _try_publish_visualization_event(
                    db,
                    "order.failed",
                    {
                        "user_id": req.user_id,
                        "reason": str(e),
                        "stage": "payment",
                        **web_source_payload,
                    },
                    correlation_id=req.request_id,
                )
                return ChatResponse(reply=reply)

            clear_pending_order(req.user_id)
            user = db.query(User).filter(User.user_id == req.user_id).first()
            balance = user.balance if user else "?"
            if len(orders) == 1:
                reply = (
                    f"好嘞！已为您下单「{orders[0].coffee_name}」，扣款 ¥{orders[0].amount}，"
                    f"当前余额 ¥{balance}。祝您品尝愉快~"
                )
            else:
                order_lines = "\n".join(f"  • {o.coffee_name} ¥{o.amount}" for o in orders)
                total = sum(o.amount for o in orders)
                reply = (
                    f"好嘞！已为您下单 {len(orders)} 杯：\n{order_lines}\n"
                    f"合计 ¥{total}，当前余额 ¥{balance}。祝您品尝愉快~"
                )
            add_message(req.user_id, "user", req.message)
            add_message(req.user_id, "assistant", reply)
            _publish_web_completion_flow(
                db,
                req=req,
                consumer_url=consumer_url,
                orders=orders,
            )
            _try_publish_visualization_event(
                db,
                "order.paid",
                {
                    "user_id": req.user_id,
                    "order_ids": [o.order_id for o in orders],
                    "coffee_names": [o.coffee_name for o in orders],
                    "total": float(sum(o.amount for o in orders)),
                    **web_source_payload,
                },
                correlation_id=req.request_id,
            )
            return ChatResponse(reply=reply, order_id=orders[0].order_id)
        else:
            # 不是纯确认词 → 清掉待确认，落入下方正常流程重新处理
            # （覆盖：修改订单"只要28的"、换一杯、重新选、闲聊等所有情况）
            clear_pending_order(req.user_id)

    # ===== 第2步：无待确认订单 → 调 LLM 理解用户意图 =====
    # LLM 返回三分类之一：order（下单）/ recommend（求推荐）/ chat（闲聊）
    intent = llm.parse_intent(history, req.message)
    _try_publish_visualization_event(
        db,
        "order.intent_detected",
        {"user_id": req.user_id, "intent": intent.get("intent", "chat"), **web_source_payload},
        correlation_id=req.request_id,
    )

    # ===== 第3步：LLM 判断为"下单"意图 → 解析具体是哪杯咖啡 =====
    # 四路优先级：价格匹配 > LLM显式名 > RAG关键词 > 历史提取
    if intent.get("intent") == "order":
        coffees = []

        # 第3.1路：价格匹配（"来个28元的"→ 按价格查 MySQL CoffeeKB）
        price = extract_price(req.message)
        if price is not None:
            coffees = [c.coffee_name for c in match_by_price(db, price)]

        # 第3.2路：LLM 显式给出了咖啡名（它能理解"一开始说的""刚才那杯"等引用）
        # 信任 LLM 的引用理解能力，排在历史盲扫之前
        if not coffees:
            coffee = intent.get("coffee_name")
            if coffee:
                # 处理 LLM 可能返回合并名 "柑橘冷萃和美式咖啡"
                valid_names = [c.coffee_name for c in db.query(CoffeeKB).all()]
                parts = [p.strip() for p in coffee.replace("和", ",").replace("、", ",").split(",") if p.strip()]
                matched = [p for p in parts if p in valid_names]
                if matched:
                    coffees = matched

        # 第3.3路：消息含描述性词（"无牛奶"/"果味"）→ RAG 关键词过滤
        if not coffees:
            positive, negative = extract_keywords(req.message)
            if positive or negative:
                coffees = [r.coffee_name for r in retrieve(db, positive, negative)]

        # 第3.4路：以上都没命中 → 从 Redis 历史提取（最弱信号，兜底）
        # 默认只看最近1条消息（1杯）；用户说「两杯/这些/都」时跨轮提取3条
        _MULTI_SIGNALS = ("两杯", "这些", "都", "全部", "三个", "两个", "这几杯", "都来", "全要")
        wants_multi = any(w in req.message for w in _MULTI_SIGNALS)
        if not coffees:
            scan = 3 if wants_multi else 1
            coffees = _resolve_coffees_from_history(db, history, max_messages=scan)

        # 默认只取 1 杯，除非明确说了多杯信号
        if len(coffees) > 1 and not wants_multi:
            coffees = coffees[:1]

        if not coffees:
            reply = "不好意思，我没太确定您想买哪杯，能再说一下咖啡名字吗？"
            add_message(req.user_id, "user", req.message)
            add_message(req.user_id, "assistant", reply)
            _publish_web_restaurant_event(
                db,
                "restaurant.order_failed",
                req=req,
                consumer_url=consumer_url,
                state="failed",
                message=req.message,
                reason="coffee_not_resolved",
                stage="resolve",
                patience=45,
                satisfaction=32,
            )
            _try_publish_visualization_event(
                db,
                "order.failed",
                {
                    "user_id": req.user_id,
                    "reason": "coffee_not_resolved",
                    "stage": "resolve",
                    **web_source_payload,
                },
                correlation_id=req.request_id,
            )
            return ChatResponse(reply=reply)

        # ===== 第4步：两段式下单 —— 先存 Redis 待确认，显示摘要（不直接扣款）=====
        # 把选中的咖啡名+价格存入 Redis，等用户回复"确认"后才执行扣款
        items = []
        for name in coffees:
            p = _lookup_price_from_kb(db, name)
            items.append({"name": name, "price": p})
        total = sum(i["price"] for i in items)
        set_pending_order(req.user_id, {"coffees": items, "total": total})

        lines = "\n".join(f"  • {i['name']}  ¥{i['price']:.2f}" for i in items)
        reply = (
            f"收到！您点的是：\n{lines}\n"
            f"合计 ¥{total:.2f}\n"
            f"确认下单请回复「确认」或「下单」~"
        )
        add_message(req.user_id, "user", req.message)
        add_message(req.user_id, "assistant", reply)
        _publish_web_restaurant_event(
            db,
            "restaurant.order_confirming",
            req=req,
            consumer_url=consumer_url,
            state="confirming",
            coffees=[{"name": i["name"], "price": float(i["price"])} for i in items],
            total=float(total),
            payment_status=PAYMENT_STATUS_PAYMENT_PENDING,
            patience=88,
            satisfaction=84,
        )
        _try_publish_visualization_event(
            db,
            "order.pending_confirmation",
            {
                "user_id": req.user_id,
                "coffees": [{"name": i["name"], "price": float(i["price"])} for i in items],
                "total": float(total),
                **web_source_payload,
            },
            correlation_id=req.request_id,
        )
        return ChatResponse(reply=reply)

    # ===== 非下单意图（recommend/chat）→ 走 RAG 聊天流程 =====
    # handle_message 内部：读Redis → 关键词提取 → LIKE检索 → LLM生成 → 写Redis
    clear_pending_order(req.user_id)
    reply = handle_message(db, req.user_id, req.message)
    _try_publish_visualization_event(
        db,
        "order.reply",
        {"user_id": req.user_id, "intent": intent.get("intent", "chat"), **web_source_payload},
        correlation_id=req.request_id,
    )
    return ChatResponse(reply=reply)


@app.post("/agents/register", response_model=AgentRegisterResponse)
def register_agent(req: AgentRegisterRequest, db: Session = Depends(get_db)):
    role_type = req.role_type.strip().lower()
    if role_type not in VALID_AGENT_ROLES:
        raise HTTPException(status_code=400, detail=f"不支持的角色类型：{req.role_type}")
    token = generate_agent_token()
    agent = AgentProfile(
        tool_name=req.tool_name.strip(),
        display_name=req.display_name.strip(),
        role_type=role_type,
        capabilities_json=encode_json(req.capabilities),
        metadata_json=encode_json(req.metadata),
        api_token_hash=hash_agent_token(token),
        sprite_seed=make_sprite_seed(),
        status=IDENTITY_STATUS_ACTIVE,
        created_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    _publish_visualization_event(
        db,
        "agent.registered",
        {
            "agent_id": agent.agent_id,
            "tool_name": agent.tool_name,
            "display_name": agent.display_name,
            "role_type": agent.role_type,
            "capabilities": req.capabilities,
            "sprite_seed": agent.sprite_seed,
        },
        agent_id=agent.agent_id,
    )
    return AgentRegisterResponse(
        agent_id=agent.agent_id,
        api_token=token,
        role_type=agent.role_type,
        sprite_seed=agent.sprite_seed,
    )


@app.post("/skill/register", response_model=SkillRegisterResponse)
def register_skill_consumer(req: SkillRegisterRequest, db: Session = Depends(get_db)):
    role_type = req.role_type.strip().lower()
    if role_type not in VALID_AGENT_ROLES:
        raise HTTPException(status_code=400, detail=f"不支持的角色类型：{req.role_type}")

    consumer = ensure_consumer(
        db,
        evomap_node_id=req.evomap_node_id,
        evomap_did=req.evomap_did,
        display_name=req.display_name,
    )
    token = generate_agent_token()
    metadata = dict(req.metadata)
    metadata.update(
        {
            "source": "a2a-super-order-skill",
            "consumer_id": consumer.consumer_id,
            "evomap_node_id": consumer.evomap_node_id,
            "evomap_did": consumer.evomap_did,
            "evomap_capability_status": req.evomap_capability_status,
        }
    )
    agent = AgentProfile(
        tool_name=req.tool_name.strip(),
        display_name=req.display_name.strip() or consumer.display_name,
        role_type=role_type,
        capabilities_json=encode_json(req.capabilities),
        metadata_json=encode_json(metadata),
        api_token_hash=hash_agent_token(token),
        sprite_seed=make_sprite_seed(),
        status=IDENTITY_STATUS_ACTIVE,
        created_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    free_orders_remaining = max(settings.skill_free_order_limit - consumer.free_orders_used, 0)
    _publish_visualization_event(
        db,
        "agent.registered",
        {
            "agent_id": agent.agent_id,
            "consumer_id": consumer.consumer_id,
            "tool_name": agent.tool_name,
            "display_name": agent.display_name,
            "role_type": agent.role_type,
            "capabilities": req.capabilities,
            "sprite_seed": agent.sprite_seed,
            "evomap_node_id": consumer.evomap_node_id,
            "free_orders_remaining": free_orders_remaining,
        },
        agent_id=agent.agent_id,
    )
    return SkillRegisterResponse(
        consumer_id=consumer.consumer_id,
        agent_id=agent.agent_id,
        api_token=token,
        role_type=agent.role_type,
        sprite_seed=agent.sprite_seed,
        free_orders_remaining=free_orders_remaining,
        evomap_node_id=consumer.evomap_node_id,
    )


@app.post("/skill/orders", response_model=SkillOrderResponse)
def create_skill_order(
    req: SkillOrderRequest,
    authorization: Optional[str] = Header(None),
    x_agent_token: Optional[str] = Header(None),
    x_evomap_node_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not req.auto_confirm:
        raise HTTPException(status_code=400, detail="Skill 点单当前要求 auto_confirm=true")

    agent = _require_agent(db, req.agent_id, authorization, x_agent_token)
    metadata = decode_json(agent.metadata_json, {})
    if metadata.get("consumer_id") and int(metadata["consumer_id"]) != req.consumer_id:
        raise HTTPException(status_code=403, detail="Agent 与消费者身份不匹配")

    consumer = db.query(EvomapConsumer).filter(EvomapConsumer.consumer_id == req.consumer_id).first()
    if not consumer or consumer.status != IDENTITY_STATUS_ACTIVE:
        raise HTTPException(status_code=404, detail="EvoMap 消费者不存在或已停用")

    try:
        return process_skill_order(
            db,
            consumer=consumer,
            agent=agent,
            message=req.message,
            request_id=req.request_id,
            evomap_node_secret=x_evomap_node_secret or req.evomap_node_secret,
            payment_proof=req.payment_proof,
        )
    except SkillPaymentRequired as exc:
        raise HTTPException(status_code=402, detail=exc.payload) from exc
    except SkillOrderError as exc:
        _try_publish_visualization_event(
            db,
            "order.failed",
            {
                "consumer_id": req.consumer_id,
                "agent_id": req.agent_id,
                "reason": str(exc),
                "code": exc.code,
                "stage": "skill_order",
                "source_type": ORDER_SOURCE_SKILL,
                "payment_status": PAYMENT_STATUS_PAYMENT_FAILED,
            },
            agent_id=req.agent_id,
            correlation_id=req.request_id,
        )
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@app.get("/agents")
def list_agents(db: Session = Depends(get_db)):
    rows = (
        db.query(AgentProfile)
        .filter(AgentProfile.status == IDENTITY_STATUS_ACTIVE)
        .order_by(AgentProfile.created_at.asc())
        .all()
    )
    return [
        {
            "agent_id": a.agent_id,
            "tool_name": a.tool_name,
            "display_name": a.display_name,
            "role_type": a.role_type,
            "capabilities": decode_json(a.capabilities_json, []),
            "metadata": decode_json(a.metadata_json, {}),
            "sprite_seed": a.sprite_seed,
            "status": a.status,
            "last_seen_at": a.last_seen_at.isoformat(),
        }
        for a in rows
    ]


@app.post("/agents/{agent_id}/heartbeat")
def agent_heartbeat(
    agent_id: int,
    authorization: Optional[str] = Header(None),
    x_agent_token: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    agent = _require_agent(db, agent_id, authorization, x_agent_token)
    agent.last_seen_at = datetime.utcnow()
    db.commit()
    event = _publish_visualization_event(
        db,
        "agent.heartbeat",
        {
            "agent_id": agent.agent_id,
            "display_name": agent.display_name,
            "role_type": agent.role_type,
        },
        agent_id=agent.agent_id,
    )
    return {"ok": True, "event_id": event["event_id"]}


@app.post("/agents/{agent_id}/actions", response_model=AgentActionResponse)
def post_agent_action(
    agent_id: int,
    req: AgentActionRequest,
    authorization: Optional[str] = Header(None),
    x_agent_token: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    agent = _require_agent(db, agent_id, authorization, x_agent_token)
    action_type = req.action_type.strip()
    if action_type not in VALID_AGENT_ACTIONS:
        raise HTTPException(status_code=400, detail=f"不支持的动作类型：{req.action_type}")
    agent.last_seen_at = datetime.utcnow()
    db.commit()
    event = _publish_visualization_event(
        db,
        "agent.action",
        {
            "agent_id": agent.agent_id,
            "tool_name": agent.tool_name,
            "display_name": agent.display_name,
            "role_type": agent.role_type,
            "sprite_seed": agent.sprite_seed,
            "action_type": action_type,
            "target": req.target,
            "message": req.message,
            "payload": req.payload,
        },
        agent_id=agent.agent_id,
        correlation_id=req.correlation_id,
    )
    return AgentActionResponse(ok=True, event_id=event["event_id"])


@app.get("/visualization/events")
def list_visualization_events(limit: int = 50, db: Session = Depends(get_db)):
    safe_limit = min(max(limit, 1), 200)
    rows = (
        db.query(VisualizationEvent)
        .order_by(VisualizationEvent.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    return [event_to_message(row) for row in reversed(rows)]


@app.get("/admin/restaurant-state")
def restaurant_state(limit: int = 50, db: Session = Depends(get_db)):
    """Read-only aggregate state for the restaurant visualization screen."""
    safe_limit = min(max(limit, 1), 200)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    today_count, today_amount = (
        db.query(func.count(Order.order_id), func.coalesce(func.sum(Order.amount), 0))
        .filter(Order.created_at >= today_start)
        .one()
    )
    source_rows = (
        db.query(
            Order.source_type,
            func.count(Order.order_id),
            func.coalesce(func.sum(Order.amount), 0),
        )
        .filter(Order.created_at >= today_start)
        .group_by(Order.source_type)
        .all()
    )

    recent_orders = (
        db.query(Order)
        .order_by(Order.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    agent_ids = {row.agent_id for row in recent_orders if row.agent_id}
    consumer_ids = {row.consumer_id for row in recent_orders if row.consumer_id}
    ledger_ids = {row.ledger_id for row in recent_orders if row.ledger_id}

    agents_by_id = {
        row.agent_id: row
        for row in db.query(AgentProfile).filter(AgentProfile.agent_id.in_(agent_ids)).all()
    } if agent_ids else {}
    consumers_by_id = {
        row.consumer_id: row
        for row in db.query(EvomapConsumer).filter(EvomapConsumer.consumer_id.in_(consumer_ids)).all()
    } if consumer_ids else {}
    ledgers_by_id = {
        row.ledger_id: row
        for row in db.query(SkillOrderLedger).filter(SkillOrderLedger.ledger_id.in_(ledger_ids)).all()
    } if ledger_ids else {}

    event_rows = (
        db.query(VisualizationEvent)
        .order_by(VisualizationEvent.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    active_agents = (
        db.query(AgentProfile)
        .filter(AgentProfile.status == IDENTITY_STATUS_ACTIVE)
        .order_by(AgentProfile.last_seen_at.desc())
        .limit(50)
        .all()
    )
    active_consumers = (
        db.query(EvomapConsumer)
        .filter(EvomapConsumer.status == IDENTITY_STATUS_ACTIVE)
        .order_by(EvomapConsumer.last_seen_at.desc())
        .limit(50)
        .all()
    )

    return {
        "summary": {
            "today_order_count": int(today_count or 0),
            "today_amount": float(today_amount or 0),
            "source_stats": [
                {
                    "source_type": source_type or "unknown",
                    "count": int(count or 0),
                    "amount": float(amount or 0),
                }
                for source_type, count, amount in source_rows
            ],
            "active_agent_count": len(active_agents),
            "active_consumer_count": len(active_consumers),
        },
        "recent_orders": [
            {
                "order_id": row.order_id,
                "coffee_name": row.coffee_name,
                "amount": float(row.amount),
                "status": row.status,
                "source_type": row.source_type,
                "payment_status": row.payment_status,
                "consumer_url": row.consumer_url,
                "consumer": _public_consumer(consumers_by_id.get(row.consumer_id)),
                "agent": _public_agent(agents_by_id.get(row.agent_id)),
                "ledger": _public_ledger(ledgers_by_id.get(row.ledger_id)),
                "correlation_id": row.correlation_id,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in recent_orders
        ],
        "recent_events": [event_to_message(row) for row in event_rows],
        "agents": [_public_agent(row) for row in active_agents],
        "consumers": [_public_consumer(row) for row in active_consumers],
    }


def _public_agent(agent: AgentProfile | None) -> dict[str, Any] | None:
    if not agent:
        return None
    return {
        "agent_id": agent.agent_id,
        "tool_name": agent.tool_name,
        "display_name": agent.display_name,
        "role_type": agent.role_type,
        "capabilities": decode_json(agent.capabilities_json, []),
        "metadata": decode_json(agent.metadata_json, {}),
        "sprite_seed": agent.sprite_seed,
        "status": agent.status,
        "last_seen_at": agent.last_seen_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }


def _public_consumer(consumer: EvomapConsumer | None) -> dict[str, Any] | None:
    if not consumer:
        return None
    return {
        "consumer_id": consumer.consumer_id,
        "evomap_node_id": consumer.evomap_node_id,
        "display_name": consumer.display_name,
        "free_orders_used": consumer.free_orders_used,
        "status": consumer.status,
        "last_seen_at": consumer.last_seen_at.isoformat(),
        "updated_at": consumer.updated_at.isoformat(),
    }


def _public_ledger(ledger: SkillOrderLedger | None) -> dict[str, Any] | None:
    if not ledger:
        return None
    return {
        "ledger_id": ledger.ledger_id,
        "request_id": ledger.request_id,
        "amount_credits": ledger.amount_credits,
        "payment_status": ledger.payment_status,
        "free_order_sequence": ledger.free_order_sequence,
        "evomap_order_id": ledger.evomap_order_id,
        "updated_at": ledger.updated_at.isoformat(),
    }


def _presence_coordinate(value: Any, minimum: float, maximum: float) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return int(minimum)
    return int(max(minimum, min(maximum, number)))


def _presence_message_from_client(message: dict[str, Any]) -> dict[str, Any] | None:
    event_type = _PRESENCE_CLIENT_EVENTS.get(str(message.get("type") or ""))
    if not event_type:
        return None
    raw_payload = message.get("payload")
    if not isinstance(raw_payload, dict):
        return None
    visitor_id = str(raw_payload.get("visitor_id") or "").strip()
    if not visitor_id:
        return None
    visitor_id = visitor_id[:80]
    display_name = str(raw_payload.get("display_name") or "").strip()[:40]
    if not display_name:
        display_name = f"Guest {visitor_id[-4:].upper()}"
    payload: dict[str, Any] = {
        "visitor_id": visitor_id,
        "display_name": display_name,
    }
    if event_type != "presence.customer_left":
        payload["x"] = _presence_coordinate(raw_payload.get("x"), 24, 616)
        payload["y"] = _presence_coordinate(raw_payload.get("y"), 82, 326)
    elif "x" in raw_payload and "y" in raw_payload:
        payload["x"] = _presence_coordinate(raw_payload.get("x"), 24, 616)
        payload["y"] = _presence_coordinate(raw_payload.get("y"), 82, 326)
    return {
        "type": event_type,
        "payload": payload,
        "correlation_id": f"presence:{visitor_id}",
        "created_at": datetime.utcnow().isoformat(),
    }


@app.websocket("/ws/visualization")
async def visualization_websocket(websocket: WebSocket):
    await visualization_hub.connect(websocket)
    presence_payload: dict[str, Any] | None = None
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "payload": {},
                        "created_at": datetime.utcnow().isoformat(),
                    }
                )
                continue
            presence_message = _presence_message_from_client(message)
            if presence_message:
                if presence_message["type"] != "presence.customer_left":
                    presence_payload = presence_message["payload"]
                else:
                    presence_payload = None
                await visualization_hub.broadcast(presence_message)
    except WebSocketDisconnect:
        visualization_hub.disconnect(websocket)
        if presence_payload:
            await visualization_hub.broadcast(
                {
                    "type": "presence.customer_left",
                    "payload": presence_payload,
                    "correlation_id": f"presence:{presence_payload['visitor_id']}",
                    "created_at": datetime.utcnow().isoformat(),
                }
            )


@app.get("/user/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    return {
        "user_id": user.user_id,
        "nickname": user.nickname,
        "balance": float(user.balance),
        "taste_preference": user.taste_preference,
    }


@app.get("/history/{user_id}")
def get_chat_history(user_id: int):
    return get_history(user_id)


@app.delete("/history/{user_id}")
def clear_chat_history(user_id: int):
    from app.memory.chat_history import clear_history

    clear_history(user_id)
    return {"ok": True}


@app.get("/orders/{user_id}")
def list_orders(user_id: int, db: Session = Depends(get_db)):
    """返回某用户的订单列表（最近 10 单），供网页侧栏展示"""
    rows = (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "order_id": o.order_id,
            "coffee_name": o.coffee_name,
            "amount": float(o.amount),
            "status": o.status,
            "source_type": o.source_type,
            "payment_status": o.payment_status,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for o in rows
    ]


@app.get("/status")
def status():
    """Return system status for the fixed MySQL/Redis architecture."""
    return {
        "database": "mysql",
        "memory": "redis",
        "llm_active": llm.has_real_key(),
        "llm_key_source": settings.llm_api_key_source,
        "llm_status_reason": settings.llm_status_reason,
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
    }


@app.get("/")
def index():
    """根路由：返回聊天网页"""
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/screen")
def screen():
    """Full-screen restaurant visualization display."""
    return FileResponse(_STATIC_DIR / "screen.html")


@app.get("/screeny")
def screeny():
    """Alias for the full-screen restaurant visualization display."""
    return FileResponse(_STATIC_DIR / "screen.html")
