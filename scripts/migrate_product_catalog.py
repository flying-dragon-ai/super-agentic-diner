"""Idempotent MySQL migration: normalized product catalog (replaces coffee_kb).

Creates ``product`` / ``product_option_group`` / ``product_option`` if missing,
backfills them from the legacy ``coffee_kb`` rows, and is safe to run more than
once. ``coffee_kb`` is left in place for rollback; new code reads ``product``.

Usage: python scripts/migrate_product_catalog.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine  # noqa: E402
from app.db.models import Product, ProductOption, ProductOptionGroup  # noqa: E402
from app.domain_constants import PRODUCT_STATUS_AVAILABLE  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


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

    # 1) Create tables if missing (uses the SQLAlchemy models' DDL verbatim).
    for model in (Product, ProductOptionGroup, ProductOption):
        if not _table_exists(inspector, model.__tablename__):
            print(f"[catalog] creating table {model.__tablename__}")
            model.__table__.create(engine, checkfirst=True)
        else:
            print(f"[catalog] table {model.__tablename__} already exists")

    # 2) Backfill product rows from legacy coffee_kb (idempotent on coffee_name).
    # Use the ORM session so Python-side defaults (created_at/updated_at) apply.
    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT coffee_name, content, price, tags FROM coffee_kb "
                "WHERE coffee_name IS NOT NULL"
            )
        ).fetchall()
        inserted = 0
        for coffee_name, content, price, tags in rows:
            existing = session.execute(
                text("SELECT COUNT(*) FROM product WHERE name = :name"),
                {"name": coffee_name},
            ).scalar()
            if existing:
                continue
            sku = str(coffee_name).upper().replace(" ", "-")
            sku_taken = session.execute(
                text("SELECT COUNT(*) FROM product WHERE sku = :sku"),
                {"sku": sku},
            ).scalar()
            if sku_taken:
                sku = f"{sku}-{coffee_name}"
            session.add(
                Product(
                    sku=sku,
                    name=coffee_name,
                    category="咖啡",
                    description=content or "",
                    base_price=price or 0,
                    tags=tags,
                    status=PRODUCT_STATUS_AVAILABLE,
                    stock=0,
                )
            )
            inserted += 1
        session.commit()
        print(f"[catalog] backfilled {inserted} product row(s) from coffee_kb")

    print("product catalog migration complete")


if __name__ == "__main__":
    main()
