"""Autonomous digital customer runtime.

The 3D avatar is driven from this backend loop: sense cafe state, decide a
small plan, publish the decision, then execute visible agent actions. v1 is
intentionally non-transactional: it does not create orders, consume inventory,
touch wallets, or call EvoMap payment APIs.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import AgentProfile, Product, VisualizationEvent
from app.domain_constants import IDENTITY_STATUS_ACTIVE, PRODUCT_STATUS_AVAILABLE
from app.memory._redis_client import get_redis_client
from app.services import staff_service
from app.services.visualization_service import (
    encode_json,
    hash_agent_token,
    publish_visualization_event,
)
from app.llm import client as llm_client

AUTONOMOUS_TOOL_NAME: Final[str] = "evomap:autonomous_customer"
AUTONOMOUS_DISPLAY_NAME: Final[str] = "数字顾客"
AUTONOMOUS_SPRITE_SEED: Final[int] = 200001
AUTONOMOUS_USER_ID: Final[int] = 1
AUTONOMOUS_LOOP_LOCK_KEY: Final[str] = "coffee:autonomous:loop-lock"

_last_decision: dict[str, Any] | None = None
_next_run_after: datetime | None = None
_last_error: str | None = None
_running = False


@dataclass(slots=True)
class AutonomousProduct:
    product_id: int
    name: str
    category: str | None
    base_price: str
    stock: int
    tags: str | None = None


@dataclass(slots=True)
class AutonomousPerception:
    agent_id: int
    now: str
    available_products: list[AutonomousProduct]
    recent_event_types: list[str]
    active_agent_count: int


@dataclass(slots=True)
class AutonomousActionStep:
    action_type: str
    wait_seconds: float = 0.0
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AutonomousDecision:
    decision_id: str
    correlation_id: str
    intent: str
    reason: str
    chosen_product: str | None
    steps: list[AutonomousActionStep]
    created_at: str

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.action_type for step in self.steps]
        return data


def _now() -> datetime:
    return datetime.utcnow()


def _agent_metadata() -> dict[str, Any]:
    return {
        "source": "autonomous",
        "user_id": AUTONOMOUS_USER_ID,
        "autonomy_source": "backend_agent_runtime",
    }


def ensure_autonomous_customer_agent(
    db: Session,
    *,
    tool_name: str = AUTONOMOUS_TOOL_NAME,
    display_name: str = AUTONOMOUS_DISPLAY_NAME,
) -> AgentProfile:
    """Idempotently create/reuse the autonomous digital customer agent."""
    existing = db.query(AgentProfile).filter(AgentProfile.tool_name == tool_name).first()
    if existing:
        return existing
    agent = AgentProfile(
        tool_name=tool_name,
        display_name=display_name,
        role_type="customer",
        capabilities_json=encode_json(["autonomous_customer"]),
        metadata_json=encode_json(_agent_metadata()),
        api_token_hash=hash_agent_token("autonomous:internal"),
        sprite_seed=AUTONOMOUS_SPRITE_SEED,
        status=IDENTITY_STATUS_ACTIVE,
        created_at=_now(),
        last_seen_at=_now(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def sense(db: Session, agent: AgentProfile) -> AutonomousPerception:
    products = (
        db.query(Product)
        .filter(Product.status == PRODUCT_STATUS_AVAILABLE, Product.stock > 0)
        .order_by(Product.product_id.asc())
        .limit(12)
        .all()
    )
    recent_events = (
        db.query(VisualizationEvent.event_type)
        .order_by(VisualizationEvent.created_at.desc())
        .limit(8)
        .all()
    )
    active_cutoff = _now() - timedelta(seconds=settings.autonomous_agent_status_ttl_seconds)
    active_agent_count = (
        db.query(AgentProfile)
        .filter(
            AgentProfile.status == IDENTITY_STATUS_ACTIVE,
            AgentProfile.last_seen_at >= active_cutoff,
        )
        .count()
    )
    return AutonomousPerception(
        agent_id=agent.agent_id,
        now=_now().isoformat(),
        available_products=[
            AutonomousProduct(
                product_id=p.product_id,
                name=p.name,
                category=p.category,
                base_price=str(p.base_price),
                stock=p.stock,
                tags=p.tags,
            )
            for p in products
        ],
        recent_event_types=[row[0] for row in recent_events],
        active_agent_count=active_agent_count,
    )


# ============================================================
# LLM 驱动的行走/行为决策（2026-07-17）
# 把「数字顾客走到哪、做什么、说什么」从硬编码脚本升级为模型接管。
# 模型感知场景布局 + 今日菜单，输出一段 JSON 行为流；后端规范化后
# 逐 step 广播，前端 A* 寻路照常执行（前端只吃 action_type + 坐标）。
# 无 key / LLM 失败 / 输出不合法时降级回下方硬编码 decide()，确保
# 无模型环境也能跑。
# ============================================================

# 画布尺寸（与前端 roleMap.ts 注释一致：1800×720）。
_CANVAS_SEAT_X_MIN, _CANVAS_SEAT_X_MAX = 480, 1180
_CANVAS_SEAT_Y_MIN, _CANVAS_SEAT_Y_MAX = 300, 700
_DEFAULT_SEAT_X, _DEFAULT_SEAT_Y = 755, 580

# action 白名单：必须与前端 roleMap.ts 的 ACTION_BEHAVIOR 对齐，
# 否则前端 resolveAction 会兜底成 walk_to_table，语义错位。
_VALID_AUTONOMOUS_ACTIONS: Final[set[str]] = {
    "enter_scene",
    "walk_to_counter",
    "walk_to_table",
    "show_message",
    "take_order",
    "leave_scene",
}

AUTONOMOUS_DECIDE_PROMPT = """你是「Crossroads Agent Café」里一位由大模型驱动的自主数字顾客。请决定本次进店后的完整走路、动作与台词，让它像一位真实的咖啡馆顾客。

【场景布局】画布 1800×720 像素，左上角为原点，x 向右增、y 向下增。
- 门（入口/出口）：(60, 360)
- 吧台区（点单/收银）：x 在 0~480；吧台收银位 (350, 300)，咖啡机位 (200, 300)
- 座位区（圆桌、入座）：x 在 480~1180；常用座位 (755, 580)，圆桌之间 (755, 480)
- 休闲区（lounge）：x 在 1200~1750

【动作白名单（action 只能取以下值之一）】
- "enter_scene"：进门入场，通常作为第一步
- "walk_to_counter"：走向吧台收银位点单（无需坐标，前端自动定位到 350,300）
- "walk_to_table"：走向某个座位，必须带 x、y（座位区坐标，如 755,580）
- "show_message"：说一句话，必须带 message
- "take_order"：在吧台点单，可带 message
- "leave_scene"：走向出口离店

【今日可用菜单（只能从中点单）】
__MENU__

【输出格式】只输出一个 JSON 对象，不要任何额外文字、不要 markdown 代码围栏：
{
  "intent": "browse_menu | order_coffee | sit_and_chat | just_leave 任选其一",
  "reason": "一句话动机，20字以内",
  "chosen_product": "你点的咖啡名（从菜单选，没点单则 null）",
  "steps": [
    {"action": "enter_scene", "message": "进店随口一句"},
    {"action": "walk_to_counter"},
    {"action": "show_message", "message": "今天想喝点…"},
    {"action": "take_order", "message": "我要一杯XXX"},
    {"action": "walk_to_table", "x": 755, "y": 580},
    {"action": "show_message", "message": "坐下后的一句感想"},
    {"action": "leave_scene"}
  ]
}

【行为风格】
1. 像真实顾客，带情绪/偏好（今天想提神 / 想坐窗边 / 赶时间看一眼就走 都可以）。
2. 台词自然口语，20 字以内，可加 1 个表情。
3. steps 以 enter_scene 开头、leave_scene 结尾，4~7 步为宜。
4. walk_to_table 的坐标必须落在座位区（x:480~1180, y:300~700）。
5. 只要 take_order，chosen_product 必须是菜单里出现过的名字。
"""


def _coerce_llm_step(raw: Any) -> AutonomousActionStep | None:
    """把 LLM 输出的单个 step 规范化成 AutonomousActionStep。

    丢弃非法 action；walk_to_table 缺坐标则用默认座位，坐标裁到座位区内。
    返回 None 表示该 step 整段不可用、应由调用方过滤。
    """
    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action", "")).strip()
    if action not in _VALID_AUTONOMOUS_ACTIONS:
        return None
    message_raw = raw.get("message")
    message: str | None
    if message_raw in (None, ""):
        message = None
    else:
        message = str(message_raw).strip()[:120] or None
    payload: dict[str, Any] = {}
    if action == "walk_to_table":
        try:
            tx = float(raw.get("x", _DEFAULT_SEAT_X))
            ty = float(raw.get("y", _DEFAULT_SEAT_Y))
        except (TypeError, ValueError):
            tx, ty = float(_DEFAULT_SEAT_X), float(_DEFAULT_SEAT_Y)
        # 裁到座位区，避免 LLM 给出画布外的坐标导致前端寻路失败。
        tx = float(max(_CANVAS_SEAT_X_MIN, min(_CANVAS_SEAT_X_MAX, tx)))
        ty = float(max(_CANVAS_SEAT_Y_MIN, min(_CANVAS_SEAT_Y_MAX, ty)))
        payload = {"x": int(tx), "y": int(ty)}
    return AutonomousActionStep(action, message=message, payload=payload)


def _coerce_llm_decision(
    data: Any,
    *,
    step_interval: float,
) -> AutonomousDecision | None:
    """把 LLM 的 JSON 输出规范化成一个可执行的 AutonomousDecision。

    保证 steps 非空、以 enter_scene 开头、以 leave_scene 结尾，且每步都有
    合理的 wait_seconds（避免人偶瞬移）。任何不合法都返回 None → 走硬编码兜底。
    """
    if not isinstance(data, dict):
        return None
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None
    steps = [s for s in (_coerce_llm_step(r) for r in raw_steps) if s is not None]
    if not steps:
        return None
    # 补全进出场的 envelope（进店/离店是 3D 人偶生命周期的硬约定）。
    if steps[0].action_type != "enter_scene":
        steps.insert(0, AutonomousActionStep("enter_scene"))
    if steps[-1].action_type != "leave_scene":
        steps.append(
            AutonomousActionStep("leave_scene", wait_seconds=step_interval)
        )
    # 每步给一个最小间隔，让前端有时间播放走动动画。
    for step in steps:
        if step.wait_seconds <= 0:
            step.wait_seconds = step_interval
    decision_id = uuid.uuid4().hex
    chosen_raw = data.get("chosen_product")
    chosen = str(chosen_raw).strip() if chosen_raw not in (None, "", [], {}) else None
    return AutonomousDecision(
        decision_id=decision_id,
        correlation_id="auto-" + decision_id[:12],
        intent=str(data.get("intent") or "order_coffee")[:40],
        reason=str(data.get("reason") or "llm_decided")[:80],
        chosen_product=chosen,
        steps=steps,
        created_at=_now().isoformat(),
    )


def _llm_decide(perception: AutonomousPerception) -> AutonomousDecision | None:
    """模型驱动的行走/行为决策。返回 None 表示应降级到硬编码兜底。"""
    if not llm_client.has_real_key():
        return None
    if perception.available_products:
        menu_lines = [
            f"- {p.name}（{p.base_price}元，库存{p.stock}"
            + (f"，{p.tags}" if p.tags else "")
            + "）"
            for p in perception.available_products[:12]
        ]
        menu_text = "\n".join(menu_lines)
    else:
        menu_text = "（今日暂无可用菜单，只能 browse 或离开）"
    system_prompt = AUTONOMOUS_DECIDE_PROMPT.replace("__MENU__", menu_text)
    user_msg = (
        f"当前场景：活跃 agent 数 {perception.active_agent_count}，"
        f"最近事件类型 {perception.recent_event_types[-5:] or '无'}。"
        "\n请输出你的行为 JSON。"
    )
    try:
        raw = llm_client.chat_with_role(
            system_prompt,
            "",  # 菜单已融进 system prompt，无需额外 context
            [],  # 自主决策无历史对话
            user_msg,
            timeout_seconds=settings.llm_generation_timeout_seconds,
        )
    except Exception:
        return None
    data = llm_client.parse_json_response(raw)
    return _coerce_llm_decision(
        data, step_interval=settings.autonomous_agent_step_interval_seconds
    )


def decide(perception: AutonomousPerception) -> AutonomousDecision:
    # 有真实 LLM key 时，走路/行为/台词由模型接管。
    llm_decision = _llm_decide(perception)
    if llm_decision is not None:
        return llm_decision
    # 无 key / LLM 失败 / 输出不合法 → 硬编码兜底（保留原确定性脚本）。
    decision_id = uuid.uuid4().hex
    correlation_id = "auto-" + decision_id[:12]
    created_at = _now().isoformat()
    if not perception.available_products:
        return AutonomousDecision(
            decision_id=decision_id,
            correlation_id=correlation_id,
            intent="browse_menu",
            reason="no_available_product",
            chosen_product=None,
            created_at=created_at,
            steps=[
                AutonomousActionStep(
                    "enter_scene",
                    message="我先看看今天还有什么可以点。",
                ),
                AutonomousActionStep(
                    "show_message",
                    wait_seconds=settings.autonomous_agent_step_interval_seconds,
                    message="看起来暂时没有可点的咖啡，我下次再来。",
                ),
                AutonomousActionStep(
                    "leave_scene",
                    wait_seconds=settings.autonomous_agent_step_interval_seconds,
                ),
            ],
        )

    # Stable enough to avoid always picking the first product, deterministic enough
    # that tests can assert membership rather than an exact random branch.
    product = random.choice(perception.available_products)
    return AutonomousDecision(
        decision_id=decision_id,
        correlation_id=correlation_id,
        intent="simulate_coffee_order",
        reason="timer_triggered_with_available_menu",
        chosen_product=product.name,
        created_at=created_at,
        steps=[
            AutonomousActionStep(
                "enter_scene",
                message=f"我想试试{product.name}，去吧台看看。",
            ),
            AutonomousActionStep(
                "show_message",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
                message=f"今天想喝{product.name}。",
            ),
            AutonomousActionStep(
                "walk_to_counter",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
            ),
            AutonomousActionStep(
                "take_order",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
                message=f"模拟点单：{product.name}",
            ),
            AutonomousActionStep(
                "walk_to_table",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
                payload={"x": 230, "y": 260},
            ),
            AutonomousActionStep(
                "leave_scene",
                wait_seconds=settings.autonomous_agent_step_interval_seconds,
            ),
        ],
    )


def _decision_payload(
    decision: AutonomousDecision,
    perception: AutonomousPerception,
) -> dict[str, Any]:
    return {
        "autonomous": True,
        "autonomy_source": "backend_agent_runtime",
        "decision": decision.public_dict(),
        "perception": {
            "available_product_count": len(perception.available_products),
            "recent_event_types": perception.recent_event_types,
            "active_agent_count": perception.active_agent_count,
        },
    }


def publish_decision(
    db: Session,
    agent: AgentProfile,
    decision: AutonomousDecision,
    perception: AutonomousPerception,
) -> None:
    publish_visualization_event(
        db,
        "agent.autonomous.decision",
        _decision_payload(decision, perception),
        agent_id=agent.agent_id,
        correlation_id=decision.correlation_id,
    )


def _step_payload(
    decision: AutonomousDecision,
    step: AutonomousActionStep,
    index: int,
) -> dict[str, Any]:
    payload = {
        "autonomous": True,
        "autonomy_source": "backend_agent_runtime",
        "decision_id": decision.decision_id,
        "plan_step": index,
        "intent": decision.intent,
        "reason": decision.reason,
        "chosen_product": decision.chosen_product,
        "trigger": "timer",
        "payload": step.payload,
    }
    payload.update(step.payload)
    if step.message:
        payload["message"] = step.message
        payload["text"] = step.message
    return payload


def publish_action_step(
    db: Session,
    agent: AgentProfile,
    decision: AutonomousDecision,
    step: AutonomousActionStep,
    index: int,
) -> None:
    agent.last_seen_at = _now()
    db.commit()
    db.refresh(agent)
    staff_service.publish_agent_action(
        db,
        agent,
        step.action_type,
        correlation_id=decision.correlation_id,
        **_step_payload(decision, step, index),
    )


async def execute_decision(
    db: Session,
    agent: AgentProfile,
    decision: AutonomousDecision,
) -> None:
    for index, step in enumerate(decision.steps, start=1):
        if step.wait_seconds > 0:
            await asyncio.sleep(step.wait_seconds)
        publish_action_step(db, agent, decision, step, index)


async def run_one_cycle(
    *,
    tool_name: str = AUTONOMOUS_TOOL_NAME,
    display_name: str = AUTONOMOUS_DISPLAY_NAME,
) -> AutonomousDecision | None:
    """Run one autonomous decision/execution cycle.

    Returns None when another worker owns the short lease.
    """
    global _last_decision, _last_error, _running
    if not _acquire_loop_lease():
        return None
    _running = True
    db = SessionLocal()
    try:
        agent = ensure_autonomous_customer_agent(
            db, tool_name=tool_name, display_name=display_name
        )
        perception = sense(db, agent)
        # LLM 决策可能阻塞数秒（推理模型），放线程池跑避免卡住 asyncio 事件循环
        # （WS 广播、presence 心跳等协程都依赖事件循环不能被阻塞）。
        decision = await asyncio.to_thread(decide, perception)
        publish_decision(db, agent, decision, perception)
        await execute_decision(db, agent, decision)
        _last_decision = decision.public_dict()
        _last_error = None
        return decision
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _last_error = exc.__class__.__name__
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()
        _running = False


def _acquire_loop_lease() -> bool:
    if settings.use_fakeredis:
        return True
    try:
        client = get_redis_client(decode_responses=True)
        return bool(
            client.set(
                AUTONOMOUS_LOOP_LOCK_KEY,
                uuid.uuid4().hex,
                nx=True,
                ex=max(30, int(settings.autonomous_agent_step_interval_seconds * 10)),
            )
        )
    except Exception:
        return True


def _next_interval_seconds() -> float:
    return random.uniform(
        settings.autonomous_agent_interval_min_seconds,
        settings.autonomous_agent_interval_max_seconds,
    )


async def autonomous_loop() -> None:
    """Background loop: one autonomous session every configured interval."""
    global _next_run_after
    while True:
        try:
            await run_one_cycle()
        except asyncio.CancelledError:
            raise
        interval = _next_interval_seconds()
        _next_run_after = _now() + timedelta(seconds=interval)
        await asyncio.sleep(interval)


def status_snapshot(db: Session) -> dict[str, Any]:
    agent = (
        db.query(AgentProfile)
        .filter(AgentProfile.tool_name == AUTONOMOUS_TOOL_NAME)
        .first()
    )
    return {
        "enabled": settings.autonomous_agent_enabled,
        "running": _running,
        "agent_id": agent.agent_id if agent else None,
        "display_name": agent.display_name if agent else AUTONOMOUS_DISPLAY_NAME,
        "last_seen_at": agent.last_seen_at.isoformat() if agent else None,
        "last_decision": _last_decision,
        "next_run_after": _next_run_after.isoformat() if _next_run_after else None,
        "last_error": _last_error,
    }


def reset_runtime_state_for_tests() -> None:
    global _last_decision, _next_run_after, _last_error, _running
    _last_decision = None
    _next_run_after = None
    _last_error = None
    _running = False
