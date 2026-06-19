"""Order placement service with transaction-safe balance deduction."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CoffeeKB, Order, User


class InsufficientBalanceError(Exception):
    pass


def _lookup_price(db: Session, coffee_name: str) -> Decimal:
    """从知识库反查价格，查不到则用兜底默认价"""
    kb = (
        db.query(CoffeeKB)
        .filter(CoffeeKB.coffee_name.like(f"%{coffee_name}%"))
        .first()
    )
    return kb.price if kb else Decimal("25.00")


def place_orders(
    db: Session,
    user_id: int,
    items: list[tuple[str, str | None]],
    *,
    source_type: str = "web_dialog",
    consumer_url: str | None = None,
    consumer_id: int | None = None,
    agent_id: int | None = None,
    ledger_id: int | None = None,
    correlation_id: str | None = None,
) -> list[Order]:
    """批量下单：同一事务内对多杯咖啡扣款。
    items = [(coffee_name, request_id), ...]
    任意一杯余额不足则全部回滚。
    """
    user = db.execute(
        select(User).where(User.user_id == user_id).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    orders: list[Order] = []
    total = Decimal("0.00")
    for coffee_name, req_id in items:
        amount = _lookup_price(db, coffee_name)
        total += amount
        if req_id:
            existed = db.query(Order).filter(Order.request_id == req_id).first()
            if existed:
                existed.source_type = existed.source_type or source_type
                existed.consumer_url = existed.consumer_url or consumer_url
                existed.consumer_id = existed.consumer_id or consumer_id
                existed.agent_id = existed.agent_id or agent_id
                existed.ledger_id = existed.ledger_id or ledger_id
                existed.correlation_id = existed.correlation_id or correlation_id
                orders.append(existed)
                continue
        orders.append(Order(
            user_id=user_id, coffee_name=coffee_name,
            amount=amount, status=1, request_id=req_id,
            source_type=source_type,
            consumer_url=consumer_url,
            consumer_id=consumer_id,
            agent_id=agent_id,
            ledger_id=ledger_id,
            correlation_id=correlation_id,
        ))

    if user.balance < total:
        raise InsufficientBalanceError(
            f"余额不足：当前 ¥{user.balance}，{len(orders)} 杯共需 ¥{total}"
        )

    user.balance = user.balance - total
    for o in orders:
        db.add(o)
    db.commit()
    for o in orders:
        db.refresh(o)
    return orders
