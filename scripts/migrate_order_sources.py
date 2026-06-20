"""MySQL-only migration for order source, payment state, and FK consistency.

Run this after deploying model changes to an existing MySQL database:

    python scripts/migrate_order_sources.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine  # noqa: E402
from app.domain_constants import (  # noqa: E402
    IDENTITY_STATUSES,
    LEDGER_PAYMENT_STATUSES,
    ORDER_PAYMENT_STATUSES,
    ORDER_SOURCE_TYPES,
    ORDER_SOURCE_WEB_DIALOG,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PAYMENT_FAILED,
    PAYMENT_STATUS_PAYMENT_PENDING,
)


def _sql_strings(values) -> str:
    return ", ".join(f"'{str(value)}'" for value in sorted(values))


ORDER_TABLE = "`order`"

TABLE_COLUMNS = {
    "order": {
        "source_type": f"VARCHAR(32) NOT NULL DEFAULT '{ORDER_SOURCE_WEB_DIALOG}'",
        "payment_status": f"VARCHAR(32) NOT NULL DEFAULT '{PAYMENT_STATUS_PAID}'",
        "consumer_url": "VARCHAR(512) NULL",
        "consumer_id": "BIGINT NULL",
        "agent_id": "BIGINT NULL",
        "ledger_id": "BIGINT NULL",
        "correlation_id": "VARCHAR(128) NULL",
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "coffee_kb": {
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "agent_profile": {
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "visualization_event": {
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "evomap_consumer": {
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
}

INDEXES = {
    "order": {
        "idx_order_source_created": "`source_type`, `created_at`",
        "idx_order_payment_status": "`payment_status`",
        "idx_order_consumer_url": "`consumer_url`",
        "idx_order_consumer": "`consumer_id`",
        "idx_order_agent": "`agent_id`",
        "idx_order_ledger": "`ledger_id`",
        "idx_order_correlation": "`correlation_id`",
    },
}

CHECKS = {
    "order": {
        "ck_order_source_type": f"source_type IN ({_sql_strings(ORDER_SOURCE_TYPES)})",
        "ck_order_status": (
            "status IN "
            f"({', '.join(str(value) for value in sorted({ORDER_STATUS_PENDING, ORDER_STATUS_PAID, ORDER_STATUS_FAILED}))})"
        ),
        "ck_order_payment_status": f"payment_status IN ({_sql_strings(ORDER_PAYMENT_STATUSES)})",
    },
    "agent_profile": {
        "ck_agent_profile_status": f"status IN ({_sql_strings(IDENTITY_STATUSES)})",
    },
    "evomap_consumer": {
        "ck_evomap_consumer_status": f"status IN ({_sql_strings(IDENTITY_STATUSES)})",
    },
    "skill_order_ledger": {
        "ck_skill_order_ledger_payment_status": (
            f"payment_status IN ({_sql_strings(LEDGER_PAYMENT_STATUSES)})"
        ),
    },
}

ORDER_FOREIGN_KEYS = {
    "fk_order_consumer_id": ("consumer_id", "evomap_consumer", "consumer_id"),
    "fk_order_agent_id": ("agent_id", "agent_profile", "agent_id"),
    "fk_order_ledger_id": ("ledger_id", "skill_order_ledger", "ledger_id"),
}


def _ensure_mysql() -> None:
    if engine.dialect.name != "mysql":
        raise RuntimeError(
            f"This migration is MySQL-only; current dialect is {engine.dialect.name!r}."
        )


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return bool(result.scalar())


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(result.scalar())


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND INDEX_NAME = :index_name
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    )
    return bool(result.scalar())


def _check_exists(conn, table_name: str, constraint_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND CONSTRAINT_NAME = :constraint_name
              AND CONSTRAINT_TYPE = 'CHECK'
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    )
    return bool(result.scalar())


def _foreign_key_exists(
    conn,
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str,
) -> bool:
    result = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
              AND REFERENCED_TABLE_NAME = :referred_table
              AND REFERENCED_COLUMN_NAME = :referred_column
            """
        ),
        {
            "table_name": table_name,
            "column_name": column_name,
            "referred_table": referred_table,
            "referred_column": referred_column,
        },
    )
    return bool(result.scalar())


def _ensure_columns(conn) -> None:
    for table_name, columns in TABLE_COLUMNS.items():
        if not _table_exists(conn, table_name):
            print(f"table {table_name} missing; skipped column migration")
            continue
        table_sql = f"`{table_name}`"
        for column_name, definition in columns.items():
            if not _column_exists(conn, table_name, column_name):
                conn.execute(text(f"ALTER TABLE {table_sql} ADD COLUMN `{column_name}` {definition}"))
                print(f"added column {table_name}.{column_name}")
            else:
                print(f"column {table_name}.{column_name} already exists")


def _backfill_order(conn) -> None:
    conn.execute(
        text(
            f"""
            UPDATE {ORDER_TABLE}
            SET source_type = :source_type
            WHERE source_type IS NULL OR source_type = ''
            """
        ),
        {"source_type": ORDER_SOURCE_WEB_DIALOG},
    )
    conn.execute(
        text(
            f"""
            UPDATE {ORDER_TABLE} AS o
            LEFT JOIN skill_order_ledger AS l ON l.ledger_id = o.ledger_id
            SET o.payment_status = CASE
                WHEN l.payment_status IS NOT NULL THEN l.payment_status
                WHEN o.status = :paid_status THEN :paid_payment
                WHEN o.status = :failed_status THEN :failed_payment
                ELSE :pending_payment
            END
            WHERE o.payment_status IS NULL OR o.payment_status = ''
            """
        ),
        {
            "paid_status": ORDER_STATUS_PAID,
            "failed_status": ORDER_STATUS_FAILED,
            "paid_payment": PAYMENT_STATUS_PAID,
            "failed_payment": PAYMENT_STATUS_PAYMENT_FAILED,
            "pending_payment": PAYMENT_STATUS_PAYMENT_PENDING,
        },
    )


def _ensure_indexes(conn) -> None:
    for table_name, indexes in INDEXES.items():
        if not _table_exists(conn, table_name):
            print(f"table {table_name} missing; skipped index migration")
            continue
        table_sql = f"`{table_name}`"
        for index_name, columns in indexes.items():
            if not _index_exists(conn, table_name, index_name):
                conn.execute(text(f"CREATE INDEX `{index_name}` ON {table_sql} ({columns})"))
                print(f"added index {table_name}.{index_name}")
            else:
                print(f"index {table_name}.{index_name} already exists")


def _assert_no_orphans(
    conn,
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str,
) -> None:
    result = conn.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM `{table_name}` AS child
            LEFT JOIN `{referred_table}` AS parent
              ON child.`{column_name}` = parent.`{referred_column}`
            WHERE child.`{column_name}` IS NOT NULL
              AND parent.`{referred_column}` IS NULL
            """
        )
    )
    count = int(result.scalar() or 0)
    if count:
        raise RuntimeError(
            f"Cannot add FK {table_name}.{column_name} -> "
            f"{referred_table}.{referred_column}: {count} orphan row(s) found."
        )


def _ensure_order_foreign_keys(conn) -> None:
    if not _table_exists(conn, "order"):
        print("table order missing; skipped FK migration")
        return
    for constraint_name, (column_name, referred_table, referred_column) in ORDER_FOREIGN_KEYS.items():
        if _foreign_key_exists(conn, "order", column_name, referred_table, referred_column):
            print(f"foreign key order.{column_name} already exists")
            continue
        _assert_no_orphans(conn, "order", column_name, referred_table, referred_column)
        conn.execute(
            text(
                f"""
                ALTER TABLE {ORDER_TABLE}
                ADD CONSTRAINT `{constraint_name}`
                FOREIGN KEY (`{column_name}`)
                REFERENCES `{referred_table}` (`{referred_column}`)
                """
            )
        )
        print(f"added foreign key {constraint_name}")


def _ensure_checks(conn) -> None:
    for table_name, checks in CHECKS.items():
        if not _table_exists(conn, table_name):
            print(f"table {table_name} missing; skipped check migration")
            continue
        table_sql = f"`{table_name}`"
        for constraint_name, expression in checks.items():
            if _check_exists(conn, table_name, constraint_name):
                print(f"check {table_name}.{constraint_name} already exists")
                continue
            conn.execute(
                text(
                    f"""
                    ALTER TABLE {table_sql}
                    ADD CONSTRAINT `{constraint_name}`
                    CHECK ({expression})
                    """
                )
            )
            print(f"added check {table_name}.{constraint_name}")


def main() -> None:
    _ensure_mysql()
    with engine.begin() as conn:
        _ensure_columns(conn)
        _backfill_order(conn)
        _ensure_indexes(conn)
        _ensure_order_foreign_keys(conn)
        _ensure_checks(conn)

    print("order source/payment migration complete")


if __name__ == "__main__":
    main()
