"""Idempotent MySQL migration: unified multi-currency wallet + ledger.

Creates ``balance_transaction`` (append-only) and ``user_wallet`` (per-currency
running balance) if missing, migrates each ``user.balance`` into a CNY
``user_wallet`` row plus a single ``topup`` ledger row, and is safe to run more
than once. The legacy ``user.balance`` column is left in place for rollback.

Usage: python scripts/migrate_wallet_ledger.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine  # noqa: E402
from app.db.models import BalanceTransaction, UserWallet  # noqa: E402
from app.domain_constants import TRANSACTION_TYPE_TOPUP, WALLET_CURRENCY_CNY  # noqa: E402


def _ensure_mysql() -> None:
    if engine.dialect.name != "mysql":
        raise RuntimeError(
            f"This migration is MySQL-only; current dialect is {engine.dialect.name!r}."
        )


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def main() -> None:
    _ensure_mysql()
    inspector = inspect(engine)

    for model in (BalanceTransaction, UserWallet):
        if not _table_exists(inspector, model.__tablename__):
            print(f"[wallet] creating table {model.__tablename__}")
            model.__table__.create(engine, checkfirst=True)
        else:
            print(f"[wallet] table {model.__tablename__} already exists")

    # Backfill via ORM so Python defaults (created_at/updated_at) are applied.
    with Session(engine) as session:
        users = session.execute(text("SELECT user_id, balance FROM `user`")).fetchall()
        migrated = 0
        for user_id, balance in users:
            balance = float(balance or 0)
            already = session.execute(
                text(
                    "SELECT COUNT(*) FROM user_wallet "
                    "WHERE user_id = :uid AND currency = :cur"
                ),
                {"uid": user_id, "cur": WALLET_CURRENCY_CNY},
            ).scalar()
            if already:
                continue
            session.add(
                UserWallet(
                    user_id=user_id,
                    currency=WALLET_CURRENCY_CNY,
                    balance=balance,
                )
            )
            session.flush()
            if balance > 0:
                has_topup = session.execute(
                    text(
                        "SELECT COUNT(*) FROM balance_transaction "
                        "WHERE user_id = :uid AND currency = :cur "
                        "AND type = :t AND correlation_id = :cid"
                    ),
                    {
                        "uid": user_id,
                        "cur": WALLET_CURRENCY_CNY,
                        "t": TRANSACTION_TYPE_TOPUP,
                        "cid": f"migrate:user:{user_id}",
                    },
                ).scalar()
                if not has_topup:
                    session.add(
                        BalanceTransaction(
                            user_id=user_id,
                            currency=WALLET_CURRENCY_CNY,
                            type=TRANSACTION_TYPE_TOPUP,
                            amount=balance,
                            balance_after=balance,
                            correlation_id=f"migrate:user:{user_id}",
                            note="迁移 user.balance 到 CNY 钱包",
                        )
                    )
            migrated += 1
        session.commit()
        print(f"[wallet] migrated {migrated} user(s) into CNY wallet")

    print("wallet ledger migration complete")


if __name__ == "__main__":
    main()
