"""FastAPI entrypoint for chat ordering and Agent visualization APIs."""
import asyncio
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import anyio
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal, get_db, Base, engine
from app.db.models import (
    AgentProfile,
    EvomapConsumer,
    Order,
    SkillOrderLedger,
    User,
    VisualizationEvent,
)
from app.db.models import OrderItem, Product
from app.domain_constants import WALLET_CURRENCY_CNY
from app.services import autonomous_agent_service, office_layout_service, wallet_service
from app.domain_constants import (
    IDENTITY_STATUS_ACTIVE,
    ORDER_SOURCE_SKILL,
    ORDER_SOURCE_WEB_DIALOG,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_FREE,
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
from app.memory._redis_client import get_redis_client
from app.services.chat_service import extract_price, handle_message, match_by_price, get_all_products, resolve_image_path
from app.services.agent_orchestrator import orchestrate as agent_orchestrate
from app.services.agents.experience_agent import list_recent_experiences
from app.services import visitor_analytics_service
from app.services import user_profile_service
from app.services.reorder_service import detect_reorder_intent as _detect_reorder_intent
from app.services.reorder_service import resolve_reorder_target as _resolve_reorder_target
from app.services import evomap_evolution_service
from app.services.agents.experience_agent import sync_community_experience as _sync_community_exp
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
    broadcast_visualization_message,
    decode_json,
    encode_json,
    event_to_message,
    generate_agent_token,
    hash_agent_token,
    make_sprite_seed,
    publish_visualization_event,
    publish_visualization_events,
    visualization_event_bus,
    visualization_hub,
)
from app.services import staff_service
from app.auth import service as auth_service
from app.colyseus_bridge import start_colyseus_server, stop_colyseus_server

app = FastAPI(title="Crossroads Agent Café")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

# EvoMap 心跳定时器（群体进化：保持节点在线 + 定时拉取社区经验）
_evomap_heartbeat_thread: threading.Thread | None = None
_evomap_heartbeat_stop = threading.Event()

# 自主数字顾客循环（P1：每 45-75s 跑一次模拟买咖啡会话，3D 人偶自主走动）
_autonomous_task: asyncio.Task | None = None


def _evomap_heartbeat_loop() -> None:
    """后台心跳线程：每 5 分钟发心跳 + 拉取社区经验缓存到 Redis。"""
    import time as _time
    while not _evomap_heartbeat_stop.is_set():
        try:
            evomap_evolution_service.heartbeat()
            _sync_community_exp()
        except Exception:
            pass  # 心跳失败不阻塞服务
        _evomap_heartbeat_stop.wait(300)  # 5 分钟


def _ensure_staff_seeded() -> None:
    """幂等创建 4 个固有服务员 agent（启动时落库）。

    不在 startup 广播 agent.registered：冷启动时无已连接客户端，--reload 时进程
    重启、内存连接集合清空、客户端会断开重连并收到新的 scene.snapshot。服务员
    由 _build_snapshot_agents 稳定返回，是客户端看到服务员团队的唯一可靠路径。
    Best-effort：失败绝不阻断 app 启动。
    """
    try:
        db = SessionLocal()
        try:
            staff_service.ensure_staff_agents(db)
        finally:
            db.close()
    except Exception:
        pass


@app.on_event("startup")
async def _startup_colyseus() -> None:
    # SQLite/MySQL 双后端：首次启动自动建表（幂等，已有表不会重建）。
    Base.metadata.create_all(bind=engine)
    start_colyseus_server()
    await visualization_event_bus.start()
    _ensure_staff_seeded()
    # 预加载 jieba(中文分词库)：词典初始化需 ~1s，放启动期避免首个 /chat 请求卡顿。
    _preload_jieba()
    # 预热 LLM httpx 连接池：提前完成 DNS 解析 + TLS 握手，省首请求 ~0.5s。
    _warm_llm_connection()
    # Background sweep: drop Skill/CLI customer avatars once their heartbeat window
    # expires (they can't push a leave signal — the order.py script already exited).
    global _skill_sweep_task
    _skill_sweep_task = asyncio.create_task(_skill_presence_sweep_loop())
    # 自主数字顾客循环：后端 Agent runtime 定时决策并驱动 3D 人偶。
    global _autonomous_task
    if settings.autonomous_agent_enabled:
        _autonomous_task = asyncio.create_task(autonomous_agent_service.autonomous_loop())
    # 启动 EvoMap 心跳（仅当配置了节点身份）
    if settings.evomap_node_id and settings.evomap_node_secret:
        _evomap_heartbeat_stop.clear()
        _evomap_heartbeat_thread = threading.Thread(target=_evomap_heartbeat_loop, daemon=True)
        _evomap_heartbeat_thread.start()


def _preload_jieba() -> None:
    """在启动时预加载 jieba 词典（~1s），避免第一个 /chat 请求承担延迟。"""
    try:
        import jieba  # noqa: F401
        jieba.initialize()
        logger.info("jieba(中文分词) 词典预加载完成")
    except Exception:
        logger.warning("jieba 预加载失败，将在首个请求时延迟加载", exc_info=True)


def _warm_llm_connection() -> None:
    """预热 LLM httpx 连接池：提前建立到 LLM 服务器的 TCP+TLS 连接。

    首个 LLM 调用省去 DNS 解析 + TLS 握手（~0.5s）。用 HEAD 请求探测，
    不消耗 API 额度；失败静默（首个请求时会正常建连）。
    """
    if not settings.effective_llm_api_key:
        return
    try:
        from app.llm.client import get_client
        from urllib.parse import urlparse
        parsed = urlparse(settings.llm_base_url)
        host = parsed.hostname
        if not host:
            return
        scheme = parsed.scheme or "https"
        port = parsed.port or (443 if scheme == "https" else 80)
        base = f"{scheme}://{host}:{port}"
        # 建一个 dummy 连接放进连接池（不发送真实请求）
        client = get_client()
        try:
            client.head(base, timeout=2.0)
        except Exception:
            pass  # 连接已建立，即使 HEAD 被拒绝也达到预热目的
        logger.info("LLM 连接池预热完成: %s", base)
    except Exception:
        pass  # 预热失败不影响功能


@app.on_event("shutdown")
async def _shutdown_colyseus() -> None:
    stop_colyseus_server()
    await visualization_event_bus.stop()
    _evomap_heartbeat_stop.set()
    global _skill_sweep_task
    if _skill_sweep_task is not None:
        _skill_sweep_task.cancel()
        _skill_sweep_task = None
    global _autonomous_task
    if _autonomous_task is not None:
        _autonomous_task.cancel()
        _autonomous_task = None


_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
# 3D office app build output (Vite -> app/static/3d). Served at /3d/.
_3D_STATIC_DIR = Path(__file__).resolve().parent / "static" / "3d"
if _3D_STATIC_DIR.is_dir():
    _3d_assets = _3D_STATIC_DIR / "assets"
    if _3d_assets.is_dir():
        app.mount("/3d/assets", StaticFiles(directory=_3d_assets), name="static-3d-assets")
    _3d_office_assets = _3D_STATIC_DIR / "office-assets"
    if _3d_office_assets.is_dir():
        app.mount("/3d/office-assets", StaticFiles(directory=_3d_office_assets), name="static-3d-office-assets")
    _3d_evomap_materials = _3D_STATIC_DIR / "evomap-materials"
    if _3d_evomap_materials.is_dir():
        app.mount("/3d/evomap-materials", StaticFiles(directory=_3d_evomap_materials), name="static-3d-evomap-materials")
    _3d_sounds = _3D_STATIC_DIR / "sounds"
    if _3d_sounds.is_dir():
        # 3D 场景背景音乐（m1/m2 ...），构建产物来自 frontend/public/sounds/。
        # 不挂载则会被 /3d/{full_path:path} SPA fallback 返回 HTML，Audio.play 静默失败。
        app.mount("/3d/sounds", StaticFiles(directory=_3d_sounds), name="static-3d-sounds")

# 咖啡菜单图片（app/images/ 下的 PNG）
_IMAGES_DIR = Path(__file__).resolve().parent / "images"
if _IMAGES_DIR.is_dir():
    app.mount("/images", StaticFiles(directory=_IMAGES_DIR), name="menu-images")

from app.auth.router import router as auth_router  # noqa: E402

app.include_router(auth_router)

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
    all_coffees = [c.name for c in get_all_products(db)]
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


def _lookup_price_from_product(db, coffee_name):
    """从商品目录查价格，查不到返回 0"""
    product = db.query(Product).filter(Product.name == coffee_name).first()
    return float(product.base_price) if product else 0.0


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

# ======/chat 加速：启发式判断消息是否「明显不是下单」以跳过 parse_intent 的 LLM 调用/======
# 触发条件：消息含订单/确认信号 → 必须调 parse_intent 提取 coffee_name 等细节；
# 否则消息含推荐/口味/问号等信号 → 直接走 recommend，省一次 LLM 往返（约 1-5s）。
_ORDER_HEURISTIC_WORDS = (
    "买", "下单", "结账", "扣钱", "扣款", "付款", "买单", "从余额",
    "来一杯", "来个", "来两杯", "要一杯", "要个", "要两杯",
    "点一杯", "点个", "来份", "给我来", "整一杯", "整一个",
    "就这个", "就它", "这两杯", "就买", "就点",
)
# 明确的推荐/聊天信号（仅在不含订单词时才触发跳过）
_RECOMMEND_CHAT_HINTS = (
    "推荐", "有什么", "介绍一下", "介绍下", "区别", "哪种", "换口味", "换个",
    "多少钱", "几点", "为什么", "怎么", "如何", "？", "?", "吗",
    "果味", "苦", "甜", "酸", "椰", "口味", "偏好", "忌口", "喜欢", "清爽",
    "不要牛奶", "无奶", "不加奶", "深烘", "浅烘", "加冰", "热饮", "冷饮",
)


def _is_clearly_non_order(user_msg: str) -> bool:
    """启发式：消息是否「明显不是下单」，可以跳过 parse_intent 的 LLM 调用。

    保守策略：拿不准时返回 False（仍调 LLM），只在非常确定时才跳过省一次调用。
    安全兜底：即便误判为「非下单」，orchestrator(编排器) 里的 _detect_exact_product
    仍会从消息里捞出精确商品名（如「柑橘冷萃」）并改路由为 order。
    """
    msg = user_msg.strip()
    if not msg:
        return True  # 空消息不会下单
    # 含疑问标记 → 提问而非下单（即使以「可以」开头也是提问，如「可以加冰吗」）
    if any(w in msg for w in _CONFIRM_QUESTION_MARKS):
        return True
    # 含订单词或确认词 → 不能跳过
    if any(w in msg for w in _ORDER_HEURISTIC_WORDS):
        return False
    if any(w in msg for w in _CONFIRM_STRONG):
        return False
    if len(msg) <= 6 and any(msg.startswith(w) for w in _CONFIRM_WEAK):
        return False
    # 没有订单词时，再看是否有推荐/聊天信号
    return any(w in msg for w in _RECOMMEND_CHAT_HINTS)


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
    products: Optional[list[dict]] = None  # 推荐/菜单场景的产品卡片数据


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
    return publish_visualization_event(
        db,
        event_type=event_type,
        payload=payload,
        agent_id=agent_id,
        correlation_id=correlation_id,
    )


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
        broadcast_visualization_message(
            {
                "event_id": None,
                "type": event_type,
                "agent_id": agent_id,
                "payload": payload,
                "correlation_id": correlation_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            replay=True,
        )


def _try_publish_visualization_events(
    db: Session,
    events: list[dict[str, Any]],
) -> None:
    if not events:
        return
    try:
        publish_visualization_events(db, events)
    except Exception:
        db.rollback()
        for event in events:
            broadcast_visualization_message(
                {
                    "event_id": None,
                    "type": event["event_type"],
                    "agent_id": event.get("agent_id"),
                    "payload": event.get("payload") or {},
                    "correlation_id": event.get("correlation_id"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                replay=True,
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


def _web_restaurant_event_record(
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
    agent_id: int | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "payload": _web_restaurant_payload(
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
        "agent_id": agent_id,
        "correlation_id": req.request_id,
    }


def _staff_action_event_record(
    staff: dict[str, AgentProfile],
    role: str,
    action_type: str,
    correlation_id: str,
) -> dict[str, Any] | None:
    staff_agent = staff.get(role)
    if staff_agent is None:
        return None
    return {
        "event_type": "agent.action",
        "payload": {
            "agent_id": staff_agent.agent_id,
            "tool_name": staff_agent.tool_name,
            "display_name": staff_agent.display_name,
            "role_type": staff_agent.role_type,
            "sprite_seed": staff_agent.sprite_seed,
            "action_type": action_type,
        },
        "agent_id": staff_agent.agent_id,
        "correlation_id": correlation_id,
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
    agent_id: int | None = None,
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
        agent_id=agent_id,
        correlation_id=req.request_id,
    )


def _publish_web_completion_flow(
    db: Session,
    *,
    req: ChatRequest,
    consumer_url: str | None,
    orders: list[Order],
    agent_id: int | None = None,
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
        "agent_id": agent_id,
    }
    # 服务员团队编排（对齐 Skill 路径 _publish_skill_completion_flow）：各业务节点
    # 发完 restaurant.* 事件后追加服务员 agent.action，让 3D 场景里的服务员团队完整
    # 联动（cashier 接单 → barista 做咖啡 → waiter 送餐 → 复位）。best-effort：
    # ensure/orchestrate 内部已包 try/except，可视化绝不阻断点单/支付业务。
    try:
        staff = staff_service.ensure_staff_agents(db)
    except Exception:
        staff = {}
    correlation = req.request_id
    events: list[dict[str, Any]] = []
    events.append(_web_restaurant_event_record(
        "restaurant.payment_completed",
        state="payment_completed",
        patience=82,
        satisfaction=88,
        **common,
    ))
    staff_event = _staff_action_event_record(staff, "cashier", "take_order", correlation)
    if staff_event:
        events.append(staff_event)
    for stage, label, patience in (
        ("grinding", "grinding beans", 78),
        ("brewing", "brewing coffee", 72),
        ("plating", "plating order", 68),
    ):
        events.append(_web_restaurant_event_record(
            "restaurant.preparation_progress",
            state="making",
            stage=stage,
            message=label,
            patience=patience,
            satisfaction=90,
            **common,
        ))
        staff_event = _staff_action_event_record(staff, "barista", "prepare_coffee", correlation)
        if staff_event:
            events.append(staff_event)
    events.append(_web_restaurant_event_record(
        "restaurant.order_ready",
        state="ready",
        patience=70,
        satisfaction=92,
        **common,
    ))
    staff_event = _staff_action_event_record(staff, "barista", "enter_scene", correlation)
    if staff_event:
        events.append(staff_event)
    events.append(_web_restaurant_event_record(
        "restaurant.order_delivered",
        state="delivered",
        patience=74,
        satisfaction=94,
        **common,
    ))
    staff_event = _staff_action_event_record(staff, "waiter", "deliver_order", correlation)
    if staff_event:
        events.append(staff_event)
    events.append(_web_restaurant_event_record(
        "restaurant.customer_reviewed",
        state="reviewed",
        message="顾客评价：出餐顺利",
        patience=76,
        satisfaction=96,
        **common,
    ))
    events.append(_web_restaurant_event_record(
        "restaurant.customer_left",
        state="left",
        patience=80,
        satisfaction=96,
        **common,
    ))
    for role in ("waiter", "cashier"):
        staff_event = _staff_action_event_record(staff, role, "enter_scene", correlation)
        if staff_event:
            events.append(staff_event)
    _try_publish_visualization_events(db, events)
    # 画像总结（购买完成触发）：异步 fire-and-forget，仅登录用户有效，
    # 失败 swallow 绝不阻断下单。放在完成流最末，确保订单已落库可被画像读取。
    try:
        user_profile_service.summarize_async(req.user_id)
    except Exception:
        logger.warning("web 画像总结触发失败 user_id=%s", req.user_id, exc_info=True)


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
    # 建立网页顾客 agent（匿名 user_id 也建），让其人偶进入 3D 场景。
    # customer_enter_scene 刷 last_seen_at（落入 snapshot 心跳窗口）+ 广播
    # enter_scene（已连接客户端实时创建人偶）。best-effort：绝不阻断点单。
    customer_agent_id: int | None = None
    try:
        customer_agent = staff_service.ensure_web_customer_agent(db, req.user_id)
        customer_agent_id = customer_agent.agent_id
        staff_service.customer_enter_scene(
            db, customer_agent, correlation_id=req.request_id
        )
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    # 预取店长 agent（只读查询，不触发创建）；用于回复时广播 show_message 让 3D
    # 店长人偶气泡显示回复（3D 交互增强·第三步）。best-effort：未创建则为 None 跳过。
    _manager_agent = None
    try:
        _manager_agent = (
            db.query(AgentProfile)
            .filter(AgentProfile.tool_name == "staff:manager")
            .first()
        )
    except Exception:
        pass

    def _broadcast_reply_speech(text: str) -> None:
        """3D 交互增强·第三步：让 3D 店长气泡显示回复。best-effort，不阻断 /chat。"""
        if not text or _manager_agent is None:
            return
        try:
            staff_service.publish_agent_action(
                db,
                _manager_agent,
                "show_message",
                text=text[:200],
                correlation_id=req.request_id,
            )
        except Exception:
            pass

    _publish_web_restaurant_event(
        db,
        "restaurant.customer_entered",
        req=req,
        consumer_url=consumer_url,
        state="entered",
        message=req.message,
        patience=100,
        satisfaction=80,
        agent_id=customer_agent_id,
    )
    _try_publish_visualization_event(
        db,
        "message.received",
       {"user_id": req.user_id, "message": req.message, **web_source_payload},
       agent_id=customer_agent_id,
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
        _broadcast_reply_speech(reply)
        return ChatResponse(reply=reply)

    # ===== 第1步：读 Redis 上下文（短期记忆，最近5轮对话）=====
    history = get_history(req.user_id)

    # 访客分析：记录今日访客（best-effort，不阻断主流程）
    try:
        visitor_analytics_service.record_visit(db, user_id=req.user_id, message=req.message)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

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
                    agent_id=customer_agent_id,
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
                    agent_id=customer_agent_id,
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
                _broadcast_reply_speech(reply)
                return ChatResponse(reply=reply)

            clear_pending_order(req.user_id)
            user = db.query(User).filter(User.user_id == req.user_id).first()
            balance = (
                wallet_service.get_balance(db, req.user_id, WALLET_CURRENCY_CNY)
                if user
                else "?"
            )
            if len(orders) == 1:
                reply = (
                    f"好嘞！已为您下单「{orders[0].coffee_name}」，扣款 ¥{orders[0].amount}，"
                    f"当前余额 {int(balance)}元。祝您品尝愉快~"
                )
            else:
                order_lines = "\n".join(f"  • {o.coffee_name} ¥{o.amount}" for o in orders)
                total = sum(o.amount for o in orders)
                reply = (
                    f"好嘞！已为您下单 {len(orders)} 杯：\n{order_lines}\n"
                    f"合计 ¥{total}，当前余额 {int(balance)}元。祝您品尝愉快~"
                )
            add_message(req.user_id, "user", req.message)
            add_message(req.user_id, "assistant", reply)
            _publish_web_completion_flow(
                db,
                req=req,
                consumer_url=consumer_url,
                orders=orders,
                agent_id=customer_agent_id,
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
            _broadcast_reply_speech(reply)
            # 访客分析：标记已下单
            try:
                visitor_analytics_service.mark_ordered(db, user_id=req.user_id, order_id=orders[0].order_id)
            except Exception:
                pass
            return ChatResponse(reply=reply, order_id=orders[0].order_id)
        else:
            # 不是纯确认词 → 清掉待确认，落入下方正常流程重新处理
            # （覆盖：修改订单"只要28的"、换一杯、重新选、闲聊等所有情况）
            clear_pending_order(req.user_id)

    # ===== 第2步：无待确认订单 → 调 LLM 理解用户意图 =====
    # 加速 1：消息含精确/部分商品名（"美式"→"美式咖啡"）→ 直接 order，跳过所有 LLM 调用
    # 加速 2：消息「明显不是下单」时跳过 parse_intent，直接走 recommend
    from app.services.agent_orchestrator import _detect_exact_product
    exact_product = _detect_exact_product(db, req.message)
    if exact_product:
        intent = {"intent": "order", "coffee_name": exact_product, "reason": "exact_product_match"}
    elif _is_clearly_non_order(req.message):
        intent = {"intent": "recommend", "reason": "heuristic_skip_parse_intent"}
    else:
        intent = llm.parse_intent(history, req.message)
    _try_publish_visualization_event(
        db,
        "order.intent_detected",
        {"user_id": req.user_id, "intent": intent.get("intent", "chat"), **web_source_payload},
        correlation_id=req.request_id,
    )
    # 服务员编排：意图识别后服务员走向收银台准备接单（对齐 Skill 路径
    # process_skill_order 的 intent_detected 节点 → waiter walk_to_counter）。best-effort。
    try:
        _staff = staff_service.ensure_staff_agents(db)
    except Exception:
        _staff = {}
    staff_service.orchestrate_staff_node(db, _staff, "intent_detected", req.request_id)

    # 访客分析：更新意图分类（best-effort）
    try:
        visitor_analytics_service.update_visit_intent(db, req.user_id, intent.get("intent", "chat"))
    except Exception:
        pass

    # ===== 第3步：LLM 判断为"下单"意图 → 解析具体是哪杯咖啡 =====
    # 四路优先级：价格匹配 > LLM显式名 > RAG关键词 > 历史提取
    if intent.get("intent") == "order":
        coffees = []

        # 第3.1路：价格匹配（"来个28元的"→ 按价格查 MySQL CoffeeKB）
        price = extract_price(req.message)
        if price is not None:
            coffees = [c.name for c in match_by_price(db, price)]

        # 第3.15路：复购意图 → 查真实历史订单最常点款（优先于 LLM 盲猜）
        # 用户说「和之前一样/老样子/上次那杯」时，LLM 会从对话上下文盲猜出刚推荐
        # 的同款（如刚推荐柑橘冷萃→"和之前一样"又被解析成柑橘冷萃）。这是错的：
        # "之前"在用户语境里指历史订单/常点款。所以复购意图必须优先于 LLM 盲猜，
        # 查真实历史订单最常点的那杯。历史为空（新用户）回退到后续 LLM/RAG 路。best-effort。
        if not coffees:
            try:
                if _detect_reorder_intent(req.message):
                    reorder_coffee = _resolve_reorder_target(db, req.user_id)
                    if reorder_coffee:
                        coffees = [reorder_coffee]
                        logger.info("复购解析命中 user_id=%s → %s", req.user_id, reorder_coffee)
            except Exception:
                logger.warning("复购意图解析失败 user_id=%s", req.user_id, exc_info=True)

        # 第3.2路：LLM 显式给出了咖啡名（它能理解"一开始说的""刚才那杯"等引用）
        # 信任 LLM 的引用理解能力，排在历史盲扫之前
        _llm_gave_unknown_coffee = False  # 标记 LLM 给了咖啡名但不在菜单
        if not coffees:
            coffee = intent.get("coffee_name")
            if coffee:
                # 处理 LLM 可能返回合并名 "柑橘冷萃和美式咖啡"
                valid_names = [c.name for c in get_all_products(db)]
                parts = [p.strip() for p in coffee.replace("和", ",").replace("、", ",").split(",") if p.strip()]
                matched = [p for p in parts if p in valid_names]
                if matched:
                    coffees = matched
                else:
                    # LLM 给了咖啡名但都不在菜单 → 用户说的是不存在的咖啡
                    _llm_gave_unknown_coffee = True

        # 第3.3路：消息含描述性词（"无牛奶"/"果味"）→ RAG 关键词过滤
        # 跳过条件：LLM 已判定为不存在的咖啡（避免 RAG/历史误匹配）
        if not coffees and not _llm_gave_unknown_coffee:
            positive, negative = extract_keywords(req.message)
            if positive or negative:
                coffees = [r.name for r in retrieve(db, positive, negative)]

        # 第3.4路：以上都没命中 → 从 Redis 历史提取（最弱信号，兜底）
        # 跳过条件：LLM 已判定为不存在的咖啡
        # 默认只看最近1条消息（1杯）；用户说「两杯/这些/都」时跨轮提取3条
        _MULTI_SIGNALS = ("两杯", "这些", "都", "全部", "三个", "两个", "这几杯", "都来", "全要")
        wants_multi = any(w in req.message for w in _MULTI_SIGNALS)
        if not coffees and not _llm_gave_unknown_coffee:
            scan = 3 if wants_multi else 1
            coffees = _resolve_coffees_from_history(db, history, max_messages=scan)

        # 默认只取 1 杯，除非明确说了多杯信号
        if len(coffees) > 1 and not wants_multi:
            coffees = coffees[:1]

        if not coffees:
            # 区分：用户说了咖啡名但我们没有 vs 完全没说咖啡名
            # 如果消息含咖啡品类词但没匹配任何产品 → 用户说的是不存在的咖啡
            _COFFEE_TYPE_WORDS = (
                "咖啡", "拿铁", "美式", "冷萃", "玛奇朵", "摩卡", "卡布", "卡布奇诺",
                "澳白", "澳白咖啡", "flat white", "espresso", "意式", "浓缩",
                "手冲", "挂耳", "速溶", "frappe", "frappuccino", "玛奇朵",
            )
            msg_lower = req.message.lower()
            says_coffee_type = any(w.lower() in msg_lower for w in _COFFEE_TYPE_WORDS)
            if says_coffee_type:
                reply = "这款我们没有哦～您说的这个问题我们已经反馈给店长了，感谢您的光临！目前可以试试我们的美式、柑橘冷萃、椰香冷萃、焦糖玛奇朵或莓果拿铁～"
            else:
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
                agent_id=customer_agent_id,
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
            _broadcast_reply_speech(reply)
            return ChatResponse(reply=reply)

        # ===== 第4步：两段式下单 —— 先存 Redis 待确认，显示摘要（不直接扣款）=====
        # 把选中的咖啡名+价格存入 Redis，等用户回复"确认"后才执行扣款
        items = []
        for name in coffees:
            p = _lookup_price_from_product(db, name)
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
            agent_id=customer_agent_id,
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
        _broadcast_reply_speech(reply)
        return ChatResponse(reply=reply)

    # ===== 非下单意图（recommend/chat）→ 多 Agent(智能体) 协作流程 =====
    # 编排器按序调用：店长(意图)→推荐(RAG+经验)→[纠正检测]→复盘→经验继承
    # emit 回调：编排器在每步执行时实时推送 agent 事件（让前端灯在思考期间跟着亮）
    def _emit_agent_event(event_type: str, payload: dict) -> None:
        _try_publish_visualization_event(
            db,
            event_type,
            {**payload, **web_source_payload},
            correlation_id=req.request_id,
        )

    clear_pending_order(req.user_id)
    orch = agent_orchestrate(
        db,
        req.user_id,
        req.message,
        correlation_id=req.request_id,
        precomputed_intent=intent,
        emit=_emit_agent_event,
    )
    # 编排器已在执行期间实时推送 agent.* 事件（通过 emit 回调），无需再批量发布
    # 若编排器已写对话历史并给出回复，直接返回
    if orch.reply:
        _broadcast_reply_speech(orch.reply)
        # 访客分析：非下单路径，异步触发流失分析
        visitor_analytics_service.analyze_churn_async()
        return ChatResponse(reply=orch.reply, products=orch.products if orch.products else None)
    # 编排器降级（如无 LLM key）：回退到原 handle_message
    reply, products = handle_message(db, req.user_id, req.message)
    _try_publish_visualization_event(
        db,
        "order.reply",
        {"user_id": req.user_id, "intent": intent.get("intent", "chat"), **web_source_payload},
        correlation_id=req.request_id,
    )
    _broadcast_reply_speech(reply)
    visitor_analytics_service.analyze_churn_async()
    return ChatResponse(reply=reply, products=products if products else None)


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


@app.get("/admin/autonomous-agent/status")
def autonomous_agent_status(db: Session = Depends(get_db)):
    """Read-only status for the backend-driven autonomous 3D customer."""
    return autonomous_agent_service.status_snapshot(db)


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


@app.get("/admin/agent-collaboration")
def agent_collaboration_state(db: Session = Depends(get_db)):
    """多 Agent(智能体) 协作面板数据：最近经验记录 + 协作事件统计。"""
    experiences = list_recent_experiences(db, limit=20)
    # 统计最近 200 条事件中各 Agent 的协作次数
    agent_event_types = (
        "agent.manager.intent",
        "agent.recommender.suggested",
        "agent.reviewer.reviewed",
        "agent.experience.learned",
        "agent.experience.applied",
    )
    rows = (
        db.query(VisualizationEvent.event_type, func.count(VisualizationEvent.event_id))
        .filter(
            VisualizationEvent.event_type.in_(agent_event_types),
        )
        .group_by(VisualizationEvent.event_type)
        .all()
    )
    stats = {row[0]: int(row[1]) for row in rows}
    return {
        "summary": {
            "total_experiences": len(experiences),
            "manager_actions": stats.get("agent.manager.intent", 0),
            "recommender_actions": stats.get("agent.recommender.suggested", 0),
            "reviewer_actions": stats.get("agent.reviewer.reviewed", 0),
            "experience_learned": stats.get("agent.experience.learned", 0),
            "experience_applied": stats.get("agent.experience.applied", 0),
        },
        "recent_experiences": experiences,
    }


@app.get("/admin/evomap/status")
def evomap_status():
    """EvoMap 群体进化节点状态（供大屏展示节点在线/积分/进化圈/社区经验）。"""
    return evomap_evolution_service.get_node_status()


@app.get("/admin/visitor-analytics")
def visitor_analytics(db: Session = Depends(get_db)):
    """访客分析面板：今日访客数、转化率、意图分布、访客列表。"""
    return visitor_analytics_service.get_daily_analytics(db)


@app.get("/admin/churn-analysis")
def churn_analysis(db: Session = Depends(get_db)):
    """流失分析面板：流失原因分类、今日流失详情、自进化洞察。"""
    return visitor_analytics_service.get_churn_analysis(db)


# ============================================================
# 访客社交：在线访客列表 + 访客聊天消息
# ============================================================

# 进程内在线访客注册表（WebSocket 连接时注册，断开时移除）。
# 格式: { agent_id: { display_name, joined_at, user_id } }
_online_visitors: dict[int, dict[str, Any]] = {}

# 最近的访客聊天消息缓存（最近100条，供新连接者回看）。
_visitor_chat_buffer: list[dict[str, Any]] = []
_VISITOR_CHAT_MAX = 100


def _register_online_visitor(agent_id: int, display_name: str, user_id: int | None = None) -> None:
    _online_visitors[agent_id] = {
        "agent_id": agent_id,
        "display_name": display_name,
        "user_id": user_id,
        "joined_at": datetime.now(timezone.utc).isoformat(),
    }


def _unregister_online_visitor(agent_id: int) -> None:
    _online_visitors.pop(agent_id, None)


def _add_visitor_chat(message: dict[str, Any]) -> None:
    _visitor_chat_buffer.append(message)
    if len(_visitor_chat_buffer) > _VISITOR_CHAT_MAX:
        _visitor_chat_buffer.pop(0)


@app.get("/admin/online-visitors")
def online_visitors():
    """获取当前在线访客列表（供大屏和社交面板展示）。"""
    return {
        "count": len(_online_visitors),
        "visitors": list(_online_visitors.values()),
    }


@app.get("/admin/visitor-chat")
def visitor_chat_history(limit: int = 50):
    """获取最近的访客聊天记录（供新连接者回看历史消息）。"""
    safe_limit = max(1, min(limit, _VISITOR_CHAT_MAX))
    return {
        "messages": _visitor_chat_buffer[-safe_limit:],
        "total": len(_visitor_chat_buffer),
    }


@app.get("/admin/today-topics")
def today_topics(db: Session = Depends(get_db)):
    """当天话题热度榜：聚合今日订单 + 访客聊天关键词，返回 TOP-N 热门话题。"""
    from collections import Counter

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # --- 1. 今日订单饮品统计 ---
    todays = (
        db.query(Order)
        .filter(Order.created_at >= today_start)
        .filter(Order.coffee_name.isnot(None))
        .all()
    )
    drink_counts: Counter[str] = Counter()
    for o in todays:
        name = (o.coffee_name or "").strip()
        if name:
            drink_counts[name] += 1

    # --- 2. 访客聊天关键词统计（今日）---
    chat_keywords: Counter[str] = Counter()
    HOT_KW = [
        ("冷饮", ["冷", "冰", "冷萃", "气泡"]),
        ("热饮", ["热", "拿铁", "美式", "摩卡", "卡布"]),
        ("特调", ["特调", "季节", "限定", "芒", "肉桂"]),
        ("推荐", ["推荐", "建议", "人气"]),
        ("优惠", ["优惠", "折扣", "活动", "券"]),
    ]
    today_chat = [
        m for m in _visitor_chat_buffer
        if m.get("created_at") and m["created_at"] >= today_start.isoformat()
    ]
    for m in today_chat:
        text = m.get("message", "")
        for label, kws in HOT_KW:
            if any(kw in text for kw in kws):
                chat_keywords[label] += 1

    # --- 3. 合并计算热度 ---
    topics: list[dict[str, Any]] = []
    max_orders = max(drink_counts.values(), default=1)
    for name, cnt in drink_counts.most_common(5):
        heat = int(40 + (cnt / max_orders) * 50)  # 40-90 range
        topics.append({
            "label": name,
            "type": "drink",
            "count": cnt,
            "heat": min(99, heat),
            "rank": 0,
        })
    max_kw = max(chat_keywords.values(), default=1)
    for label, cnt in chat_keywords.most_common(3):
        if cnt == 0:
            continue
        heat = int(30 + (cnt / max_kw) * 40)
        topics.append({
            "label": label,
            "type": "topic",
            "count": cnt,
            "heat": min(89, heat),
            "rank": 0,
        })

    # Deduplicate + sort by heat
    seen = set()
    unique = []
    for t in topics:
        if t["label"] in seen:
            continue
        seen.add(t["label"])
        unique.append(t)
    unique.sort(key=lambda x: x["heat"], reverse=True)
    for i, t in enumerate(unique):
        t["rank"] = i + 1

    return {
        "topics": unique[:6],
        "total_orders_today": len(todays),
        "total_chats_today": len(today_chat),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class VisitorChatRequest(BaseModel):
    user_id: int
    display_name: str = Field(default="匿名访客")
    message: str


@app.post("/api/visitor-chat")
def post_visitor_chat(req: VisitorChatRequest):
    """访客发送社交聊天消息（通过 HTTP POST，服务端广播到所有 WebSocket 客户端）。"""
    msg = {
        "event_id": None,
        "type": "visitor.chat",
        "agent_id": None,
        "payload": {
            "user_id": req.user_id,
            "display_name": req.display_name,
            "message": req.message[:500],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "correlation_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _add_visitor_chat(msg["payload"])
    broadcast_visualization_message(msg, replay=True)
    return {"ok": True}


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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# Skill/CLI users can't hold a WebSocket (order.py exits after each request), so
# their "online" window is defined by agent.last_seen_at recency instead of presence.
ONLINE_WINDOW_SECONDS = 120
WEB_PRESENCE_KEY_PREFIX = "coffee:visualization:presence:web:"
SKILL_SWEEP_PREV_KEY = "coffee:visualization:skill_online_prev"
SKILL_SWEEP_LOCK_KEY = "coffee:visualization:skill_sweep_lock"


def _redis_visualization_enabled() -> bool:
    return not settings.use_fakeredis


def _web_presence_key(connection_id: str) -> str:
    return WEB_PRESENCE_KEY_PREFIX + connection_id


def _set_web_customer_presence(connection_id: str, customer: dict[str, Any]) -> None:
    if not _redis_visualization_enabled():
        return
    try:
        get_redis_client(decode_responses=True).set(
            _web_presence_key(connection_id),
            encode_json(customer),
            ex=max(5, settings.visualization_presence_ttl_seconds),
        )
    except Exception:
        pass


def _clear_web_customer_presence(connection_id: str) -> None:
    if not _redis_visualization_enabled():
        return
    try:
        get_redis_client(decode_responses=True).delete(_web_presence_key(connection_id))
    except Exception:
        pass


def _redis_online_ws_agent_ids() -> set[int]:
    if not _redis_visualization_enabled():
        return set()
    ids: set[int] = set()
    try:
        client = get_redis_client(decode_responses=True)
        for key in client.scan_iter(match=WEB_PRESENCE_KEY_PREFIX + "*", count=100):
            payload = decode_json(client.get(key), {})
            agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
            if agent_id is not None:
                ids.add(int(agent_id))
    except Exception:
        return set()
    return ids


def _acquire_skill_sweep_lock() -> str | None:
    if not _redis_visualization_enabled():
        return "local"
    token = uuid.uuid4().hex
    try:
        ok = get_redis_client(decode_responses=True).set(
            SKILL_SWEEP_LOCK_KEY,
            token,
            nx=True,
            ex=max(10, settings.visualization_skill_sweep_lock_ttl_seconds),
        )
        return token if ok else None
    except Exception:
        return None


def _release_skill_sweep_lock(token: str | None) -> None:
    if not token or token == "local" or not _redis_visualization_enabled():
        return
    try:
        client = get_redis_client(decode_responses=True)
        if client.get(SKILL_SWEEP_LOCK_KEY) == token:
            client.delete(SKILL_SWEEP_LOCK_KEY)
    except Exception:
        pass


def _load_prev_skill_online() -> set[int]:
    if not _redis_visualization_enabled():
        return set(_prev_skill_online)
    try:
        return {
            int(value)
            for value in get_redis_client(decode_responses=True).smembers(SKILL_SWEEP_PREV_KEY)
        }
    except Exception:
        return set()


def _store_prev_skill_online(agent_ids: set[int]) -> None:
    global _prev_skill_online
    if not _redis_visualization_enabled():
        _prev_skill_online = set(agent_ids)
        return
    try:
        client = get_redis_client(decode_responses=True)
        client.delete(SKILL_SWEEP_PREV_KEY)
        if agent_ids:
            client.sadd(SKILL_SWEEP_PREV_KEY, *[str(agent_id) for agent_id in agent_ids])
    except Exception:
        pass


def _agent_snapshot_dict(agent: AgentProfile) -> dict[str, Any]:
    """Lean agent descriptor matching frontend SnapshotAgent (net/api.ts)."""
    return {
        "agent_id": agent.agent_id,
        "tool_name": agent.tool_name,
        "display_name": agent.display_name,
        "role_type": agent.role_type,
        "sprite_seed": agent.sprite_seed,
        "status": agent.status,
    }


def _build_snapshot_agents(db: Session) -> list[dict[str, Any]]:
    """Agents sent in scene.snapshot: 4 fixed staff (always on duty) + online customers.

    A customer counts as online if they have a live web WS connection (presence) OR
    their agent.last_seen_at falls within ONLINE_WINDOW_SECONDS (Skill/CLI heartbeat
    window). Anonymous/not-logged-in visitors are not shown (login required).
    """
    agents: list[dict[str, Any]] = []
    # 1) Fixed staff — always on duty.
    try:
        for agent in staff_service.ensure_staff_agents(db).values():
            agents.append(_agent_snapshot_dict(agent))
    except Exception:
        pass
    # 2) Online customers: WS presence ∪ last_seen_at heartbeat window.
    online_ws_ids = visualization_hub.online_ws_agent_ids() | _redis_online_ws_agent_ids()
    cutoff = datetime.utcnow() - timedelta(seconds=ONLINE_WINDOW_SECONDS)
    query = db.query(AgentProfile).filter(
        AgentProfile.role_type == "customer",
        AgentProfile.status == IDENTITY_STATUS_ACTIVE,
    )
    if online_ws_ids:
        query = query.filter(
            or_(
                AgentProfile.agent_id.in_(online_ws_ids),
                AgentProfile.last_seen_at >= cutoff,
            )
        )
    else:
        query = query.filter(AgentProfile.last_seen_at >= cutoff)
    for agent in query.order_by(AgentProfile.last_seen_at.desc()).limit(30):
        agents.append(_agent_snapshot_dict(agent))
    return agents


def _register_web_customer_presence(websocket: WebSocket) -> dict[str, Any] | None:
    """Identify the logged-in web user from the signed session cookie and (re)create
    their customer agent, refreshing last_seen_at. Returns the agent snapshot dict
    (for presence + online broadcast), or None if not logged in.

    Anonymous visitors are intentionally not tracked/shown — login is required.
    Best-effort: failures return None and never break the WS handshake.
    """
    token = websocket.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    account_id = auth_service.read_session_token(token)
    if account_id is None:
        return None
    db = SessionLocal()
    try:
        account = auth_service.get_account_by_id(db, account_id)
        if account is None or account.status != IDENTITY_STATUS_ACTIVE:
            return None
        agent = staff_service.ensure_web_customer_agent(db, account.user_id)
        # Reflect the real login name (nickname/username), not the placeholder.
        agent.display_name = (account.nickname or account.username or agent.display_name)[:128]
        # Carry profile info (specialty/profession/gender) into agent metadata
        try:
            meta = decode_json(agent.metadata_json, {}) if agent.metadata_json else {}
        except Exception:
            meta = {}
        meta["source"] = meta.get("source", "web")
        meta["specialty"] = getattr(account, "specialty", None)
        meta["profession"] = getattr(account, "profession", None)
        meta["gender"] = getattr(account, "gender", None)
        agent.metadata_json = encode_json(meta)
        agent.last_seen_at = datetime.utcnow()
        db.commit()
        db.refresh(agent)
        return _agent_snapshot_dict(agent)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


def _build_snapshot_agents_for_connect() -> list[dict[str, Any]]:
    """DB-backed snapshot build run off the event loop (via anyio.to_thread)."""
    db = SessionLocal()
    try:
        return _build_snapshot_agents(db)
    finally:
        db.close()


# Skill/CLI customers can't push a go-offline signal (their script already exited),
# so already-connected clients wouldn't drop the avatar when the heartbeat window
# expires. This background sweep diffs the online set each interval and broadcasts
# leave_scene for anyone who just fell out of the window, so avatars vanish live.
# Web users are excluded (the WS disconnect handler handles them immediately).
SKILL_SWEEP_INTERVAL_SECONDS = 30
_prev_skill_online: set[int] = set()
_skill_sweep_task: asyncio.Task | None = None


async def _sweep_offline_skill_customers() -> None:
    token = _acquire_skill_sweep_lock()
    if token is None:
        return
    now_skill_online: set[int] = set()
    try:
        try:
            db = SessionLocal()
            try:
                cutoff = datetime.utcnow() - timedelta(seconds=ONLINE_WINDOW_SECONDS)
                ws_online = visualization_hub.online_ws_agent_ids() | _redis_online_ws_agent_ids()
                rows = (
                    db.query(AgentProfile)
                    .filter(
                        AgentProfile.role_type == "customer",
                        AgentProfile.status == IDENTITY_STATUS_ACTIVE,
                    )
                    .all()
                )
                for agent in rows:
                    if agent.agent_id in ws_online:
                        continue  # web user — handled by the disconnect handler
                    if agent.last_seen_at and agent.last_seen_at >= cutoff:
                        now_skill_online.add(agent.agent_id)
            finally:
                db.close()
        except Exception:
            return
        prev_skill_online = _load_prev_skill_online()
        newly_offline = prev_skill_online - now_skill_online
        _store_prev_skill_online(now_skill_online)
        for agent_id in newly_offline:
            await visualization_event_bus.publish(
                {
                    "event_id": None,
                    "type": "agent.action",
                    "agent_id": agent_id,
                    "payload": {"agent_id": agent_id, "action_type": "leave_scene"},
                    "correlation_id": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                replay=False,
            )
    finally:
        _release_skill_sweep_lock(token)


async def _skill_presence_sweep_loop() -> None:
    while True:
        await asyncio.sleep(SKILL_SWEEP_INTERVAL_SECONDS)
        try:
            await _sweep_offline_skill_customers()
        except Exception:
            pass


@app.websocket("/ws/visualization")
async def visualization_websocket(websocket: WebSocket):
    # Identify the logged-in web user (login required) and register WS presence so the
    # snapshot includes them as an online customer. Anonymous visitors are skipped.
    # DB work runs off the event loop so concurrent connects don't block each other.
    connection_id = uuid.uuid4().hex
    customer = await anyio.to_thread.run_sync(_register_web_customer_presence, websocket)
    if customer is not None:
        visualization_hub.register_ws_presence(websocket, customer["agent_id"])
        _set_web_customer_presence(connection_id, customer)
        _register_online_visitor(customer["agent_id"], customer["display_name"])
    agents = await anyio.to_thread.run_sync(_build_snapshot_agents_for_connect)
    await visualization_hub.connect(websocket, agents=agents)
    # Real-time appear: transient notice to OTHER clients (excludes self, not replayed).
    if customer is not None:
        await visualization_event_bus.publish(
            {
                "event_id": None,
                "type": "agent.registered",
                "agent_id": customer["agent_id"],
                "payload": {
                    "agent_id": customer["agent_id"],
                    "tool_name": customer.get("tool_name"),
                    "display_name": customer["display_name"],
                    "role_type": customer["role_type"],
                    "sprite_seed": customer["sprite_seed"],
                },
                "correlation_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            replay=False,
            exclude=websocket,
        )
    presence_payload: dict[str, Any] | None = None
    try:
        while True:
            message = await websocket.receive_json()
            if customer is not None:
                _set_web_customer_presence(connection_id, customer)
            if message.get("type") == "ping":
                visualization_hub.send_one(
                    websocket,
                    {
                        "type": "pong",
                        "payload": {},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                continue
            # Visitor social chat: broadcast to all connected clients.
            if message.get("type") == "visitor.chat":
                chat_payload = {
                    "user_id": message.get("user_id"),
                    "display_name": message.get("display_name", "匿名访客"),
                    "message": str(message.get("message", ""))[:500],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                _add_visitor_chat(chat_payload)
                await visualization_event_bus.publish(
                    {
                        "event_id": None,
                        "type": "visitor.chat",
                        "agent_id": None,
                        "payload": chat_payload,
                        "correlation_id": None,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    replay=True,
                )
                continue
            presence_message = _presence_message_from_client(message)
            if presence_message:
                if presence_message["type"] != "presence.customer_left":
                    presence_payload = presence_message["payload"]
                else:
                    presence_payload = None
                await visualization_event_bus.publish(presence_message, replay=True)
    except WebSocketDisconnect:
        visualization_hub.disconnect(websocket)
        _clear_web_customer_presence(connection_id)
        if customer is not None:
            _unregister_online_visitor(customer["agent_id"])
        # Real-time disappear: transient leave_scene (this ws is already gone from
        # the connection set, so broadcast_transient reaches the remaining clients).
        if customer is not None:
            await visualization_event_bus.publish(
                {
                    "event_id": None,
                    "type": "agent.action",
                    "agent_id": customer["agent_id"],
                    "payload": {
                        "agent_id": customer["agent_id"],
                        "tool_name": customer.get("tool_name"),
                        "display_name": customer["display_name"],
                        "role_type": customer["role_type"],
                        "sprite_seed": customer["sprite_seed"],
                        "action_type": "leave_scene",
                    },
                    "correlation_id": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                replay=False,
            )
        if presence_payload:
            await visualization_event_bus.publish(
                {
                    "type": "presence.customer_left",
                    "payload": presence_payload,
                    "correlation_id": f"presence:{presence_payload['visitor_id']}",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                replay=True,
            )


class OfficeLayoutRequest(BaseModel):
    items: list[Any]
    namespace: Optional[str] = "default"


@app.get("/api/office/layout")
def get_office_layout(namespace: str = "default", db: Session = Depends(get_db)):
    """3D 编辑器布局读取（匿名可读）。未保存时返回空列表，前端用默认/localStorage 兜底。"""
    items, updated_at = office_layout_service.get_layout_record(db, namespace)
    return {"items": items or [], "namespace": namespace, "updated_at": updated_at}


@app.put("/api/office/layout")
def put_office_layout(req: OfficeLayoutRequest, db: Session = Depends(get_db)):
    """3D 编辑器布局保存（匿名可写，遵循项目无登录门槛原则；单例 upsert）。"""
    office_layout_service.save_layout(db, list(req.items), req.namespace or "default")
    return {"ok": True, "namespace": req.namespace or "default"}


@app.get("/menu")
def get_menu(db: Session = Depends(get_db)):
    """返回完整菜单（供前端图片卡片渲染），含名称、价格、标签、图片路径。"""
    products = get_all_products(db)
    return [
        {
            "name": p.name,
            "price": float(p.base_price),
            "tags": p.tags or "",
            "category": p.category or "",
            "description": (p.description or "")[:120],
            "image": resolve_image_path(p.name),
            "stock": p.stock,
        }
        for p in products
    ]


@app.get("/user/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
   user = db.query(User).filter(User.user_id == user_id).first()
   if not user:
       raise HTTPException(404, "用户不存在")
   return {
       "user_id": user.user_id,
       "nickname": user.nickname,
        "balance": float(wallet_service.get_balance(db, user_id, WALLET_CURRENCY_CNY)),
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


# ---------------------------------------------------------------------------
# Agent Services Marketplace + Economic Value Dashboard
# ---------------------------------------------------------------------------

_AGENT_SERVICE_DEFS = [
    {
        "sku": "SVC-CODE-REVIEW",
        "name": "代码审查服务",
        "category": "agent_service",
        "description": "Agent 对你的 Pull Request 进行深度代码审查，覆盖安全漏洞、性能瓶颈、代码规范、架构合理性四个维度，输出结构化审查报告。适用于团队 CI/CD 流水线集成。",
        "base_price": Decimal("50.00"),
        "tags": "B端,代码审查,CI/CD,安全,质量保障",
        "stock": 9999,
        "icon": "🔍",
        "target": "B端",
        "unit": "次/PR",
        "time_saved_hours": 2.0,
    },
    {
        "sku": "SVC-DOC-WRITING",
        "name": "技术文档撰写",
        "category": "agent_service",
        "description": "Agent 根据代码仓库自动生成 API 文档、架构设计文档、变更日志。支持 Markdown / OpenAPI / AsciiDoc 格式输出，可直接推送到文档站点。",
        "base_price": Decimal("80.00"),
        "tags": "B端,文档,API,自动化,技术写作",
        "stock": 9999,
        "icon": "📝",
        "target": "B端",
        "unit": "篇/仓库",
        "time_saved_hours": 4.0,
    },
    {
        "sku": "SVC-DATA-ANALYSIS",
        "name": "数据洞察分析",
        "category": "agent_service",
        "description": "Agent 接入你的业务数据源，自动生成数据洞察报告：趋势分析、异常检测、用户分群、增长建议。支持 CSV / JSON / SQL 数据库输入。",
        "base_price": Decimal("120.00"),
        "tags": "B端,数据分析,BI,洞察,报表",
        "stock": 9999,
        "icon": "📊",
        "target": "B端",
        "unit": "份/数据集",
        "time_saved_hours": 8.0,
    },
    {
        "sku": "SVC-TRANSLATION",
        "name": "多语言翻译",
        "category": "agent_service",
        "description": "Agent 提供高质量多语言翻译服务，支持技术文档、产品文案、用户反馈等场景。中英日韩四语互译，保留专业术语和上下文语义。",
        "base_price": Decimal("30.00"),
        "tags": "C端,翻译,多语言,本地化",
        "stock": 9999,
        "icon": "🌐",
        "target": "C端",
        "unit": "千字",
        "time_saved_hours": 1.5,
    },
    {
        "sku": "SVC-API-INTEGRATION",
        "name": "API 集成方案",
        "category": "agent_service",
        "description": "Agent 分析你的系统集成需求，输出完整的 API 对接方案：接口选型、鉴权方案、错误处理、限流策略、代码示例。适用于企业级系统对接。",
        "base_price": Decimal("200.00"),
        "tags": "B端,API,集成,架构,企业级",
        "stock": 9999,
        "icon": "🔌",
        "target": "B端",
        "unit": "套/项目",
        "time_saved_hours": 16.0,
    },
    {
        "sku": "SVC-AUTO-SCRIPT",
        "name": "自动化脚本生成",
        "category": "agent_service",
        "description": "Agent 根据你的重复性工作描述，自动生成 Python / Shell / TypeScript 自动化脚本。包含错误处理、日志记录、定时调度，开箱即用。",
        "base_price": Decimal("100.00"),
        "tags": "C端,自动化,脚本,效率,Python",
        "stock": 9999,
        "icon": "⚙️",
        "target": "C端",
        "unit": "个/需求",
        "time_saved_hours": 6.0,
    },
    {
        "sku": "SVC-BUG-FIX",
        "name": "智能 Bug 定位",
        "category": "agent_service",
        "description": "Agent 分析 Bug 报告 + 错误日志 + 相关代码，精准定位根因并给出修复方案。支持 Java / Python / TypeScript / Go 等主流语言。",
        "base_price": Decimal("60.00"),
        "tags": "B端,C端,Bug,调试,修复",
        "stock": 9999,
        "icon": "🐛",
        "target": "B+C",
        "unit": "次/Bug",
        "time_saved_hours": 3.0,
    },
    {
        "sku": "SVC-TEST-GEN",
        "name": "测试用例生成",
        "category": "agent_service",
        "description": "Agent 根据你的代码自动生成单元测试、集成测试用例。覆盖边界条件、异常路径、性能基准。支持 pytest / Jest / JUnit 框架。",
        "base_price": Decimal("70.00"),
        "tags": "B端,测试,质量,自动化,CI",
        "stock": 9999,
        "icon": "🧪",
        "target": "B端",
        "unit": "套/模块",
        "time_saved_hours": 5.0,
    },
]


def _ensure_agent_services(db: Session) -> None:
    """Idempotent: insert agent_service products if they don't exist yet."""
    existing_skus = {
        row.sku for row in db.query(Product).filter(Product.category == "agent_service").all()
    }
    changed = False
    import json as _json
    for svc in _AGENT_SERVICE_DEFS:
        if svc["sku"] in existing_skus:
            continue
        product = Product(
            sku=svc["sku"],
            name=svc["name"],
            category="agent_service",
            description=svc["description"],
            base_price=svc["base_price"],
            tags=svc["tags"],
            stock=svc["stock"],
        )
        db.add(product)
        changed = True
    if changed:
        db.commit()


@app.get("/api/services")
def list_agent_services(db: Session = Depends(get_db)):
    """List all agent services available in the marketplace."""
    _ensure_agent_services(db)
    rows = (
        db.query(Product)
        .filter(Product.category == "agent_service")
        .order_by(Product.base_price.asc())
        .all()
    )
    # Build a quick lookup from the definition list for icon / target / unit.
    meta = {s["sku"]: s for s in _AGENT_SERVICE_DEFS}
    services = []
    for row in rows:
        m = meta.get(row.sku, {})
        services.append({
            "product_id": row.product_id,
            "sku": row.sku,
            "name": row.name,
            "description": row.description,
            "base_price": float(row.base_price),
            "tags": row.tags or "",
            "icon": m.get("icon", "🤖"),
            "target": m.get("target", "B+C"),
            "unit": m.get("unit", "次"),
            "time_saved_hours": m.get("time_saved_hours", 1.0),
            "stock": row.stock,
        })
    return {"services": services, "total": len(services)}


@app.get("/api/economy/metrics")
def economy_metrics(db: Session = Depends(get_db)):
    """Real economic metrics computed from persisted orders & transactions."""
    from app.db.models import BalanceTransaction, EvomapConsumer as _Consumer

    # Total orders (all sources).
    total_orders = db.query(func.count(Order.order_id)).scalar() or 0

    # Orders by source.
    skill_orders = (
        db.query(func.count(Order.order_id))
        .filter(Order.source_type == ORDER_SOURCE_SKILL)
        .scalar() or 0
    )
    web_orders = (
        db.query(func.count(Order.order_id))
        .filter(Order.source_type == ORDER_SOURCE_WEB_DIALOG)
        .scalar() or 0
    )

    # Total revenue (CNY face value of all paid/free orders).
    total_revenue = float(
        db.query(func.coalesce(func.sum(Order.amount), 0))
        .filter(Order.payment_status.in_([PAYMENT_STATUS_PAID, PAYMENT_STATUS_FREE]))
        .scalar() or 0
    )

    # Credits consumed (mirror of EvoMap spending).
    from app.domain_constants import WALLET_CURRENCY_CREDITS
    credits_consumed = float(
        db.query(func.coalesce(func.sum(func.abs(BalanceTransaction.amount)), 0))
        .filter(BalanceTransaction.currency == WALLET_CURRENCY_CREDITS)
        .filter(BalanceTransaction.type == "consume")
        .scalar() or 0
    )

    # Free orders count.
    free_orders = (
        db.query(func.count(Order.order_id))
        .filter(Order.payment_status == PAYMENT_STATUS_FREE)
        .scalar() or 0
    )
    paid_orders = (
        db.query(func.count(Order.order_id))
        .filter(Order.payment_status == PAYMENT_STATUS_PAID)
        .scalar() or 0
    )

    # Active agents.
    active_agents = (
        db.query(func.count(AgentProfile.agent_id))
        .filter(AgentProfile.status == IDENTITY_STATUS_ACTIVE)
        .scalar() or 0
    )

    # Unique consumers.
    unique_consumers = db.query(func.count(_Consumer.consumer_id)).scalar() or 0

    # Agent services available.
    _ensure_agent_services(db)
    service_count = (
        db.query(func.count(Product.product_id))
        .filter(Product.category == "agent_service")
        .scalar() or 0
    )

    # Estimate time saved (sum of service time_saved * assumed uptake).
    # Conservative: assume 20% of paid orders are service-type.
    estimated_hours_saved = round(paid_orders * 2.5 + skill_orders * 1.0, 1)

    # Estimated CNY value created (time_saved * ¥80/hr developer rate).
    estimated_value_cny = round(estimated_hours_saved * 80, 0)

    return {
        "total_orders": total_orders,
        "skill_orders": skill_orders,
        "web_orders": web_orders,
        "total_revenue": total_revenue,
        "credits_consumed": credits_consumed,
        "free_orders": free_orders,
        "paid_orders": paid_orders,
        "active_agents": active_agents,
        "unique_consumers": unique_consumers,
        "service_count": service_count,
        "estimated_hours_saved": estimated_hours_saved,
        "estimated_value_cny": estimated_value_cny,
        "conversion_rate": round(paid_orders / max(total_orders, 1) * 100, 1),
    }


@app.get("/api/economy/transactions")
def economy_transactions(db: Session = Depends(get_db), limit: int = 20):
    """Recent transaction stream for the economy dashboard."""
    rows = (
        db.query(Order)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .all()
    )
    items = []
    for o in rows:
        items.append({
            "order_id": o.order_id,
            "coffee_name": o.coffee_name or "—",
            "amount": float(o.amount) if o.amount else 0,
            "source_type": o.source_type,
            "payment_status": o.payment_status,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else "",
            "consumer_id": o.consumer_id,
            "agent_id": o.agent_id,
        })
    return {"transactions": items, "total": len(items)}


# ===== 商业咨询：用户与管理层 AI 私聊 =====


class ConsultRequest(BaseModel):
    """咨询请求体"""
    message: str


@app.post("/api/consult")
def consult_api(req: ConsultRequest, request: Request, db: Session = Depends(get_db)):
    """用户向管理层发送商业咨询问题，返回 AI 回复。

    需要登录。对话历史存储在独立 Redis 命名空间（consult:），
    与咖啡点单聊天历史完全隔离。
    """
    from app.auth.router import current_account
    from app.services import consult_service

    account = current_account(request, db)
    if not account:
        raise HTTPException(status_code=401, detail="请先登录后再咨询")
    result = consult_service.consult(db, account, req.message)
    return result


@app.get("/api/consult/history")
def consult_history_api(request: Request, db: Session = Depends(get_db)):
    """获取当前用户的咨询对话历史。"""
    from app.auth.router import current_account
    from app.services import consult_service

    account = current_account(request, db)
    if not account:
        raise HTTPException(status_code=401, detail="请先登录")
    history = consult_service.get_consult_history(account)
    return {"messages": history, "total": len(history)}


@app.delete("/api/consult/history")
def consult_clear_api(request: Request, db: Session = Depends(get_db)):
    """清空当前用户的咨询对话历史。"""
    from app.auth.router import current_account
    from app.services import consult_service

    account = current_account(request, db)
    if not account:
        raise HTTPException(status_code=401, detail="请先登录")
    cleared = consult_service.clear_consult_history(account)
    return {"cleared": cleared}


@app.get("/consult")
def consult_page():
    """Serve the business consultation chat page (standalone HTML)."""
    path = _STATIC_DIR / "consult.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="consult page not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/status")
def status():
    """Return system status: database backend + memory backend + LLM config."""
    return {
        "database": settings.db_mode,
        "memory": "fakeredis" if settings.use_fakeredis else "redis",
        "llm_active": llm.has_real_key(),
        "llm_key_source": settings.llm_api_key_source,
        "llm_status_reason": settings.llm_status_reason,
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
    }


@app.get("/3d")
def three_d_app():
    """Serve the 3D office SPA. Assets are under /3d/assets (Vite base ./)."""
    index_path = _3D_STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="3D build not found. Run: cd frontend && npm run build")
    return FileResponse(
        index_path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/3d/{full_path:path}")
def three_d_app_spa(full_path: str):
    """SPA fallback: any /3d/* sub-path serves index.html so client-side
    routing (/3d/scene, /3d/login, /3d/dashboard) works. Static assets under
    /3d/assets are handled by the /3d StaticFiles mount."""
    index_path = _3D_STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="3D build not found. Run: cd frontend && npm run build")
    return FileResponse(
        index_path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    """Root: 未登录 → 302 跳 /welcome（独立HTML，不依赖前端构建）；已登录 → 3D 场景。"""
    from app.auth.router import current_account

    account = current_account(request, db)
    if not account:
        return RedirectResponse(url="/welcome", status_code=302)
    # 已登录 → 直接进入 3D 场景
    return RedirectResponse(url="/3d", status_code=302)


@app.get("/welcome")
def welcome_page():
    """Standalone registration + login landing page (no frontend build needed)."""
    path = _STATIC_DIR / "welcome.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="welcome page not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/about")
def about_page():
    """Serve the Crossroads Agent Café product brochure (standalone HTML)."""
    about_path = _STATIC_DIR / "about.html"
    if not about_path.is_file():
        raise HTTPException(status_code=404, detail="about page not found")
    return FileResponse(
        about_path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/services")
def services_page():
    """Serve the Agent Services Marketplace page."""
    path = _STATIC_DIR / "services.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="services page not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/economy")
def economy_page():
    """Serve the Economic Value Dashboard page."""
    path = _STATIC_DIR / "economy.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="economy page not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )
