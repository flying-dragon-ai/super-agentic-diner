"""Idempotent MySQL migration: order line items + header expansion.

Creates ``order_item`` / ``order_item_option`` if missing, backfills each
existing ``order`` row into a single ``order_item`` row, relaxes the legacy
``order.coffee_name`` / ``order.amount`` columns to nullable, and widens the
order status / payment CHECK constraints to include cancelled / refunded.

Safe to run more than once.

Usage: python scripts/migrate_order_lineitem.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine  # noqa: E402
from app.db.models import OrderItem, OrderItemOption  # noqa: E402
from app.domain_constants import ORDER_PAYMENT_STATUSES, ORDER_STATUSES  # noqa: E402


def _ensure_mysql() -> None:
    if engine.dialect.name != "mysql":
        raise RuntimeError(
            f"This migration is MySQL-only; current dialect is {engine.dialect.name!r}."
        )


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ),
            {"t": table_name, "c": column_name},
        ).scalar()
    )


def _check_exists(conn, table_name: str, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = :t "
                "AND CONSTRAINT_NAME = :c AND CONSTRAINT_TYPE = 'CHECK'"
            ),
            {"t": table_name, "c": constraint_name},
        ).scalar()
    )


def _sql_ints(values) -> str:
    return ", ".join(str(v) for v in sorted(values))


def _sql_strings(values) -> str:
    return ", ".join(f"'{v}'" for v in sorted(values))


def main() -> None:
    _ensure_mysql()
    inspector = inspect(engine)

    # 1) Create order_item / order_item_option if missing.
    for model in (OrderItem, OrderItemOption):
        if not _table_exists(inspector, model.__tablename__):
            print(f"[lineitem] creating table {model.__tablename__}")
            model.__table__.create(engine, checkfirst=True)
        else:
            print(f"[lineitem] table {model.__tablename__} already exists")

    # 2) Add header columns + relax legacy columns (DDL via raw connection).
    with engine.begin() as conn:
        for column, definition in (
            ("total_amount", "DECIMAL(10, 2) NULL"),
            ("cancelled_at", "DATETIME NULL"),
            ("refunded_at", "DATETIME NULL"),
        ):
            if not _column_exists(conn, "order", column):
                conn.execute(text(f"ALTER TABLE `order` ADD COLUMN `{column}` {definition}"))
                print(f"[lineitem] added column order.{column}")
            else:
                print(f"[lineitem] column order.{column} already exists")

        for column, ddl in (
            ("coffee_name", "VARCHAR(128) NULL"),
            ("amount", "DECIMAL(10, 2) NULL"),
        ):
            conn.execute(text(f"ALTER TABLE `order` MODIFY COLUMN `{column}` {ddl}"))
            print(f"[lineitem] relaxed order.{column} to nullable")

    # 3) Backfill one order_item per existing order row via ORM (Python defaults).
    with Session(engine) as session:
        existing_items = session.execute(text("SELECT COUNT(*) FROM order_item")).scalar()
        if existing_items == 0:
            rows = session.execute(
                text(
                    "SELECT order_id, coffee_name, amount FROM `order` "
                    "WHERE coffee_name IS NOT NULL AND amount IS NOT NULL"
                )
            ).fetchall()
            for order_id, coffee_name, amount in rows:
                product_id = session.execute(
                    text("SELECT product_id FROM product WHERE name = :name"),
                    {"name": coffee_name},
                ).scalar()
                session.add(
                    OrderItem(
                        order_id=order_id,
                        product_id=product_id,
                        product_name_snapshot=coffee_name,
                        unit_price=amount,
                        quantity=1,
                        line_total=amount,
                    )
                )
            session.commit()
            print(f"[lineitem] backfilled {len(rows)} order_item row(s)")
        else:
            print(f"[lineitem] order_item already populated ({existing_items} rows)")

    # 4) Widen order status / payment CHECK constraints.
    with engine.begin() as conn:
        if _check_exists(conn, "order", "ck_order_status"):
            conn.execute(text("ALTER TABLE `order` DROP CHECK `ck_order_status`"))
        conn.execute(
            text(
                "ALTER TABLE `order` ADD CONSTRAINT `ck_order_status` "
                f"CHECK (status IN ({_sql_ints(ORDER_STATUSES)}))"
            )
        )
        print("[lineitem] widened ck_order_status")

        if _check_exists(conn, "order", "ck_order_payment_status"):
            conn.execute(text("ALTER TABLE `order` DROP CHECK `ck_order_payment_status`"))
        conn.execute(
            text(
                "ALTER TABLE `order` ADD CONSTRAINT `ck_order_payment_status` "
                f"CHECK (payment_status IN ({_sql_strings(ORDER_PAYMENT_STATUSES)}))"
            )
        )
        print("[lineitem] widened ck_order_payment_status")

    print("order line-item migration complete")


if __name__ == "__main__":
    main()
