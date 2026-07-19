from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    AgentProfile,
    EvomapConsumer,
    Order,
    OrderItem,
    SkillOrderLedger,
    User,
)
from app.domain_constants import (
    IDENTITY_STATUS_ACTIVE,
    ORDER_SOURCE_SKILL,
    ORDER_STATUS_PAID,
    PAYMENT_STATUS_FREE,
    PAYMENT_STATUS_NEEDS_RECONCILE,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PAYMENT_FAILED,
    PAYMENT_STATUS_PAYMENT_PROCESSING,
    PAYMENT_STATUS_PAYMENT_PENDING,
    PAYMENT_STATUS_PAYMENT_REQUIRED,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_RECONCILING,
    PRODUCT_STATUS_AVAILABLE,
    STOCK_RESERVATION_CONSUMED,
    STOCK_RESERVATION_RELEASED,
    STOCK_RESERVATION_RESERVING,
    STOCK_RESERVATION_RESERVED,
)
from app.llm import client as llm
from app.rag.keywords import extract_keywords
from app.rag.retrieval import retrieve
from app.services.chat_service import extract_price, match_by_price
from app.services.order_service import (
    InsufficientBalanceError,
    OrderError,
    place_orders,
)
from app.services.evomap_payment_service import (
    EvomapPaymentError,
    build_service_order_request,
    credits_for_order,
    place_service_order,
)
from app.services.visualization_service import (
    broadcast_visualization_message,
    decode_json,
    encode_json,
    publish_visualization_event as publish_persisted_visualization_event,
    publish_visualization_events as publish_persisted_visualization_events,
)
from app.db.models import Product
from app.domain_constants import WALLET_CURRENCY_CREDITS
from app.domain_constants import WALLET_CURRENCY_CNY
from app.services import wallet_service
from app.services.catalog_service import (
    AmbiguousProductError,
    CatalogError,
    OutOfStockError,
    decrement_stock,
    get_product_by_name,
    restore_stock,
)
from app.services.staff_service import (
    customer_enter_scene,
    ensure_staff_agents,
    orchestrate_staff_node,
)

logger = logging.getLogger(__name__)


class SkillOrderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_order_error",
        http_status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class SkillPaymentRequired(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__("EvoMap payment required")
        self.payload = payload


def publish_visualization_event(
    db: Session,
    event_type: str,
    payload: dict[str, Any],
    *,
    agent_id: int | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    return publish_persisted_visualization_event(
        db,
        event_type=event_type,
        payload=payload,
        agent_id=agent_id,
        correlation_id=correlation_id,
    )


def try_publish_visualization_event(
    db: Session,
    event_type: str,
    payload: dict[str, Any],
    *,
    agent_id: int | None = None,
    correlation_id: str | None = None,
) -> None:
    try:
        publish_visualization_event(
            db,
            event_type,
            payload,
            agent_id=agent_id,
            correlation_id=correlation_id,
        )
    except Exception:
        db.rollback()
        broadcast_visualization_message(
            {
                "event_id": None,
                "type": event_type,
                "agent_id": agent_id,
                "payload": payload,
                "correlation_id": correlation_id,
                "created_at": datetime.utcnow().isoformat(),
            },
            replay=True,
        )


def try_publish_visualization_events(db: Session, events: list[dict[str, Any]]) -> None:
    try:
        publish_persisted_visualization_events(db, events)
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
                    "created_at": datetime.utcnow().isoformat(),
                },
                replay=True,
            )


def _skill_restaurant_payload(
    consumer: EvomapConsumer,
    *,
    state: str,
    items: list[dict[str, Any]] | None = None,
    coffee_names: list[str] | None = None,
    total: Decimal | float | None = None,
    amount_credits: int | None = None,
    payment_status: str | None = None,
    order_ids: list[int] | None = None,
    ledger: SkillOrderLedger | None = None,
    message: str | None = None,
    reason: str | None = None,
    stage: str | None = None,
    free_order_sequence: int | None = None,
    evomap_order_id: str | None = None,
    patience: int | None = None,
    satisfaction: int | None = None,
) -> dict[str, Any]:
    public_items = _public_items(items) if items is not None else []
    names = coffee_names or [item["name"] for item in public_items]
    if total is None and items is not None:
        total = sum((Decimal(str(item["price"])) for item in items), Decimal("0.00"))
    return {
        "version": 1,
        "state": state,
        "source_type": ORDER_SOURCE_SKILL,
        "customer": {
            "kind": "evomap",
            "consumer_id": consumer.consumer_id,
            "display_name": consumer.display_name,
            "evomap_node_id": consumer.evomap_node_id,
        },
        "consumer_id": consumer.consumer_id,
        "evomap_node_id": consumer.evomap_node_id,
        "coffees": public_items,
        "coffee_names": names,
        "total": float(total) if total is not None else None,
        "amount_credits": amount_credits,
        "payment_status": payment_status,
        "order_ids": order_ids or [],
        "ledger_id": ledger.ledger_id if ledger else None,
        "free_order_sequence": free_order_sequence,
        "evomap_order_id": evomap_order_id,
        "message": message,
        "reason": reason,
        "stage": stage,
        "patience": patience,
        "satisfaction": satisfaction,
    }


def _skill_restaurant_event_record(
    event_type: str,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    correlation_id: str,
    state: str,
    items: list[dict[str, Any]] | None = None,
    coffee_names: list[str] | None = None,
    total: Decimal | float | None = None,
    amount_credits: int | None = None,
    payment_status: str | None = None,
    order_ids: list[int] | None = None,
    ledger: SkillOrderLedger | None = None,
    message: str | None = None,
    reason: str | None = None,
    stage: str | None = None,
    free_order_sequence: int | None = None,
    evomap_order_id: str | None = None,
    patience: int | None = None,
    satisfaction: int | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "payload": _skill_restaurant_payload(
            consumer,
            state=state,
            items=items,
            coffee_names=coffee_names,
            total=total,
            amount_credits=amount_credits,
            payment_status=payment_status,
            order_ids=order_ids,
            ledger=ledger,
            message=message,
            reason=reason,
            stage=stage,
            free_order_sequence=free_order_sequence,
            evomap_order_id=evomap_order_id,
            patience=patience,
            satisfaction=satisfaction,
        ),
        "agent_id": agent.agent_id,
        "correlation_id": correlation_id,
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


def _publish_skill_restaurant_event(
    db: Session,
    event_type: str,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    correlation_id: str,
    state: str,
    items: list[dict[str, Any]] | None = None,
    coffee_names: list[str] | None = None,
    total: Decimal | float | None = None,
    amount_credits: int | None = None,
    payment_status: str | None = None,
    order_ids: list[int] | None = None,
    ledger: SkillOrderLedger | None = None,
    message: str | None = None,
    reason: str | None = None,
    stage: str | None = None,
    free_order_sequence: int | None = None,
    evomap_order_id: str | None = None,
    patience: int | None = None,
    satisfaction: int | None = None,
) -> None:
    try_publish_visualization_event(
        db,
        event_type,
        _skill_restaurant_payload(
            consumer,
            state=state,
            items=items,
            coffee_names=coffee_names,
            total=total,
            amount_credits=amount_credits,
            payment_status=payment_status,
            order_ids=order_ids,
            ledger=ledger,
            message=message,
            reason=reason,
            stage=stage,
            free_order_sequence=free_order_sequence,
            evomap_order_id=evomap_order_id,
            patience=patience,
            satisfaction=satisfaction,
        ),
        agent_id=agent.agent_id,
        correlation_id=correlation_id,
    )


def _publish_skill_completion_flow(
    db: Session,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    ledger: SkillOrderLedger,
    orders: list[Order],
    items: list[dict[str, Any]],
    payment_status: str,
    free_order_sequence: int | None,
) -> None:
    order_ids = [order.order_id for order in orders]
    coffee_names = [order.coffee_name for order in orders]
    total = sum((order.amount for order in orders), Decimal("0.00"))
    common = {
        "consumer": consumer,
        "agent": agent,
        "correlation_id": ledger.request_id,
        "items": items,
        "coffee_names": coffee_names,
        "total": total,
        "amount_credits": ledger.amount_credits,
        "payment_status": payment_status,
        "order_ids": order_ids,
        "ledger": ledger,
        "free_order_sequence": free_order_sequence,
        "evomap_order_id": ledger.evomap_order_id,
    }
    try:
        staff = ensure_staff_agents(db)
    except Exception:
        staff = {}
    correlation = ledger.request_id
    events: list[dict[str, Any]] = []
    events.append(_skill_restaurant_event_record(
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
        events.append(_skill_restaurant_event_record(
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
    events.append(_skill_restaurant_event_record(
        "restaurant.order_ready",
        state="ready",
        patience=70,
        satisfaction=92,
        **common,
    ))
    staff_event = _staff_action_event_record(staff, "barista", "enter_scene", correlation)
    if staff_event:
        events.append(staff_event)
    events.append(_skill_restaurant_event_record(
        "restaurant.order_delivered",
        state="delivered",
        patience=74,
        satisfaction=94,
        **common,
    ))
    staff_event = _staff_action_event_record(staff, "waiter", "deliver_order", correlation)
    if staff_event:
        events.append(staff_event)
    events.append(_skill_restaurant_event_record(
        "restaurant.customer_reviewed",
        state="reviewed",
        message="顾客评价：出餐顺利",
        patience=76,
        satisfaction=96,
        **common,
    ))
    events.append(_skill_restaurant_event_record(
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
    try_publish_visualization_events(db, events)


def ensure_consumer(
    db: Session,
    *,
    evomap_node_id: str,
    display_name: str,
    evomap_did: str | None = None,
) -> EvomapConsumer:
    node_id = evomap_node_id.strip()
    if not node_id:
        raise SkillOrderError("缺少 EvoMap node_id", code="missing_evomap_node_id")

    consumer = (
        db.query(EvomapConsumer)
        .filter(EvomapConsumer.evomap_node_id == node_id)
        .first()
    )
    if consumer is None:
        user = User(
            nickname=display_name.strip() or node_id,
            balance=Decimal("0.00"),
            taste_preference="EvoMap 积分用户",
        )
        db.add(user)
        db.flush()
        consumer = EvomapConsumer(
            evomap_node_id=node_id,
            evomap_did=evomap_did,
            display_name=display_name.strip() or node_id,
            local_user_id=user.user_id,
            free_orders_used=0,
            status=IDENTITY_STATUS_ACTIVE,
            created_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(consumer)
    else:
        consumer.display_name = display_name.strip() or consumer.display_name
        consumer.evomap_did = evomap_did or consumer.evomap_did
        consumer.last_seen_at = datetime.utcnow()
        if consumer.local_user_id is None:
            user = User(
                nickname=consumer.display_name,
                balance=Decimal("0.00"),
                taste_preference="EvoMap 积分用户",
            )
            db.add(user)
            db.flush()
            consumer.local_user_id = user.user_id
    db.commit()
    db.refresh(consumer)
    return consumer


def _reserve_free_order_slot(
    db: Session,
    consumer: EvomapConsumer,
) -> int | None:
    """Atomically reserve one free-order slot inside the order transaction.

    The update is intentionally not committed here: the quota increment, stock
    decrement, order rows, and wallet mirror are committed together by
    ``_complete_order``. A failure rolls all of them back, so a transient error
    cannot consume a user's free quota without creating an order.
    """
    limit = max(int(settings.skill_free_order_limit), 0)
    if limit == 0:
        return None

    result = db.execute(
        update(EvomapConsumer)
        .where(
            EvomapConsumer.consumer_id == consumer.consumer_id,
            EvomapConsumer.free_orders_used < limit,
        )
        .values(
            free_orders_used=EvomapConsumer.free_orders_used + 1,
            last_seen_at=datetime.utcnow(),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        db.refresh(consumer)
        return None

    db.refresh(consumer)
    return int(consumer.free_orders_used)


def _claim_payment_attempt(
    db: Session,
    ledger: SkillOrderLedger,
) -> tuple[SkillOrderLedger, bool]:
    """Claim the right to make the external EvoMap payment exactly once.

    A conditional UPDATE is used instead of a Python-side status check so it is
    safe on both MySQL and SQLite. A stuck ``payment_processing`` claim may be
    reclaimed only after the configured timeout; an active claim causes the
    concurrent request to return a retryable conflict instead of double-paying.
    """
    now = datetime.utcnow()
    timeout_seconds = max(
        int(getattr(settings, "skill_payment_processing_timeout_seconds", 120)),
        30,
    )
    stale_before = now - timedelta(seconds=timeout_seconds)
    claim_values = {
        "payment_status": PAYMENT_STATUS_PAYMENT_PROCESSING,
        "payment_attempts": func.coalesce(SkillOrderLedger.payment_attempts, 0) + 1,
        "version": func.coalesce(SkillOrderLedger.version, 0) + 1,
        "updated_at": now,
    }

    result = db.execute(
        update(SkillOrderLedger)
        .where(
            SkillOrderLedger.ledger_id == ledger.ledger_id,
            SkillOrderLedger.payment_status.in_(
                {
                    PAYMENT_STATUS_PAYMENT_REQUIRED,
                    PAYMENT_STATUS_PAYMENT_FAILED,
                    PAYMENT_STATUS_PAYMENT_PENDING,
                }
            ),
        )
        .values(**claim_values)
    )
    if result.rowcount != 1:
        result = db.execute(
            update(SkillOrderLedger)
            .where(
                SkillOrderLedger.ledger_id == ledger.ledger_id,
                SkillOrderLedger.payment_status == PAYMENT_STATUS_PAYMENT_PROCESSING,
                or_(
                    SkillOrderLedger.updated_at.is_(None),
                    SkillOrderLedger.updated_at <= stale_before,
                ),
            )
            .values(**claim_values)
        )

    claimed = result.rowcount == 1
    if claimed:
        # Commit the claim before making a non-transactional external payment.
        db.commit()
    else:
        db.rollback()

    current = db.get(SkillOrderLedger, ledger.ledger_id)
    if current is None:
        raise SkillOrderError(
            "订单账本不存在",
            code="ledger_not_found",
            http_status=404,
        )
    return current, claimed


def _require_payment_claim(
    consumer: EvomapConsumer,
    ledger: SkillOrderLedger,
    claimed: bool,
) -> dict[str, Any] | None:
    """Translate a lost payment claim into an idempotent result or safe error."""
    if claimed:
        return None
    if ledger.payment_status in {PAYMENT_STATUS_FREE, PAYMENT_STATUS_PAID}:
        return _success_response(consumer, ledger, "幂等重试：订单已完成")
    if ledger.payment_status == PAYMENT_STATUS_PAYMENT_PROCESSING:
        raise SkillOrderError(
            "该订单正在支付处理中，请稍后使用相同 request_id 查询结果",
            code="payment_processing",
            http_status=409,
        )
    if ledger.payment_status == PAYMENT_STATUS_NEEDS_RECONCILE:
        raise SkillOrderError(
            "该订单已扣款但本地落单待对账，请勿重复支付",
            code="payment_reconcile_required",
            http_status=409,
        )
    raise SkillOrderError(
        "未能取得支付处理权，请稍后重试",
        code="payment_claim_conflict",
        http_status=409,
    )


def _assert_items_available(db: Session, items: list[dict[str, Any]]) -> None:
    """Best-effort stock preflight before an irreversible external payment."""
    required: dict[str, int] = {}
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            raise CatalogError("订单商品名称为空")
        required[name] = required.get(name, 0) + 1

    products = {
        product.name: product
        for product in db.query(Product).filter(Product.name.in_(required)).all()
    }
    for name, quantity in required.items():
        product = products.get(name)
        if product is None:
            raise CatalogError(f"商品不存在：{name}")
        if product.status != PRODUCT_STATUS_AVAILABLE:
            raise OutOfStockError(f"{name} 当前不可售")
        if product.stock is None or product.stock < quantity:
            raise OutOfStockError(
                f"{name} 库存不足：剩余 {product.stock or 0}，需要 {quantity}"
            )


def _stock_reservation_entries(ledger: SkillOrderLedger) -> list[dict[str, Any]]:
    entries = decode_json(ledger.stock_reservation_json, [])
    return entries if isinstance(entries, list) else []


def _reserve_stock_for_ledger(
    db: Session,
    ledger: SkillOrderLedger,
    items: list[dict[str, Any]],
) -> None:
    """Commit stock before the irreversible external credit payment."""
    if ledger.stock_reservation_status in {
        STOCK_RESERVATION_RESERVED,
        STOCK_RESERVATION_CONSUMED,
    }:
        return
    now = datetime.utcnow()
    stale_before = now - timedelta(
        seconds=max(
            int(getattr(settings, "skill_reconcile_claim_timeout_seconds", 300)),
            60,
        )
    )
    claim = db.execute(
        update(SkillOrderLedger)
        .where(
            SkillOrderLedger.ledger_id == ledger.ledger_id,
            or_(
                SkillOrderLedger.stock_reservation_status.is_(None),
                SkillOrderLedger.stock_reservation_status == STOCK_RESERVATION_RELEASED,
                (
                    (SkillOrderLedger.stock_reservation_status == STOCK_RESERVATION_RESERVING)
                    & or_(
                        SkillOrderLedger.updated_at.is_(None),
                        SkillOrderLedger.updated_at <= stale_before,
                    )
                ),
            ),
        )
        .values(
            stock_reservation_status=STOCK_RESERVATION_RESERVING,
            version=func.coalesce(SkillOrderLedger.version, 0) + 1,
            updated_at=now,
        )
    )
    if claim.rowcount != 1:
        db.rollback()
        current = db.get(SkillOrderLedger, ledger.ledger_id)
        if current is not None and current.stock_reservation_status in {
            STOCK_RESERVATION_RESERVED,
            STOCK_RESERVATION_CONSUMED,
        }:
            ledger.stock_reservation_json = current.stock_reservation_json
            ledger.stock_reservation_status = current.stock_reservation_status
            return
        raise SkillOrderError(
            "该订单正在预留库存，请稍后使用相同 request_id 重试",
            code="stock_reservation_processing",
            http_status=409,
        )
    db.commit()
    ledger = db.get(SkillOrderLedger, ledger.ledger_id)
    if ledger is None:
        raise SkillOrderError("订单账本不存在", code="ledger_not_found", http_status=404)

    required: dict[str, int] = {}
    for item in items:
        name = str(item["name"])
        required[name] = required.get(name, 0) + 1

    products = {
        product.name: product
        for product in db.query(Product).filter(Product.name.in_(required)).all()
    }
    entries: list[dict[str, Any]] = []
    try:
        _assert_items_available(db, items)
        for name, quantity in required.items():
            product = products.get(name)
            if product is None:
                raise CatalogError(f"商品不存在：{name}")
            decrement_stock(db, product.product_id, quantity)
            entries.append(
                {
                    "product_id": product.product_id,
                    "name": name,
                    "quantity": quantity,
                }
            )
        ledger.stock_reservation_json = encode_json(entries)
        ledger.stock_reservation_status = STOCK_RESERVATION_RESERVED
        ledger.updated_at = datetime.utcnow()
        db.add(ledger)
        db.commit()
        db.refresh(ledger)
    except Exception:
        db.rollback()
        current = db.get(SkillOrderLedger, ledger.ledger_id)
        if current is not None:
            current.stock_reservation_status = STOCK_RESERVATION_RELEASED
            current.updated_at = datetime.utcnow()
            db.commit()
        raise


def _release_stock_reservation(
    db: Session,
    ledger: SkillOrderLedger,
) -> None:
    """Return a committed reservation after an external payment failure."""
    if ledger.stock_reservation_status != STOCK_RESERVATION_RESERVED:
        return
    for entry in _stock_reservation_entries(ledger):
        product_id = entry.get("product_id")
        quantity = int(entry.get("quantity") or 0)
        if product_id is not None and quantity > 0:
            restore_stock(db, int(product_id), quantity)
    ledger.stock_reservation_status = STOCK_RESERVATION_RELEASED
    ledger.updated_at = datetime.utcnow()


def process_skill_order(
    db: Session,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    message: str,
    request_id: str | None,
    evomap_node_secret: str | None = None,
    payment_proof: dict[str, Any] | None,
) -> dict[str, Any]:
    correlation_id = request_id or f"skill-{consumer.consumer_id}-{uuid.uuid4().hex}"
    # 让顾客人偶实时进入已连接的 3D 客户端（best-effort，绝不阻断点单业务）。
    customer_enter_scene(db, agent, correlation_id=correlation_id)
    _publish_skill_restaurant_event(
        db,
        "restaurant.customer_entered",
        consumer=consumer,
        agent=agent,
        correlation_id=correlation_id,
        state="entered",
        message=message,
        patience=100,
        satisfaction=80,
    )
    try_publish_visualization_event(
        db,
        "message.received",
        {
                "consumer_id": consumer.consumer_id,
                "evomap_node_id": consumer.evomap_node_id,
                "message": message,
                "source_type": ORDER_SOURCE_SKILL,
            },
        agent_id=agent.agent_id,
        correlation_id=correlation_id,
    )

    existing = (
        db.query(SkillOrderLedger)
        .filter(SkillOrderLedger.request_id == correlation_id)
        .first()
    )
    if existing:
        if (
            existing.consumer_id != consumer.consumer_id
            or existing.agent_id != agent.agent_id
        ):
            raise SkillOrderError(
                "request_id 已被其他 EvoMap 消费者或 Agent 使用",
                code="request_id_conflict",
                http_status=409,
            )
        return _resume_existing_order(
            db,
            consumer=consumer,
            agent=agent,
            ledger=existing,
            evomap_node_secret=evomap_node_secret,
            payment_proof=payment_proof,
        )

    items = _resolve_items(db, message)
    if not items:
        _publish_skill_restaurant_event(
            db,
            "restaurant.order_failed",
            consumer=consumer,
            agent=agent,
            correlation_id=correlation_id,
            state="failed",
            message=message,
            reason="coffee_not_resolved",
            stage="skill_resolve",
            patience=45,
            satisfaction=32,
        )
        try_publish_visualization_event(
            db,
            "order.failed",
            {
                "consumer_id": consumer.consumer_id,
                "evomap_node_id": consumer.evomap_node_id,
                "reason": "coffee_not_resolved",
                "stage": "skill_resolve",
                "source_type": ORDER_SOURCE_SKILL,
            },
            agent_id=agent.agent_id,
            correlation_id=correlation_id,
        )
        raise SkillOrderError("未能从 Skill 点单消息中识别咖啡", code="coffee_not_resolved")

    amount = sum((item["price"] for item in items), Decimal("0.00"))
    amount_credits = credits_for_order(amount)
    provisional_free_sequence = consumer.free_orders_used + 1
    is_free = provisional_free_sequence <= settings.skill_free_order_limit

    _publish_skill_restaurant_event(
        db,
        "restaurant.order_ticketed",
        consumer=consumer,
        agent=agent,
        correlation_id=correlation_id,
        state="ordering",
        items=items,
        amount_credits=amount_credits,
        payment_status=PAYMENT_STATUS_FREE if is_free else PAYMENT_STATUS_PAYMENT_PENDING,
        free_order_sequence=provisional_free_sequence if is_free else None,
        patience=92,
        satisfaction=84,
    )
    try_publish_visualization_event(
        db,
        "order.intent_detected",
        {
            "consumer_id": consumer.consumer_id,
            "evomap_node_id": consumer.evomap_node_id,
            "intent": "skill_order",
            "coffees": _public_items(items),
            "amount_credits": amount_credits,
            "source_type": ORDER_SOURCE_SKILL,
        },
        agent_id=agent.agent_id,
        correlation_id=correlation_id,
    )
    try:
        _staff = ensure_staff_agents(db)
    except Exception:
        _staff = {}
    orchestrate_staff_node(db, _staff, "intent_detected", correlation_id)

    ledger = SkillOrderLedger(
        consumer_id=consumer.consumer_id,
        agent_id=agent.agent_id,
        request_id=correlation_id,
        coffee_items_json=encode_json(_public_items(items)),
        amount_credits=amount_credits,
        payment_status=PAYMENT_STATUS_PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    free_sequence = _reserve_free_order_slot(db, consumer)
    if free_sequence is not None:
        try:
            return _complete_order(
                db,
                consumer=consumer,
                agent=agent,
                ledger=ledger,
                items=items,
                payment_status=PAYMENT_STATUS_FREE,
                free_order_sequence=free_sequence,
                payment_proof=None,
            )
        except OutOfStockError as exc:
            db.rollback()
            raise SkillOrderError(
                str(exc), code="out_of_stock", http_status=409
            ) from exc
        except CatalogError as exc:
            db.rollback()
            raise SkillOrderError(
                str(exc), code="product_unavailable", http_status=409
            ) from exc
        except IntegrityError as exc:
            db.rollback()
            concurrent = (
                db.query(SkillOrderLedger)
                .filter(SkillOrderLedger.request_id == correlation_id)
                .first()
            )
            if concurrent and concurrent.consumer_id == consumer.consumer_id:
                return _resume_existing_order(
                    db,
                    consumer=consumer,
                    agent=agent,
                    ledger=concurrent,
                    evomap_node_secret=evomap_node_secret,
                    payment_proof=payment_proof,
                )
            raise SkillOrderError(
                "免费额度或幂等键发生并发冲突，请使用相同 request_id 重试",
                code="quota_race_retry",
                http_status=409,
            ) from exc

    ledger.payment_status = PAYMENT_STATUS_PAYMENT_PENDING
    db.add(ledger)
    db.commit()
    db.refresh(ledger)

    if payment_proof:
        _reject_unverified_payment_proof(
            db,
            consumer=consumer,
            agent=agent,
            ledger=ledger,
            items=items,
        )

    if not evomap_node_secret:
        ledger.payment_status = PAYMENT_STATUS_PAYMENT_REQUIRED
        ledger.updated_at = datetime.utcnow()
        db.commit()
        payload = _payment_required_payload(consumer, ledger, items)
        _publish_skill_restaurant_event(
            db,
            "restaurant.payment_requested",
            consumer=consumer,
            agent=agent,
            correlation_id=ledger.request_id,
            state="payment_required",
            items=items,
            amount_credits=ledger.amount_credits,
            payment_status=PAYMENT_STATUS_PAYMENT_REQUIRED,
            ledger=ledger,
            patience=68,
            satisfaction=72,
        )
        try_publish_visualization_event(
            db,
            "order.payment_required",
            payload,
            agent_id=agent.agent_id,
            correlation_id=ledger.request_id,
        )
        raise SkillPaymentRequired(payload)

    try:
        _reserve_stock_for_ledger(db, ledger, items)
    except OutOfStockError as exc:
        ledger.payment_status = PAYMENT_STATUS_PAYMENT_FAILED
        ledger.updated_at = datetime.utcnow()
        db.commit()
        raise SkillOrderError(str(exc), code="out_of_stock", http_status=409) from exc
    except CatalogError as exc:
        ledger.payment_status = PAYMENT_STATUS_PAYMENT_FAILED
        ledger.updated_at = datetime.utcnow()
        db.commit()
        raise SkillOrderError(
            str(exc), code="product_unavailable", http_status=409
        ) from exc

    ledger, claimed = _claim_payment_attempt(db, ledger)
    completed = _require_payment_claim(consumer, ledger, claimed)
    if completed is not None:
        return completed
    return _charge_evomap_and_complete(
        db,
        consumer=consumer,
        agent=agent,
        ledger=ledger,
        items=items,
        evomap_node_secret=evomap_node_secret,
    )


def _resume_existing_order(
    db: Session,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    ledger: SkillOrderLedger,
    evomap_node_secret: str | None,
    payment_proof: dict[str, Any] | None,
) -> dict[str, Any]:
    items = _ledger_items(ledger)
    if ledger.payment_status in {PAYMENT_STATUS_FREE, PAYMENT_STATUS_PAID}:
        return _success_response(consumer, ledger, "幂等重试：订单已完成")
    if ledger.payment_status in {
        PAYMENT_STATUS_NEEDS_RECONCILE,
        PAYMENT_STATUS_RECONCILING,
    }:
        raise SkillOrderError(
            "该订单已完成外部扣款，正在等待本地对账，请勿重复支付",
            code="payment_reconcile_required",
            http_status=409,
        )

    if ledger.payment_status in {
        PAYMENT_STATUS_PAYMENT_REQUIRED,
        PAYMENT_STATUS_PAYMENT_FAILED,
        PAYMENT_STATUS_PAYMENT_PENDING,
        PAYMENT_STATUS_PAYMENT_PROCESSING,
    }:
        if payment_proof:
            _reject_unverified_payment_proof(
                db,
                consumer=consumer,
                agent=agent,
                ledger=ledger,
                items=[_private_item(item) for item in items],
            )
        if not evomap_node_secret:
            if ledger.payment_status == PAYMENT_STATUS_PAYMENT_PROCESSING:
                raise SkillOrderError(
                    "该订单正在支付处理中，请稍后使用相同 request_id 查询结果",
                    code="payment_processing",
                    http_status=409,
                )
            payload = _payment_required_payload(consumer, ledger, items)
            _publish_skill_restaurant_event(
                db,
                "restaurant.payment_requested",
                consumer=consumer,
                agent=agent,
                correlation_id=ledger.request_id,
                state="payment_required",
                items=[_private_item(item) for item in items],
                amount_credits=ledger.amount_credits,
                payment_status=PAYMENT_STATUS_PAYMENT_REQUIRED,
                ledger=ledger,
                patience=62,
                satisfaction=70,
            )
            try_publish_visualization_event(
                db,
                "order.payment_required",
                payload,
                agent_id=agent.agent_id,
                correlation_id=ledger.request_id,
            )
            raise SkillPaymentRequired(payload)
        private_items = [_private_item(item) for item in items]
        try:
            _reserve_stock_for_ledger(db, ledger, private_items)
        except OutOfStockError as exc:
            ledger.payment_status = PAYMENT_STATUS_PAYMENT_FAILED
            ledger.updated_at = datetime.utcnow()
            db.commit()
            raise SkillOrderError(
                str(exc), code="out_of_stock", http_status=409
            ) from exc
        except CatalogError as exc:
            ledger.payment_status = PAYMENT_STATUS_PAYMENT_FAILED
            ledger.updated_at = datetime.utcnow()
            db.commit()
            raise SkillOrderError(
                str(exc), code="product_unavailable", http_status=409
            ) from exc

        ledger, claimed = _claim_payment_attempt(db, ledger)
        completed = _require_payment_claim(consumer, ledger, claimed)
        if completed is not None:
            return completed
        return _charge_evomap_and_complete(
            db,
            consumer=consumer,
            agent=agent,
            ledger=ledger,
            items=private_items,
            evomap_node_secret=evomap_node_secret,
        )

    raise SkillOrderError("订单账本状态不可恢复", code="ledger_not_resumable")


def _charge_evomap_and_complete(
    db: Session,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    ledger: SkillOrderLedger,
    items: list[dict[str, Any]],
    evomap_node_secret: str,
) -> dict[str, Any]:
    coffee_names = [item["name"] for item in items]
    _publish_skill_restaurant_event(
        db,
        "restaurant.payment_processing",
        consumer=consumer,
        agent=agent,
        correlation_id=ledger.request_id,
        state="payment_processing",
        items=items,
        coffee_names=coffee_names,
        amount_credits=ledger.amount_credits,
        payment_status=PAYMENT_STATUS_PAYMENT_PROCESSING,
        ledger=ledger,
        patience=70,
        satisfaction=76,
    )
    try:
        payment_proof = place_service_order(
            request_id=ledger.request_id,
            consumer_node_id=consumer.evomap_node_id,
            node_secret=evomap_node_secret,
            coffee_names=coffee_names,
            amount_credits=ledger.amount_credits,
        )
    except EvomapPaymentError as exc:
        ledger.payment_status = PAYMENT_STATUS_PAYMENT_FAILED
        ledger.payment_proof_json = encode_json(
            {
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            }
        )
        ledger.updated_at = datetime.utcnow()
        _release_stock_reservation(db, ledger)
        db.add(ledger)
        db.commit()
        _publish_skill_restaurant_event(
            db,
            "restaurant.payment_failed",
            consumer=consumer,
            agent=agent,
            correlation_id=ledger.request_id,
            state="failed",
            items=items,
            coffee_names=coffee_names,
            amount_credits=ledger.amount_credits,
            payment_status=PAYMENT_STATUS_PAYMENT_FAILED,
            ledger=ledger,
            reason=str(exc),
            stage="evomap_payment",
            patience=28,
            satisfaction=35,
        )
        _publish_skill_restaurant_event(
            db,
            "restaurant.order_failed",
            consumer=consumer,
            agent=agent,
            correlation_id=ledger.request_id,
            state="failed",
            items=items,
            coffee_names=coffee_names,
            amount_credits=ledger.amount_credits,
            payment_status=PAYMENT_STATUS_PAYMENT_FAILED,
            ledger=ledger,
            reason=str(exc),
            stage="skill_order",
            patience=24,
            satisfaction=30,
        )
        try_publish_visualization_event(
            db,
            "order.payment_failed",
            {
                "consumer_id": consumer.consumer_id,
                "evomap_node_id": consumer.evomap_node_id,
                "amount_credits": ledger.amount_credits,
                "code": exc.code,
                "reason": str(exc),
                "source_type": ORDER_SOURCE_SKILL,
            },
            agent_id=agent.agent_id,
            correlation_id=ledger.request_id,
        )
        raise SkillOrderError(str(exc), code=exc.code, http_status=exc.http_status) from exc

    try:
        return _complete_order(
            db,
            consumer=consumer,
            agent=agent,
            ledger=ledger,
            items=items,
            payment_status=PAYMENT_STATUS_PAID,
            free_order_sequence=None,
            payment_proof=payment_proof,
        )
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            logger.exception("支付对账回滚失败 consumer_id=%s", consumer.consumer_id)
        try:
            ledger.payment_status = PAYMENT_STATUS_NEEDS_RECONCILE
            ledger.payment_proof_json = encode_json(payment_proof)
            ledger.evomap_order_id = payment_proof.get("evomap_order_id")
            ledger.updated_at = datetime.utcnow()
            db.add(ledger)
            db.commit()
        except Exception:
            logger.exception("标记 NEEDS_RECONCILE 失败 consumer_id=%s", consumer.consumer_id)
            try:
                db.rollback()
            except Exception:
                logger.exception("NEEDS_RECONCILE 回滚也失败 consumer_id=%s", consumer.consumer_id)
        try_publish_visualization_event(
            db,
            "order.failed",
            {
                "consumer_id": consumer.consumer_id,
                "evomap_node_id": consumer.evomap_node_id,
                "amount_credits": ledger.amount_credits,
                "payment_status": PAYMENT_STATUS_NEEDS_RECONCILE,
                "evomap_order_id": payment_proof.get("evomap_order_id"),
                "code": "local_order_reconcile_required",
                "reason": "EvoMap payment succeeded but local order persistence failed",
                "source_type": ORDER_SOURCE_SKILL,
            },
            agent_id=agent.agent_id,
            correlation_id=ledger.request_id,
        )
        raise SkillOrderError(
            "EvoMap payment succeeded but local order persistence failed; ledger marked needs_reconcile",
            code="local_order_reconcile_required",
            http_status=500,
        ) from exc


def reconcile_skill_ledger(db: Session, ledger_id: int) -> dict[str, Any]:
    """Finish local persistence for a payment that already succeeded externally.

    This path never calls EvoMap. A conditional ``needs_reconcile -> reconciling``
    claim prevents two workers from creating duplicate local orders.
    """
    now = datetime.utcnow()
    timeout_seconds = max(
        int(getattr(settings, "skill_reconcile_claim_timeout_seconds", 300)),
        60,
    )
    stale_before = now - timedelta(seconds=timeout_seconds)
    result = db.execute(
        update(SkillOrderLedger)
        .where(
            SkillOrderLedger.ledger_id == ledger_id,
            or_(
                SkillOrderLedger.payment_status == PAYMENT_STATUS_NEEDS_RECONCILE,
                (
                    (SkillOrderLedger.payment_status == PAYMENT_STATUS_RECONCILING)
                    & or_(
                        SkillOrderLedger.updated_at.is_(None),
                        SkillOrderLedger.updated_at <= stale_before,
                    )
                ),
            ),
        )
        .values(
            payment_status=PAYMENT_STATUS_RECONCILING,
            version=func.coalesce(SkillOrderLedger.version, 0) + 1,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = db.get(SkillOrderLedger, ledger_id)
        if current is None:
            raise SkillOrderError(
                "订单账本不存在", code="ledger_not_found", http_status=404
            )
        if current.payment_status in {PAYMENT_STATUS_FREE, PAYMENT_STATUS_PAID}:
            consumer = db.get(EvomapConsumer, current.consumer_id)
            if consumer is None:
                raise SkillOrderError(
                    "消费者不存在", code="consumer_not_found", http_status=404
                )
            return _success_response(consumer, current, "对账幂等重试：订单已完成")
        raise SkillOrderError(
            "该账本正在对账或当前状态不可对账",
            code="reconcile_claim_conflict",
            http_status=409,
        )
    db.commit()

    ledger = db.get(SkillOrderLedger, ledger_id)
    if ledger is None:
        raise SkillOrderError("订单账本不存在", code="ledger_not_found", http_status=404)
    consumer = db.get(EvomapConsumer, ledger.consumer_id)
    agent = db.get(AgentProfile, ledger.agent_id)
    if consumer is None or agent is None:
        ledger.payment_status = PAYMENT_STATUS_NEEDS_RECONCILE
        ledger.updated_at = datetime.utcnow()
        db.commit()
        raise SkillOrderError(
            "对账所需消费者或 Agent 不存在",
            code="reconcile_identity_missing",
            http_status=409,
        )

    items = [_private_item(item) for item in _ledger_items(ledger)]
    proof = decode_json(ledger.payment_proof_json, {})
    try:
        if ledger.stock_reservation_status != STOCK_RESERVATION_RESERVED:
            _reserve_stock_for_ledger(db, ledger, items)
        return _complete_order(
            db,
            consumer=consumer,
            agent=agent,
            ledger=ledger,
            items=items,
            payment_status=PAYMENT_STATUS_PAID,
            free_order_sequence=None,
            payment_proof=proof if isinstance(proof, dict) else None,
        )
    except Exception as exc:
        db.rollback()
        current = db.get(SkillOrderLedger, ledger_id)
        if current is not None:
            current.payment_status = PAYMENT_STATUS_NEEDS_RECONCILE
            current.updated_at = datetime.utcnow()
            db.commit()
        if isinstance(exc, OutOfStockError):
            raise SkillOrderError(
                str(exc), code="out_of_stock", http_status=409
            ) from exc
        if isinstance(exc, CatalogError):
            raise SkillOrderError(
                str(exc), code="product_unavailable", http_status=409
            ) from exc
        if isinstance(exc, SkillOrderError):
            raise
        raise SkillOrderError(
            "本地订单对账仍未完成",
            code="local_order_reconcile_failed",
            http_status=500,
        ) from exc


def _complete_order(
    db: Session,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    ledger: SkillOrderLedger,
    items: list[dict[str, Any]],
    payment_status: str,
    free_order_sequence: int | None,
    payment_proof: dict[str, Any] | None,
) -> dict[str, Any]:
    orders: list[Order] = []
    fresh_orders: list[tuple[Order, dict[str, Any]]] = []
    stock_is_reserved = (
        payment_status == PAYMENT_STATUS_PAID
        and ledger.stock_reservation_status == STOCK_RESERVATION_RESERVED
    )
    if ledger.ledger_id is None:
        db.add(ledger)
        db.flush()

    for index, item in enumerate(items):
        order_request_id = ledger.request_id if index == 0 else f"{ledger.request_id}:{index + 1}"
        existing = db.query(Order).filter(Order.request_id == order_request_id).first()
        if existing:
            existing.source_type = existing.source_type or ORDER_SOURCE_SKILL
            existing.payment_status = payment_status
            existing.consumer_id = existing.consumer_id or consumer.consumer_id
            existing.agent_id = existing.agent_id or agent.agent_id
            existing.ledger_id = existing.ledger_id or ledger.ledger_id
            existing.correlation_id = existing.correlation_id or ledger.request_id
            orders.append(existing)
            continue
        item_total = Decimal(str(item["price"]))
        order = Order(
            user_id=consumer.local_user_id,
            coffee_name=item["name"],
            amount=item_total,
            total_amount=item_total,
            status=ORDER_STATUS_PAID,
            request_id=order_request_id,
            source_type=ORDER_SOURCE_SKILL,
            payment_status=payment_status,
            consumer_id=consumer.consumer_id,
            agent_id=agent.agent_id,
            ledger_id=ledger.ledger_id,
            correlation_id=ledger.request_id,
        )
        orders.append(order)
        fresh_orders.append((order, item))

    for order in orders:
        db.add(order)
    db.flush()

    # Write order_item rows + decrement stock for freshly created orders so the
    # catalog reflects skill consumption and historical order content survives
    # later catalog edits. Free orders still consume stock but record no credits.
    resolved_products = {
        product.name: product for product in db.query(Product).all()
    }
    for order, item in fresh_orders:
        product = resolved_products.get(item["name"])
        line_price = Decimal(str(item["price"]))
        if product is None:
            raise CatalogError(f"商品不存在：{item['name']}")
        if not stock_is_reserved:
            decrement_stock(db, product.product_id, 1)
        db.add(
            OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                product_name_snapshot=item["name"],
                unit_price=line_price,
                quantity=1,
                line_total=line_price,
            )
        )
    db.flush()

    ledger.order_ids_json = encode_json([order.order_id for order in orders])
    ledger.payment_status = payment_status
    ledger.free_order_sequence = free_order_sequence
    ledger.updated_at = datetime.utcnow()
    if payment_proof:
        ledger.payment_proof_json = encode_json(payment_proof)
        ledger.evomap_order_id = payment_proof.get("evomap_order_id")
    if stock_is_reserved:
        ledger.stock_reservation_status = STOCK_RESERVATION_CONSUMED
    db.add(ledger)

    if payment_status == PAYMENT_STATUS_FREE and free_order_sequence is not None:
        consumer.free_orders_used = max(consumer.free_orders_used, free_order_sequence)
        consumer.last_seen_at = datetime.utcnow()
        if fresh_orders and fresh_orders[0][0].user_id is not None:
            order = fresh_orders[0][0]
            wallet_service.apply_transaction(
                db,
                user_id=order.user_id,
                currency=WALLET_CURRENCY_CREDITS,
                type_="free_order",
                amount=Decimal("0"),
                order_id=order.order_id,
                ledger_id=ledger.ledger_id,
                correlation_id=ledger.request_id,
                note=f"免费单账本 #{ledger.ledger_id}",
                allow_negative=True,
            )
    elif payment_status == PAYMENT_STATUS_PAID and ledger.amount_credits:
        if fresh_orders and fresh_orders[0][0].user_id is not None:
            order = fresh_orders[0][0]
            wallet_service.apply_transaction(
                db,
                user_id=order.user_id,
                currency=WALLET_CURRENCY_CREDITS,
                type_="consume",
                amount=-Decimal(str(ledger.amount_credits)),
                order_id=order.order_id,
                ledger_id=ledger.ledger_id,
                correlation_id=ledger.request_id,
                note=f"EvoMap 扣款镜像账本 #{ledger.ledger_id}",
                allow_negative=True,
            )

    # Refresh the Skill/CLI agent heartbeat so the snapshot's online window keeps
    # seeing them. Skill scripts can't hold a WebSocket, so last_seen_at is their
    # presence signal (see main.py _build_snapshot_agents ONLINE_WINDOW_SECONDS).
    agent.last_seen_at = datetime.utcnow()

    db.commit()
    db.refresh(ledger)
    for order in orders:
        db.refresh(order)

    _publish_skill_completion_flow(
        db,
        consumer=consumer,
        agent=agent,
        ledger=ledger,
        orders=orders,
        items=items,
        payment_status=payment_status,
        free_order_sequence=free_order_sequence,
    )
    try_publish_visualization_event(
        db,
        "order.paid",
        {
            "consumer_id": consumer.consumer_id,
            "evomap_node_id": consumer.evomap_node_id,
            "order_ids": [order.order_id for order in orders],
            "coffee_names": [order.coffee_name for order in orders],
            "total": float(sum((order.amount for order in orders), Decimal("0.00"))),
            "amount_credits": ledger.amount_credits,
            "payment_status": payment_status,
            "free_order_sequence": free_order_sequence,
            "evomap_order_id": ledger.evomap_order_id,
            "source_type": ORDER_SOURCE_SKILL,
            "agent_id": agent.agent_id,
            "ledger_id": ledger.ledger_id,
        },
        agent_id=agent.agent_id,
        correlation_id=ledger.request_id,
    )
    # 画像总结（购买完成触发）：异步 fire-and-forget，仅登录用户有效，
    # 失败 swallow 绝不阻断 Skill 下单。放在订单 commit + 事件发布之后，
    # 确保订单已落库可被画像读取。局部 import 规避循环依赖。
    try:
        from app.services import user_profile_service

        user_profile_service.summarize_async(consumer.local_user_id)
    except Exception:
        logger.warning(
            "skill 画像总结触发失败 user_id=%s", consumer.local_user_id, exc_info=True
        )
    return _success_response(consumer, ledger, "Skill 点单完成")



def _success_response(
    consumer: EvomapConsumer,
    ledger: SkillOrderLedger,
    reply: str,
) -> dict[str, Any]:
    order_ids = decode_json(ledger.order_ids_json, [])
    items = _ledger_items(ledger)
    free_remaining = max(settings.skill_free_order_limit - consumer.free_orders_used, 0)
    return {
        "ok": True,
        "status": "completed",
        "reply": reply,
        "request_id": ledger.request_id,
        "consumer_id": consumer.consumer_id,
        "ledger_id": ledger.ledger_id,
        "order_ids": order_ids,
        "coffee_names": [item["name"] for item in items],
        "amount_credits": ledger.amount_credits,
        "payment_status": ledger.payment_status,
        "free_orders_remaining": free_remaining,
        "evomap_order_id": ledger.evomap_order_id,
    }


def _reject_unverified_payment_proof(
    db: Session,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    ledger: SkillOrderLedger,
    items: list[dict[str, Any]],
) -> None:
    ledger.payment_status = PAYMENT_STATUS_PAYMENT_REQUIRED
    ledger.updated_at = datetime.utcnow()
    db.add(ledger)
    db.commit()
    payload = _payment_required_payload(consumer, ledger, items)
    payload["code"] = "payment_proof_unverifiable"
    payload["reply"] = (
        "Client-submitted EvoMap payment proofs are not accepted because this "
        "backend cannot verify that credits were deducted. Provide "
        "X-Evomap-Node-Secret so the backend can place the official EvoMap "
        "service order."
    )
    _publish_skill_restaurant_event(
        db,
        "restaurant.payment_requested",
        consumer=consumer,
        agent=agent,
        correlation_id=ledger.request_id,
        state="payment_required",
        items=items,
        amount_credits=ledger.amount_credits,
        payment_status=PAYMENT_STATUS_PAYMENT_REQUIRED,
        ledger=ledger,
        reason="payment_proof_unverifiable",
        stage="evomap_payment",
        patience=60,
        satisfaction=68,
    )
    try_publish_visualization_event(
        db,
        "order.payment_required",
        payload,
        agent_id=agent.agent_id,
        correlation_id=ledger.request_id,
    )
    raise SkillPaymentRequired(payload)


def _payment_required_payload(
    consumer: EvomapConsumer,
    ledger: SkillOrderLedger,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    coffee_names = [item["name"] for item in items]
    service_order_request = build_service_order_request(
        request_id=ledger.request_id,
        consumer_node_id=consumer.evomap_node_id,
        coffee_names=coffee_names,
        amount_credits=ledger.amount_credits,
    )
    return {
        "ok": False,
        "status": PAYMENT_STATUS_PAYMENT_REQUIRED,
        "reply": "This order requires EvoMap Credits. Provide the node secret for a server-side service order.",
        "request_id": ledger.request_id,
        "consumer_id": consumer.consumer_id,
        "ledger_id": ledger.ledger_id,
        "amount_credits": ledger.amount_credits,
        "free_orders_remaining": 0,
        "coffee_names": coffee_names,
        "source_type": ORDER_SOURCE_SKILL,
        "payment_request": None,
        "payment_method": "evomap_service_order",
        "service_order_request": service_order_request,
    }


def process_skill_cny_order(
    db: Session,
    *,
    consumer: EvomapConsumer,
    agent: AgentProfile,
    message: str,
    request_id: str | None,
) -> dict[str, Any]:
    """Place a Skill order against the linked project's CNY wallet.

    Historical EvoMap ledgers continue to use :func:`process_skill_order` for
    reconciliation.  All newly authenticated Skill traffic enters here.
    """
    correlation_id = request_id or f"skill-{consumer.consumer_id}-{uuid.uuid4().hex}"
    existing = db.query(SkillOrderLedger).filter(
        SkillOrderLedger.request_id == correlation_id
    ).first()
    if existing is not None:
        if existing.consumer_id != consumer.consumer_id or existing.agent_id != agent.agent_id:
            raise SkillOrderError(
                "request_id 已被其他账号使用",
                code="request_id_conflict",
                http_status=409,
            )
        orders = db.query(Order).filter(Order.ledger_id == existing.ledger_id).all()
        if orders:
            if existing.payment_status != PAYMENT_STATUS_PAID:
                existing.payment_status = PAYMENT_STATUS_PAID
                existing.order_ids_json = encode_json([order.order_id for order in orders])
                existing.updated_at = datetime.utcnow()
                db.commit()
            return _cny_success_response(db, consumer, existing, orders)

    items = _resolve_items(db, message)
    if not items:
        raise SkillOrderError(
            "未能从 Skill 点单消息中识别咖啡",
            code="coffee_not_resolved",
            http_status=400,
        )
    total = sum((Decimal(str(item["price"])) for item in items), Decimal("0.00"))
    conflicting = db.query(Order).filter(Order.request_id == correlation_id).first()
    if conflicting is not None:
        raise SkillOrderError(
            "request_id 已被其他订单使用",
            code="request_id_conflict",
            http_status=409,
        )

    ledger = SkillOrderLedger(
        consumer_id=consumer.consumer_id,
        agent_id=agent.agent_id,
        request_id=correlation_id,
        coffee_items_json=encode_json(_public_items(items)),
        amount_credits=0,
        amount_cny=total,
        payment_status=PAYMENT_STATUS_PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(ledger)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        concurrent = db.query(SkillOrderLedger).filter(
            SkillOrderLedger.request_id == correlation_id
        ).first()
        if concurrent is not None:
            if (
                concurrent.consumer_id != consumer.consumer_id
                or concurrent.agent_id != agent.agent_id
            ):
                raise SkillOrderError(
                    "request_id 已被其他账号使用",
                    code="request_id_conflict",
                    http_status=409,
                ) from exc
            concurrent_orders = db.query(Order).filter(
                Order.ledger_id == concurrent.ledger_id
            ).all()
            if concurrent_orders:
                return _cny_success_response(
                    db, consumer, concurrent, concurrent_orders
                )
        raise SkillOrderError(
            "相同 request_id 正在处理中，请稍后使用原 request_id 重试",
            code="request_race_retry",
            http_status=409,
        ) from exc
    order_items = [
        (item["name"], correlation_id if index == 0 else f"{correlation_id}:{index + 1}")
        for index, item in enumerate(items)
    ]
    try:
        orders = place_orders(
            db,
            consumer.local_user_id,
            order_items,
            source_type=ORDER_SOURCE_SKILL,
            payment_status=PAYMENT_STATUS_PAID,
            consumer_id=consumer.consumer_id,
            agent_id=agent.agent_id,
            ledger_id=ledger.ledger_id,
            correlation_id=correlation_id,
            commit=False,
        )
    except InsufficientBalanceError as exc:
        db.rollback()
        raise SkillOrderError(
            str(exc), code="insufficient_balance", http_status=402
        ) from exc
    except OutOfStockError as exc:
        db.rollback()
        raise SkillOrderError(str(exc), code="out_of_stock", http_status=409) from exc
    except (CatalogError, OrderError, ValueError) as exc:
        db.rollback()
        raise SkillOrderError(str(exc), code="order_failed", http_status=400) from exc

    ledger = db.query(SkillOrderLedger).filter(
        SkillOrderLedger.ledger_id == ledger.ledger_id
    ).first()
    if ledger is None:
        raise SkillOrderError("订单账本写入失败", code="ledger_missing", http_status=500)
    ledger.order_ids_json = encode_json([order.order_id for order in orders])
    ledger.payment_status = PAYMENT_STATUS_PAID
    ledger.updated_at = datetime.utcnow()
    agent.last_seen_at = datetime.utcnow()
    consumer.last_seen_at = datetime.utcnow()
    db.commit()

    try:
        customer_enter_scene(db, agent, correlation_id=correlation_id)
        _publish_skill_completion_flow(
            db,
            consumer=consumer,
            agent=agent,
            ledger=ledger,
            orders=orders,
            items=items,
            payment_status=PAYMENT_STATUS_PAID,
            free_order_sequence=None,
        )
    except Exception:
        logger.warning("Skill CNY 订单可视化事件发布失败", exc_info=True)
    return _cny_success_response(db, consumer, ledger, orders)


def _cny_success_response(
    db: Session,
    consumer: EvomapConsumer,
    ledger: SkillOrderLedger,
    orders: list[Order],
) -> dict[str, Any]:
    amount_cny = ledger.amount_cny
    if amount_cny is None:
        amount_cny = sum(
            (Decimal(str(order.total_amount or order.amount or 0)) for order in orders),
            Decimal("0.00"),
        )
    balance = wallet_service.get_balance(db, consumer.local_user_id, WALLET_CURRENCY_CNY)
    items = _ledger_items(ledger)
    return {
        "ok": True,
        "status": "completed",
        "reply": "Skill 点单完成，已从咖啡厅账户余额扣款",
        "request_id": ledger.request_id,
        "consumer_id": consumer.consumer_id,
        "ledger_id": ledger.ledger_id,
        "order_ids": [order.order_id for order in orders],
        "coffee_names": [item["name"] for item in items],
        "amount_credits": 0,
        "amount_cny": float(amount_cny),
        "currency": WALLET_CURRENCY_CNY,
        "balance_after": float(balance),
        "payment_status": PAYMENT_STATUS_PAID,
        "free_orders_remaining": 0,
        "evomap_order_id": None,
    }


def _resolve_items(db: Session, message: str) -> list[dict[str, Any]]:
    names = _resolve_coffee_names(db, message)
    items = []
    for name in names:
        product = db.query(Product).filter(Product.name == name).first()
        if product:
            items.append(
                {"name": product.name, "price": Decimal(str(product.base_price))}
            )
    return items


def _resolve_coffee_names(db: Session, message: str) -> list[str]:
    """Parse coffee names from a free-form Skill message.

    Returns exact product names only. Short names (冷萃/拿铁/美式) are accepted
    via :func:`get_product_by_name` only when they match a single product;
    ambiguous short names (e.g. 「冷萃」hits both 柑橘冷萃 and 椰香冷萃) are NOT
    coerced to the cheapest match — the caller surfaces a "please specify"
    prompt instead. This fixes the bug where a short name silently mapped to a
    different cup and the charged price diverged from what the user ordered.
    """
    rows = db.query(Product).order_by(Product.base_price.asc()).all()
    names = [row.name for row in rows]

    direct = [name for name in names if name in message]
    if direct:
        return direct[:1]

    price = extract_price(message)
    if price is not None:
        matched = [row.name for row in match_by_price(db, price)]
        if matched:
            return matched[:1]

    try:
        intent = llm.parse_intent([], message)
        coffee = (intent.get("coffee_name") or "").strip()
        if coffee:
            try:
                product = get_product_by_name(db, coffee)
            except AmbiguousProductError:
                # LLM 给出歧义简称（如「冷萃」），不硬凑最便宜的一杯。
                product = None
            if product:
                return [product.name]
    except Exception:
        logger.exception("LLM 解析咖啡名失败，回退 RAG 兜底 message=%r", message[:80])

    positive, negative = extract_keywords(message)
    if positive or negative:
        retrieved = [row.name for row in retrieve(db, positive, negative)]
        # 关键词命中唯一一杯才接受；命中多杯（如「拿铁」同时命中焦糖玛奇朵
        # 和莓果拿铁的 tags）属于歧义，下单场景不取最便宜的一杯。
        if len(retrieved) == 1:
            return retrieved

    return []


def _public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"name": item["name"], "price": float(item["price"])} for item in items]


def _ledger_items(ledger: SkillOrderLedger) -> list[dict[str, Any]]:
    return decode_json(ledger.coffee_items_json, [])


def _private_item(item: dict[str, Any]) -> dict[str, Any]:
    return {"name": item["name"], "price": Decimal(str(item["price"]))}
