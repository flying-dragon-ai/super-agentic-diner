"""Unified multi-currency wallet + append-only ledger service.

All balance changes go through :func:`apply_transaction`, which writes one
``balance_transaction`` row and updates the matching ``user_wallet`` running
balance in the same unit of work. ``user.balance`` is deprecated; callers read
the CNY wallet via :func:`get_balance`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import BalanceTransaction, UserWallet
from app.domain_constants import (
    TRANSACTION_TYPES,
    WALLET_CURRENCIES,
    WALLET_CURRENCY_CNY,
)


class WalletError(Exception):
    pass


class InsufficientBalanceError(WalletError):
    pass


def _get_wallet_for_update(db: Session, user_id: int, currency: str) -> UserWallet:
    if currency not in WALLET_CURRENCIES:
        raise WalletError(f"unsupported currency: {currency}")
    wallet = db.execute(
        select(UserWallet)
        .where(UserWallet.user_id == user_id, UserWallet.currency == currency)
        .with_for_update()
    ).scalar_one_or_none()
    if wallet is None:
        # Materialize through a savepoint.  A concurrent creator may win the
        # composite primary-key race; in that case roll back only the savepoint
        # and re-read the canonical row under the normal lock.
        try:
            with db.begin_nested():
                db.add(
                    UserWallet(
                        user_id=user_id,
                        currency=currency,
                        balance=Decimal("0.0000"),
                    )
                )
                db.flush()
        except IntegrityError:
            pass
        wallet = db.execute(
            select(UserWallet)
            .where(
                UserWallet.user_id == user_id,
                UserWallet.currency == currency,
            )
            .with_for_update()
        ).scalar_one()
    return wallet


def get_balance(db: Session, user_id: int, currency: str = WALLET_CURRENCY_CNY) -> Decimal:
    """Return the running balance for a wallet, materializing a 0 row if absent."""
    if currency not in WALLET_CURRENCIES:
        raise WalletError(f"unsupported currency: {currency}")
    wallet = (
        db.query(UserWallet)
        .filter(
            UserWallet.user_id == user_id,
            UserWallet.currency == currency,
        )
        .first()
    )
    if wallet is None:
        return Decimal("0.0000")
    return Decimal(wallet.balance)


def ensure_wallet(db: Session, user_id: int, currency: str = WALLET_CURRENCY_CNY) -> UserWallet:
    return _get_wallet_for_update(db, user_id, currency)


def apply_transaction(
    db: Session,
    *,
    user_id: int,
    currency: str,
    type_: str,
    amount: Decimal,
    order_id: int | None = None,
    ledger_id: int | None = None,
    correlation_id: str | None = None,
    note: str | None = None,
    allow_negative: bool = False,
) -> BalanceTransaction:
    """Write one ledger row + update the wallet running balance.

    ``amount`` is signed. For ``consume``-style flows pass a negative amount;
    this helper still requires the wallet to stay >= 0 unless ``allow_negative``
    is set (credits mirror may go informational-only negative).
    """
    if type_ not in TRANSACTION_TYPES:
        raise WalletError(f"unsupported transaction type: {type_}")
    if amount is None:
        raise WalletError("amount is required")
    amount = Decimal(amount)
    if currency not in WALLET_CURRENCIES:
        raise WalletError(f"unsupported currency: {currency}")

    _get_wallet_for_update(db, user_id, currency)
    new_balance_expression = UserWallet.balance + amount
    conditions = [
        UserWallet.user_id == user_id,
        UserWallet.currency == currency,
    ]
    if not allow_negative:
        conditions.append(new_balance_expression >= 0)
    result = db.execute(
        update(UserWallet)
        .where(*conditions)
        .values(balance=new_balance_expression)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.expire_all()
        wallet = db.execute(
            select(UserWallet).where(
                UserWallet.user_id == user_id,
                UserWallet.currency == currency,
            )
        ).scalar_one()
        raise InsufficientBalanceError(
            f"余额不足：当前 ¥{wallet.balance}（{currency}），本次需 ¥{abs(amount)}"
        )
    db.expire_all()
    wallet = db.execute(
        select(UserWallet).where(
            UserWallet.user_id == user_id,
            UserWallet.currency == currency,
        )
    ).scalar_one()
    new_balance = Decimal(wallet.balance)
    txn = BalanceTransaction(
        user_id=user_id,
        currency=currency,
        type=type_,
        amount=amount,
        balance_after=new_balance,
        order_id=order_id,
        ledger_id=ledger_id,
        correlation_id=correlation_id,
        note=note,
    )
    db.add(txn)
    db.flush()
    return txn


def topup(
    db: Session,
    *,
    user_id: int,
    amount: Decimal,
    currency: str = WALLET_CURRENCY_CNY,
    note: str | None = None,
) -> BalanceTransaction:
    if amount <= 0:
        raise WalletError("topup amount must be positive")
    return apply_transaction(
        db,
        user_id=user_id,
        currency=currency,
        type_="topup",
        amount=Decimal(amount),
        note=note or "充值",
    )
