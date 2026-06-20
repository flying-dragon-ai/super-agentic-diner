from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

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
    PAYMENT_STATUS_PAYMENT_PENDING,
    PAYMENT_STATUS_PAYMENT_REQUIRED,
    PAYMENT_STATUS_PENDING,
)
from app.llm import client as llm
from app.rag.keywords import extract_keywords
from app.rag.retrieval import retrieve
from app.services.chat_service import extract_price, match_by_price
from app.services.evomap_payment_service import (
    EvomapPaymentError,
    build_service_order_request,
    credits_for_order,
    place_service_order,
)
from app.services.visualization_service import (
    create_visualization_event,
    decode_json,
    encode_json,
    visualization_hub,
)
from app.db.models import Product
from app.domain_constants import WALLET_CURRENCY_CREDITS
from app.services import wallet_service
from app.services.catalog_service import decrement_stock

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
    message = create_visualization_event(
        db,
        event_type=event_type,
        payload=payload,
        agent_id=agent_id,
        correlation_id=correlation_id,
    )
    visualization_hub.broadcast_from_sync(message)
    return message


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
    _publish_skill_restaurant_event(
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
        _publish_skill_restaurant_event(
            db,
            "restaurant.preparation_progress",
            state="making",
            stage=stage,
            message=label,
            patience=patience,
            satisfaction=90,
            **common,
        )
    _publish_skill_restaurant_event(
        db,
        "restaurant.order_ready",
        state="ready",
        patience=70,
        satisfaction=92,
        **common,
    )
    _publish_skill_restaurant_event(
        db,
        "restaurant.order_delivered",
        state="delivered",
        patience=74,
        satisfaction=94,
        **common,
    )
    _publish_skill_restaurant_event(
        db,
        "restaurant.customer_reviewed",
        state="reviewed",
        message="顾客评价：出餐顺利",
        patience=76,
        satisfaction=96,
        **common,
    )
    _publish_skill_restaurant_event(
        db,
        "restaurant.customer_left",
        state="left",
        patience=80,
        satisfaction=96,
        **common,
    )


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
        if existing.consumer_id != consumer.consumer_id:
            raise SkillOrderError(
                "request_id 已被其他 EvoMap 消费者使用",
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
    free_sequence = consumer.free_orders_used + 1
    is_free = free_sequence <= settings.skill_free_order_limit

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
        free_order_sequence=free_sequence if is_free else None,
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

    if is_free:
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
        PAYMENT_STATUS_PAYMENT_REQUIRED,
        PAYMENT_STATUS_PAYMENT_FAILED,
        PAYMENT_STATUS_PAYMENT_PENDING,
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
        ledger.payment_status = PAYMENT_STATUS_PAYMENT_PENDING
        ledger.updated_at = datetime.utcnow()
        db.commit()
        return _charge_evomap_and_complete(
            db,
            consumer=consumer,
            agent=agent,
            ledger=ledger,
            items=[_private_item(item) for item in items],
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
        payment_status=PAYMENT_STATUS_PAYMENT_PENDING,
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
        if product is not None:
            decrement_stock(db, product.product_id, 1)
        db.add(
            OrderItem(
                order_id=order.order_id,
                product_id=product.product_id if product else None,
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
    db.add(ledger)

    if payment_status == PAYMENT_STATUS_FREE and free_order_sequence is not None:
        consumer.free_orders_used = max(consumer.free_orders_used, free_order_sequence)
        consumer.last_seen_at = datetime.utcnow()
        for order, _item in fresh_orders:
            if order.user_id is not None:
                wallet_service.apply_transaction(
                    db,
                    user_id=order.user_id,
                    currency=WALLET_CURRENCY_CREDITS,
                    type_="free_order",
                    amount=Decimal("0"),
                    order_id=order.order_id,
                    ledger_id=ledger.ledger_id,
                    correlation_id=ledger.request_id,
                    note=f"免费单 #{order.order_id}",
                    allow_negative=True,
                )
    elif payment_status == PAYMENT_STATUS_PAID and ledger.amount_credits:
        for order, _item in fresh_orders:
            if order.user_id is not None:
                wallet_service.apply_transaction(
                    db,
                    user_id=order.user_id,
                    currency=WALLET_CURRENCY_CREDITS,
                    type_="consume",
                    amount=-Decimal(str(ledger.amount_credits)),
                    order_id=order.order_id,
                    ledger_id=ledger.ledger_id,
                    correlation_id=ledger.request_id,
                    note=f"EvoMap 扣款镜像 #{order.order_id}",
                    allow_negative=True,
                )

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
        coffee = intent.get("coffee_name")
        if coffee:
            for name in names:
                if name in coffee or coffee in name:
                    return [name]
    except Exception:
        logger.exception("LLM 解析咖啡名失败，回退 RAG 兜底 message=%r", message[:80])

    positive, negative = extract_keywords(message)
    if positive or negative:
        retrieved = [row.name for row in retrieve(db, positive, negative)]
        if retrieved:
            return retrieved[:1]

    for row in rows:
        if row.name.endswith("拿铁") and "拿铁" in message:
            return [row.name]
        if row.name.endswith("冷萃") and "冷萃" in message:
            return [row.name]
        if "美式" in row.name and "美式" in message:
            return [row.name]
    return []


def _public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"name": item["name"], "price": float(item["price"])} for item in items]


def _ledger_items(ledger: SkillOrderLedger) -> list[dict[str, Any]]:
    return decode_json(ledger.coffee_items_json, [])


def _private_item(item: dict[str, Any]) -> dict[str, Any]:
    return {"name": item["name"], "price": Decimal(str(item["price"]))}
