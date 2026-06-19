"""FastAPI entrypoint for chat ordering and Agent visualization APIs."""
from datetime import datetime
from typing import Any, Optional

from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import AgentProfile, CoffeeKB, EvomapConsumer, Order, User, VisualizationEvent
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


# 待确认订单时，用户确认的触发词（LLM 优先，这是关键字的底层兜底）
_CONFIRM_WORDS = (
    "确认", "下单", "好的", "好", "对", "是的", "没错",
    "买", "可以", "行", "就下单", "下单吧", "结账",
    "没错下单", "对了下单",
)


def _is_confirming(user_msg):
    """判断用户是否在确认待支付订单。
    用 startswith 而非 in，避免「不对」被「对」误判。
    """
    msg = user_msg.strip()
    if len(msg) <= 6:
        return any(msg.startswith(w) for w in _CONFIRM_WORDS)
    return False


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
    if not agent or agent.status != "active":
        raise HTTPException(status_code=404, detail="Agent 不存在或已停用")
    if agent.api_token_hash != hash_agent_token(token):
        raise HTTPException(status_code=401, detail="Agent API token 无效")
    return agent


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """Handle chat, recommendation, pending confirmation, and paid order flows."""
    consumer_url = _normalize_consumer_url(req.consumer_url)
    web_source_payload = {
        "source_type": "web_dialog",
        "consumer_url": consumer_url,
        "correlation_id": req.request_id,
    }
    _try_publish_visualization_event(
        db,
        "message.received",
        {"user_id": req.user_id, "message": req.message, **web_source_payload},
        correlation_id=req.request_id,
    )
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
                    source_type="web_dialog",
                    consumer_url=consumer_url,
                    correlation_id=req.request_id,
                )
            except InsufficientBalanceError as e:
                clear_pending_order(req.user_id)
                reply = f"下单失败：{e}。请先充值哦~"
                add_message(req.user_id, "user", req.message)
                add_message(req.user_id, "assistant", reply)
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
        status="active",
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
        status="active",
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
    if not consumer or consumer.status != "active":
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
        .filter(AgentProfile.status == "active")
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


@app.websocket("/ws/visualization")
async def visualization_websocket(websocket: WebSocket):
    await visualization_hub.connect(websocket)
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
    except WebSocketDisconnect:
        visualization_hub.disconnect(websocket)


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
    }


@app.get("/")
def index():
    """根路由：返回聊天网页"""
    return FileResponse(_STATIC_DIR / "index.html")
