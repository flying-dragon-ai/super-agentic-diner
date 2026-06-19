# ============================================================
# 【面试题·任务三】下单扣款服务 —— 事务 + 行锁，保证扣钱安全性
#
# 对应面试题提示："注意扣钱操作的安全性和顺序"
#
# 核心安全措施（5步）：
#   1. BEGIN（开启事务）
#   2. SELECT balance ... FOR UPDATE（行锁，防并发双扣）
#   3. 校验余额 >= 金额（防超扣）
#   4. 同事务内：扣余额 + 插订单（原子性，要么都成功要么都回滚）
#   5. COMMIT（提交事务）
#
# 额外保障：request_id 幂等键（防重复提交同一笔订单）
# ============================================================
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CoffeeKB, Order, User


class InsufficientBalanceError(Exception):
    pass


class CoffeeNotResolvedError(Exception):
    pass


def place_order(
    db, user_id, coffee_name, expected_price, request_id=None,
):
    """【任务三】安全扣款下单（单杯）。返回已支付订单。

    安全流程（对应面试题任务三"扣钱操作的安全性和顺序"）：

    第1步：确定金额（用传入的 expected_price 或从知识库查价）
    第2步：幂等检查（同 request_id 已有订单则直接返回，防重复提交）
    第3步：SELECT ... FOR UPDATE 行锁读取用户余额（防并发双扣）
    第4步：校验余额 >= 金额（防超扣）
    第5步：同事务内原子操作：扣余额 + 插订单
    第6步：COMMIT 提交（异常会自动回滚）
    """
    if not coffee_name:
        raise CoffeeNotResolvedError("无法确定要购买哪杯咖啡")

    # 第1步：确定金额（优先用 LLM 返回的价格，否则从知识库查）
    amount = (
        Decimal(str(expected_price)) if expected_price else _lookup_price(db, coffee_name)
    )

    # 第2步：幂等检查 —— 同一个 request_id 只生成一笔订单，防止用户重复点击
    if request_id:
        existed = db.query(Order).filter(Order.request_id == request_id).first()
        if existed:
            return existed  # 已有订单，直接返回，不重复扣款

    # 第3步：【任务三·核心】行锁读取用户余额
    # FOR UPDATE 加行锁：如果两个请求同时下单，第二个会等第一个提交后才能读到最新余额
    # 这防止了"并发双扣"（两个请求同时读到旧余额，各扣一次导致超扣）
    user = db.execute(
        select(User).where(User.user_id == user_id).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    # 第4步：校验余额是否足够（防超扣）
    if user.balance < amount:
        raise InsufficientBalanceError(f"余额不足：当前 {user.balance}，需 {amount}")

    # 第5步：同事务内原子操作 —— 扣余额 + 插订单
    # 这两步在同一个事务里，要么都成功要么都回滚，保证数据一致性
    user.balance = user.balance - amount
    order = Order(
        user_id=user_id,
        coffee_name=coffee_name,
        amount=amount,
        status=1,  # 已支付
        request_id=request_id,
    )
    db.add(order)

    # 第6步：提交事务（COMMIT）
    # 如果上面任何一步出错，事务会自动回滚，余额和订单都不会变
    db.commit()
    db.refresh(order)
    return order


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
                orders.append(existed)
                continue
        orders.append(Order(
            user_id=user_id, coffee_name=coffee_name,
            amount=amount, status=1, request_id=req_id,
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
