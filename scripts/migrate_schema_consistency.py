"""Idempotent schema consistency migration for SQLite and MySQL.

This script is intentionally conservative:

* create missing ORM tables;
* add only known, safe additive columns used by older deployments;
* backfill compatibility values where the data can be inferred;
* create declared SQLAlchemy indexes;
* soft-retire known dead tables by renaming them to ``*_deprecated``.

It never drops application data. Existing MySQL CHECK/FK repair is limited to
cases where current data can satisfy the new constraint.

Usage:
    python scripts/migrate_schema_consistency.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import models  # noqa: F401,E402 - register SQLAlchemy models
from app.db.database import Base, engine  # noqa: E402
from app.domain_constants import (  # noqa: E402
    IDENTITY_STATUSES,
    LEDGER_PAYMENT_STATUSES,
    ORDER_PAYMENT_STATUSES,
    ORDER_SOURCE_TYPES,
    ORDER_SOURCE_WEB_DIALOG,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_PAID,
    ORDER_STATUSES,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PAYMENT_FAILED,
    PAYMENT_STATUS_PAYMENT_PENDING,
)


@dataclass(frozen=True)
class AddColumn:
    table: str
    column: str
    sqlite: str
    mysql: str
    generic: str | None = None

    def ddl(self, dialect: str) -> str | None:
        if dialect == "sqlite":
            return self.sqlite
        if dialect == "mysql":
            return self.mysql
        return self.generic


KNOWN_ADDITIVE_COLUMNS: tuple[AddColumn, ...] = (
    AddColumn(
        "order",
        "source_type",
        f"VARCHAR(32) NOT NULL DEFAULT '{ORDER_SOURCE_WEB_DIALOG}'",
        f"VARCHAR(32) NOT NULL DEFAULT '{ORDER_SOURCE_WEB_DIALOG}'",
    ),
    AddColumn(
        "order",
        "payment_status",
        f"VARCHAR(32) NOT NULL DEFAULT '{PAYMENT_STATUS_PAID}'",
        f"VARCHAR(32) NOT NULL DEFAULT '{PAYMENT_STATUS_PAID}'",
    ),
    AddColumn("order", "consumer_url", "VARCHAR(512) NULL", "VARCHAR(512) NULL"),
    AddColumn("order", "consumer_id", "BIGINT NULL", "BIGINT NULL"),
    AddColumn("order", "agent_id", "BIGINT NULL", "BIGINT NULL"),
    AddColumn("order", "ledger_id", "BIGINT NULL", "BIGINT NULL"),
    AddColumn("order", "correlation_id", "VARCHAR(128) NULL", "VARCHAR(128) NULL"),
    AddColumn("order", "total_amount", "DECIMAL(10, 2) NULL", "DECIMAL(10, 2) NULL"),
    AddColumn("order", "cancelled_at", "DATETIME NULL", "DATETIME NULL"),
    AddColumn("order", "refunded_at", "DATETIME NULL", "DATETIME NULL"),
    AddColumn(
        "order",
        "updated_at",
        "DATETIME NULL",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    ),
    AddColumn(
        "coffee_kb",
        "updated_at",
        "DATETIME NULL",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    ),
    AddColumn(
        "agent_profile",
        "updated_at",
        "DATETIME NULL",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    ),
    AddColumn(
        "visualization_event",
        "updated_at",
        "DATETIME NULL",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    ),
    AddColumn(
        "evomap_consumer",
        "updated_at",
        "DATETIME NULL",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    ),
    AddColumn(
        "user_account",
        "status",
        "VARCHAR(16) NOT NULL DEFAULT 'active'",
        "VARCHAR(16) NOT NULL DEFAULT 'active'",
    ),
)

SOFT_RETIRED_TABLES = ("chat_messages", "pending_orders")


def _quote(name: str) -> str:
    return engine.dialect.identifier_preparer.quote(name)


def _sql_strings(values) -> str:
    return ", ".join(f"'{str(value).replace(chr(39), chr(39) * 2)}'" for value in sorted(values))


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _create_missing_tables() -> None:
    existing = set(inspect(engine).get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name in existing:
            print(f"[tables] {table.name} exists")
            continue
        table.create(bind=engine, checkfirst=True)
        print(f"[tables] created {table.name}")
        existing.add(table.name)


def _add_known_columns(conn) -> None:
    dialect = engine.dialect.name
    for migration in KNOWN_ADDITIVE_COLUMNS:
        if migration.table not in _table_names(conn):
            print(f"[columns] {migration.table} missing; skip {migration.column}")
            continue
        if migration.column in _column_names(conn, migration.table):
            print(f"[columns] {migration.table}.{migration.column} exists")
            continue
        definition = migration.ddl(dialect)
        if definition is None:
            print(
                f"[columns] {migration.table}.{migration.column} skipped for dialect {dialect}"
            )
            continue
        conn.execute(
            text(
                f"ALTER TABLE {_quote(migration.table)} "
                f"ADD COLUMN {_quote(migration.column)} {definition}"
            )
        )
        print(f"[columns] added {migration.table}.{migration.column}")


def _backfill_order(conn) -> None:
    tables = _table_names(conn)
    if "order" not in tables:
        return
    columns = _column_names(conn, "order")
    order_table = _quote("order")

    if "source_type" in columns:
        conn.execute(
            text(
                f"UPDATE {order_table} "
                "SET source_type = :source_type "
                "WHERE source_type IS NULL OR source_type = ''"
            ),
            {"source_type": ORDER_SOURCE_WEB_DIALOG},
        )
        print("[backfill] order.source_type")

    if "payment_status" in columns and "status" in columns:
        conn.execute(
            text(
                f"UPDATE {order_table} "
                "SET payment_status = CASE "
                "WHEN status = :paid_status THEN :paid_payment "
                "WHEN status = :failed_status THEN :failed_payment "
                "ELSE :pending_payment END "
                "WHERE payment_status IS NULL OR payment_status = ''"
            ),
            {
                "paid_status": ORDER_STATUS_PAID,
                "failed_status": ORDER_STATUS_FAILED,
                "paid_payment": PAYMENT_STATUS_PAID,
                "failed_payment": PAYMENT_STATUS_PAYMENT_FAILED,
                "pending_payment": PAYMENT_STATUS_PAYMENT_PENDING,
            },
        )
        print("[backfill] order.payment_status")

    if {"total_amount", "amount"}.issubset(columns):
        conn.execute(
            text(
                f"UPDATE {order_table} "
                "SET total_amount = amount "
                "WHERE total_amount IS NULL AND amount IS NOT NULL"
            )
        )
        print("[backfill] order.total_amount")


def _backfill_updated_at(conn) -> None:
    for table_name in ("order", "coffee_kb", "agent_profile", "visualization_event", "evomap_consumer"):
        if table_name not in _table_names(conn):
            continue
        if "updated_at" not in _column_names(conn, table_name):
            continue
        conn.execute(
            text(
                f"UPDATE {_quote(table_name)} "
                "SET updated_at = CURRENT_TIMESTAMP "
                "WHERE updated_at IS NULL"
            )
        )
        print(f"[backfill] {table_name}.updated_at")


def _create_indexes() -> None:
    for table in Base.metadata.sorted_tables:
        for index in sorted(table.indexes, key=lambda idx: idx.name or ""):
            index.create(bind=engine, checkfirst=True)
            print(f"[indexes] ensured {table.name}.{index.name}")


def _soft_retire_tables(conn) -> None:
    for table_name in SOFT_RETIRED_TABLES:
        tables = _table_names(conn)
        deprecated = f"{table_name}_deprecated"
        if table_name not in tables:
            print(f"[retire] {table_name} not found")
            continue
        if deprecated in tables:
            print(f"[retire] {deprecated} already exists; keep {table_name} untouched")
            continue
        conn.execute(
            text(
                f"ALTER TABLE {_quote(table_name)} "
                f"RENAME TO {_quote(deprecated)}"
            )
        )
        print(f"[retire] {table_name} -> {deprecated}")


def _mysql_check_clause(conn, constraint_name: str) -> str | None:
    row = conn.execute(
        text(
            "SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = :name"
        ),
        {"name": constraint_name},
    ).fetchone()
    return row[0] if row else None


def _mysql_check_exists(conn, table_name: str, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table_name "
                "AND CONSTRAINT_NAME = :constraint_name "
                "AND CONSTRAINT_TYPE = 'CHECK'"
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).scalar()
    )


def _mysql_fk_exists(
    conn,
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str,
) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table_name "
                "AND COLUMN_NAME = :column_name "
                "AND REFERENCED_TABLE_NAME = :referred_table "
                "AND REFERENCED_COLUMN_NAME = :referred_column"
            ),
            {
                "table_name": table_name,
                "column_name": column_name,
                "referred_table": referred_table,
                "referred_column": referred_column,
            },
        ).scalar()
    )


def _mysql_bad_check_rows(conn, table_name: str, expression: str) -> int:
    return int(
        conn.execute(
            text(
                f"SELECT COUNT(*) FROM {_quote(table_name)} "
                f"WHERE NOT ({expression})"
            )
        ).scalar()
        or 0
    )


def _mysql_ensure_check(
    conn,
    table_name: str,
    constraint_name: str,
    expression: str,
    required_tokens: tuple[str, ...],
) -> None:
    if table_name not in _table_names(conn):
        print(f"[mysql-check] {table_name} missing; skip {constraint_name}")
        return
    bad_rows = _mysql_bad_check_rows(conn, table_name, expression)
    if bad_rows:
        print(
            f"[mysql-check] {constraint_name} skipped; {bad_rows} row(s) violate target expression"
        )
        return

    clause = _mysql_check_clause(conn, constraint_name)
    if clause and all(token in clause for token in required_tokens):
        print(f"[mysql-check] {constraint_name} already current")
        return
    if _mysql_check_exists(conn, table_name, constraint_name):
        conn.execute(
            text(f"ALTER TABLE {_quote(table_name)} DROP CHECK {_quote(constraint_name)}")
        )
        print(f"[mysql-check] dropped stale {constraint_name}")
    conn.execute(
        text(
            f"ALTER TABLE {_quote(table_name)} "
            f"ADD CONSTRAINT {_quote(constraint_name)} CHECK ({expression})"
        )
    )
    print(f"[mysql-check] added {constraint_name}")


def _mysql_orphan_count(
    conn,
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str,
) -> int:
    return int(
        conn.execute(
            text(
                f"SELECT COUNT(*) FROM {_quote(table_name)} AS child "
                f"LEFT JOIN {_quote(referred_table)} AS parent "
                f"ON child.{_quote(column_name)} = parent.{_quote(referred_column)} "
                f"WHERE child.{_quote(column_name)} IS NOT NULL "
                f"AND parent.{_quote(referred_column)} IS NULL"
            )
        ).scalar()
        or 0
    )


def _mysql_ensure_fk(
    conn,
    constraint_name: str,
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str,
) -> None:
    tables = _table_names(conn)
    if table_name not in tables or referred_table not in tables:
        print(f"[mysql-fk] {constraint_name} skipped; table missing")
        return
    if column_name not in _column_names(conn, table_name):
        print(f"[mysql-fk] {constraint_name} skipped; column missing")
        return
    if _mysql_fk_exists(conn, table_name, column_name, referred_table, referred_column):
        print(f"[mysql-fk] {constraint_name} exists")
        return
    orphan_count = _mysql_orphan_count(
        conn, table_name, column_name, referred_table, referred_column
    )
    if orphan_count:
        print(f"[mysql-fk] {constraint_name} skipped; {orphan_count} orphan row(s)")
        return
    conn.execute(
        text(
            f"ALTER TABLE {_quote(table_name)} "
            f"ADD CONSTRAINT {_quote(constraint_name)} "
            f"FOREIGN KEY ({_quote(column_name)}) "
            f"REFERENCES {_quote(referred_table)} ({_quote(referred_column)})"
        )
    )
    print(f"[mysql-fk] added {constraint_name}")


def _mysql_reconcile_constraints(conn) -> None:
    if engine.dialect.name != "mysql":
        print(f"[constraints] dialect {engine.dialect.name}; existing-table CHECK/FK repair skipped")
        return

    _mysql_ensure_check(
        conn,
        "order",
        "ck_order_source_type",
        f"source_type IN ({_sql_strings(ORDER_SOURCE_TYPES)})",
        tuple(sorted(ORDER_SOURCE_TYPES)),
    )
    _mysql_ensure_check(
        conn,
        "order",
        "ck_order_status",
        f"status IN ({', '.join(str(value) for value in sorted(ORDER_STATUSES))})",
        tuple(str(value) for value in sorted(ORDER_STATUSES)),
    )
    _mysql_ensure_check(
        conn,
        "order",
        "ck_order_payment_status",
        f"payment_status IN ({_sql_strings(ORDER_PAYMENT_STATUSES)})",
        tuple(sorted(ORDER_PAYMENT_STATUSES)),
    )
    _mysql_ensure_check(
        conn,
        "skill_order_ledger",
        "ck_skill_order_ledger_payment_status",
        f"payment_status IN ({_sql_strings(LEDGER_PAYMENT_STATUSES)})",
        tuple(sorted(LEDGER_PAYMENT_STATUSES)),
    )
    _mysql_ensure_check(
        conn,
        "user_account",
        "ck_user_account_status",
        f"status IN ({_sql_strings(IDENTITY_STATUSES)})",
        tuple(sorted(IDENTITY_STATUSES)),
    )
    _mysql_ensure_check(
        conn,
        "agent_profile",
        "ck_agent_profile_status",
        f"status IN ({_sql_strings(IDENTITY_STATUSES)})",
        tuple(sorted(IDENTITY_STATUSES)),
    )
    _mysql_ensure_check(
        conn,
        "evomap_consumer",
        "ck_evomap_consumer_status",
        f"status IN ({_sql_strings(IDENTITY_STATUSES)})",
        tuple(sorted(IDENTITY_STATUSES)),
    )

    for constraint_name, column_name, referred_table, referred_column in (
        ("fk_order_consumer_id", "consumer_id", "evomap_consumer", "consumer_id"),
        ("fk_order_agent_id", "agent_id", "agent_profile", "agent_id"),
        ("fk_order_ledger_id", "ledger_id", "skill_order_ledger", "ledger_id"),
    ):
        _mysql_ensure_fk(
            conn,
            constraint_name,
            "order",
            column_name,
            referred_table,
            referred_column,
        )


def main() -> None:
    print(f"[schema] dialect={engine.dialect.name}")
    _create_missing_tables()
    with engine.begin() as conn:
        _add_known_columns(conn)
        _backfill_order(conn)
        _backfill_updated_at(conn)
    _create_indexes()
    with engine.begin() as conn:
        _soft_retire_tables(conn)
        _mysql_reconcile_constraints(conn)
    print("[schema] consistency migration complete")


if __name__ == "__main__":
    main()
