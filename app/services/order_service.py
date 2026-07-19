"""Order placement + refund service.

A paid order is one ``order`` header plus N ``order_item`` rows (one per cup),
each carrying snapshotted product name / unit price / selected options so later
catalog edits never rewrite history. Stock and CNY wallet are debited in the
same transaction and rolled back together on failure.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Order, OrderItem, OrderItemOption, Product, User
from app.domain_constants import (
    ORDER_PAYMENT_STATUSES,
    ORDER_SOURCE_TYPES,
    ORDER_SOURCE_WEB_DIALOG,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_REFUNDED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_REFUNDED,
)
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


class InsufficientBalanceError(wallet_service.InsufficientBalanceError):
    pass


class OrderError(Exception):
    pass


class LineSpec:
    """Resolved order line. Options is a list of (group_id, option_id,
    group_name, option_name, price_delta) tuples captured before insertion."""

    def __init__(
        self,
        product: Product,
        quantity: int = 1,
        options: list[tuple[int | None, int | None, str | None, str | None, Decimal]] | None = None,
    ) -> None:
        self.product = product
        self.quantity = quantity
        self.options = options or []

    @property
    def unit_price(self) -> Decimal:
        base = Decimal(self.product.base_price)
        return base + sum((Decimal(o[4]) for o in self.options), Decimal("0.00"))

    @property
    def line_total(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(Decimal("0.01"))


def resolve_line(db: Session, coffee_name: str, quantity: int = 1) -> LineSpec:
    """Look up a product by name and return a single-quantity, no-option line."""
    try:
        product = get_product_by_name(db, coffee_name)
    except AmbiguousProductError as exc:
        # 简称命中多杯（如「冷萃」），下单前必须让用户明确，不能擅自选一杯。
        raise OrderError(str(exc)) from exc
    if product is None:
        raise OrderError(f"未找到商品：{coffee_name}")
    return LineSpec(product=product, quantity=quantity)


def place_orders(
    db: Session,
    user_id: int,
    items: list[tuple[str, str | None]],
    *,
    source_type: str = ORDER_SOURCE_WEB_DIALOG,
    payment_status: str = PAYMENT_STATUS_PAID,
    consumer_url: str | None = None,
    consumer_id: int | None = None,
    agent_id: int | None = None,
    ledger_id: int | None = None,
    correlation_id: str | None = None,
    commit: bool = True,
) -> list[Order]:
    """Place a paid order.

    ``items`` keeps the legacy ``[(coffee_name, request_id), ...]`` shape. Each
    entry becomes one ``order_item`` row; the whole batch is written under one
    ``order`` header with a shared ``request_id`` (legacy per-cup request ids
    are preserved on their line for idempotency checks).

    Stock, wallet, header, and line items are committed atomically; any failure
    rolls the whole order back.
    """
    if not items:
        raise OrderError("订单为空")
    if source_type not in ORDER_SOURCE_TYPES:
        raise ValueError(f"不支持的订单来源：{source_type}")
    if payment_status not in ORDER_PAYMENT_STATUSES:
        raise ValueError(f"不支持的支付状态：{payment_status}")

    user = db.execute(
        select(User).where(User.user_id == user_id).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    # Idempotency: if any line's request_id already produced an order, return
    # the existing header rows unchanged.
    existing_orders: list[Order] = []
    seen_request_ids: set[str] = set()
    for _, req_id in items:
        if req_id and req_id not in seen_request_ids:
            seen_request_ids.add(req_id)
            existed = db.query(Order).filter(Order.request_id == req_id).first()
            if existed:
                if existed.user_id != user_id:
                    raise OrderError("request_id 已被其他用户使用")
                existing_orders.append(existed)
    if existing_orders:
        return existing_orders

    lines: list[LineSpec] = []
    for coffee_name, _ in items:
        line = resolve_line(db, coffee_name, quantity=1)
        lines.append(line)

    total = sum((line.line_total for line in lines), Decimal("0.00")).quantize(
        Decimal("0.01")
    )

    # Lock the user's CNY wallet and verify balance before any stock writes.
    wallet_service.ensure_wallet(db, user_id)
    balance = wallet_service.get_balance(db, user_id)
    if balance < total:
        raise InsufficientBalanceError(
            f"余额不足：当前 ¥{balance}，{len(lines)} 杯共需 ¥{total}"
        )

    header_request_id = items[0][1]
    header = Order(
        user_id=user_id,
        status=ORDER_STATUS_PAID,
        request_id=header_request_id,
        source_type=source_type,
        payment_status=payment_status,
        consumer_url=consumer_url,
        consumer_id=consumer_id,
        agent_id=agent_id,
        ledger_id=ledger_id,
        correlation_id=correlation_id,
        total_amount=total,
        # Legacy columns are populated for back-compat readers and then dropped
        # by a later migration; nullability has been relaxed.
        coffee_name=", ".join(line.product.name for line in lines)[:128],
        amount=total,
    )
    db.add(header)
    db.flush()

    for line in lines:
        decrement_stock(db, line.product.product_id, line.quantity)
        item = OrderItem(
            order_id=header.order_id,
            product_id=line.product.product_id,
            product_name_snapshot=line.product.name,
            unit_price=line.unit_price,
            quantity=line.quantity,
            line_total=line.line_total,
        )
        db.add(item)
        db.flush()
        for group_id, option_id, group_name, option_name, price_delta in line.options:
            db.add(
                OrderItemOption(
                    item_id=item.item_id,
                    group_id=group_id,
                    option_id=option_id,
                    group_name_snapshot=group_name,
                    option_name_snapshot=option_name,
                    price_delta=Decimal(price_delta),
                )
            )

    wallet_service.apply_transaction(
        db,
        user_id=user_id,
        currency=WALLET_CURRENCY_CNY,
        type_="consume",
        amount=-total,
        order_id=header.order_id,
        correlation_id=correlation_id or header_request_id,
        note=f"订单 #{header.order_id} 消费",
    )

    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        if header_request_id:
            concurrent = (
                db.query(Order).filter(Order.request_id == header_request_id).first()
            )
            if concurrent is not None and concurrent.user_id == user_id:
                return [concurrent]
            if concurrent is not None:
                raise OrderError("request_id 已被其他用户使用") from exc
        raise OrderError("订单幂等键发生并发冲突，请重试") from exc
    db.refresh(header)
    return [header]


def refund_order(db: Session, order_id: int, *, note: str | None = None) -> Order:
    """Refund a paid order.

    Transitions the header paid -> cancelled -> refunded, credits the CNY
    wallet back, restores product stock per line, and marks the payment status
    ``refunded``. Skill-source ledgers keep their own payment_status; callers
    that need to mirror it into ``skill_order_ledger`` do so separately.
    """
    order = db.execute(
        select(Order).where(Order.order_id == order_id).with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise OrderError(f"订单 {order_id} 不存在")
    if order.status == ORDER_STATUS_REFUNDED:
        return order
    if order.status not in {ORDER_STATUS_PAID}:
        raise OrderError(f"订单 {order_id} 当前状态无法退款：status={order.status}")

    refund_total = Decimal(order.total_amount or order.amount or 0)

    order.status = ORDER_STATUS_CANCELLED
    order.cancelled_at = datetime.utcnow()
    db.flush()

    items = (
        db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    )
    for item in items:
        if item.product_id is not None:
            restore_stock(db, item.product_id, item.quantity)

    if refund_total > 0:
        wallet_service.apply_transaction(
            db,
            user_id=order.user_id,
            currency=WALLET_CURRENCY_CNY,
            type_="refund",
            amount=refund_total,
            order_id=order.order_id,
            correlation_id=order.correlation_id or order.request_id,
            note=note or f"订单 #{order.order_id} 退款",
        )

    order.status = ORDER_STATUS_REFUNDED
    order.refunded_at = datetime.utcnow()
    order.payment_status = PAYMENT_STATUS_REFUNDED
    db.commit()
    db.refresh(order)
    return order


# Re-export for callers that import OutOfStockError/CatalogError from here.
__all__ = [
    "InsufficientBalanceError",
    "OrderError",
    "OutOfStockError",
    "CatalogError",
    "LineSpec",
    "resolve_line",
    "place_orders",
    "refund_order",
]
