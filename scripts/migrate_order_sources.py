"""Canonical, idempotent schema migration entrypoint for SQLite and MySQL.

Run this command before starting the application::

    python scripts/migrate_order_sources.py

The runner is deliberately additive. It creates missing ORM tables, adds known
columns, backfills only deterministic defaults, repairs supported constraints,
and records ordered migration versions. It never seeds demo/business data and
never deletes application rows. Existing foreign-key violations are reported;
unrelated legacy violations are not automatically changed.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateTable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import models  # noqa: F401,E402 - register all ORM tables
from app.db.database import Base, engine  # noqa: E402
from app.domain_constants import (  # noqa: E402
    ACCOUNT_ROLES,
    IDENTITY_STATUSES,
    LEDGER_PAYMENT_STATUSES,
    ORDER_PAYMENT_STATUSES,
    ORDER_SOURCE_TYPES,
    ORDER_SOURCE_WEB_DIALOG,
    ORDER_STATUSES,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_PAID,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PAYMENT_FAILED,
    PAYMENT_STATUS_PAYMENT_PENDING,
    STOCK_RESERVATION_STATUSES,
)


MIGRATION_TABLE = "schema_migration"
ORDER_TABLE = "`order`"


@dataclass(frozen=True)
class AddColumn:
    table: str
    column: str
    sqlite: str
    mysql: str

    def ddl(self, dialect: str) -> str:
        return self.mysql if dialect == "mysql" else self.sqlite


ADDITIVE_COLUMNS: tuple[AddColumn, ...] = (
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
    AddColumn("agent_profile", "consumer_id", "BIGINT NULL", "BIGINT NULL"),
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
    AddColumn("user_account", "gender", "VARCHAR(16) NULL", "VARCHAR(16) NULL"),
    AddColumn("user_account", "specialty", "VARCHAR(128) NULL", "VARCHAR(128) NULL"),
    AddColumn("user_account", "profession", "VARCHAR(128) NULL", "VARCHAR(128) NULL"),
    AddColumn(
        "user_account",
        "role",
        "VARCHAR(16) NOT NULL DEFAULT 'user'",
        "VARCHAR(16) NOT NULL DEFAULT 'user'",
    ),
    AddColumn(
        "user_account",
        "session_version",
        "INTEGER NOT NULL DEFAULT 0",
        "INT NOT NULL DEFAULT 0",
    ),
    AddColumn(
        "office_layout",
        "version",
        "INTEGER NOT NULL DEFAULT 1",
        "INT NOT NULL DEFAULT 1",
    ),
    AddColumn(
        "skill_order_ledger",
        "version",
        "INTEGER NOT NULL DEFAULT 0",
        "INT NOT NULL DEFAULT 0",
    ),
    AddColumn(
        "skill_order_ledger",
        "payment_attempts",
        "INTEGER NOT NULL DEFAULT 0",
        "INT NOT NULL DEFAULT 0",
    ),
    AddColumn(
        "skill_order_ledger",
        "stock_reservation_json",
        "TEXT NULL",
        "TEXT NULL",
    ),
    AddColumn(
        "skill_order_ledger",
        "stock_reservation_status",
        "VARCHAR(16) NULL",
        "VARCHAR(16) NULL",
    ),
    AddColumn(
        "skill_order_ledger",
        "amount_cny",
        "DECIMAL(10, 2) NULL",
        "DECIMAL(10, 2) NULL",
    ),
)


CUSTOM_INDEXES = {
    "agent_profile": {
        "idx_agent_consumer": ("consumer_id",),
    },
}

ORDER_FOREIGN_KEYS = {
    "fk_order_consumer_id": ("order", "consumer_id", "evomap_consumer", "consumer_id"),
    "fk_order_agent_id": ("order", "agent_id", "agent_profile", "agent_id"),
    "fk_order_ledger_id": ("order", "ledger_id", "skill_order_ledger", "ledger_id"),
    "fk_agent_profile_consumer_id": (
        "agent_profile",
        "consumer_id",
        "evomap_consumer",
        "consumer_id",
    ),
}


def _sql_strings(values: Iterable[object]) -> str:
    return ", ".join(
        f"'{str(value).replace(chr(39), chr(39) * 2)}'" for value in sorted(values)
    )


def _quote(bind: Engine | Connection, name: str) -> str:
    return bind.dialect.identifier_preparer.quote(name)


def _table_names(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn: Connection, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _index_names(conn: Connection, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    names = {index.get("name") for index in inspect(conn).get_indexes(table_name)}
    return {name for name in names if name}


# The following MySQL information_schema helpers intentionally keep their
# stable names because focused migration tests import them directly.
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


def _unique_index_on_column_exists(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
              AND NON_UNIQUE = 0
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(result.scalar())


def _ensure_office_layout_table(conn) -> None:
    """Ensure the global 3D editor layout table exists in existing MySQL DBs."""
    if not _table_exists(conn, "office_layout"):
        conn.execute(
            text(
                """
                CREATE TABLE `office_layout` (
                  `layout_id` BIGINT NOT NULL AUTO_INCREMENT,
                  `namespace` VARCHAR(32) NOT NULL,
                  `layout_json` TEXT NOT NULL,
                  `version` INT NOT NULL DEFAULT 1,
                  `updated_at` DATETIME NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`layout_id`),
                  UNIQUE KEY `uq_office_layout_namespace` (`namespace`),
                  KEY `idx_office_layout_namespace` (`namespace`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        )
        print("[tables] created office_layout")
        return

    print("[tables] office_layout exists")
    if not _unique_index_on_column_exists(conn, "office_layout", "namespace"):
        conn.execute(
            text(
                """
                ALTER TABLE `office_layout`
                ADD CONSTRAINT `uq_office_layout_namespace`
                UNIQUE (`namespace`)
                """
            )
        )
        print("[indexes] added office_layout.uq_office_layout_namespace")
    else:
        print("[indexes] office_layout namespace uniqueness exists")
    if not _index_exists(conn, "office_layout", "idx_office_layout_namespace"):
        conn.execute(
            text(
                """
                CREATE INDEX `idx_office_layout_namespace`
                ON `office_layout` (`namespace`)
                """
            )
        )
        print("[indexes] added office_layout.idx_office_layout_namespace")
    else:
        print("[indexes] office_layout.idx_office_layout_namespace exists")


def _ensure_migration_table(bind: Engine) -> None:
    with bind.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {_quote(bind, MIGRATION_TABLE)} (
                    version VARCHAR(96) NOT NULL PRIMARY KEY,
                    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def _migration_recorded(bind: Engine, version: str) -> bool:
    with bind.connect() as conn:
        return bool(
            conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {_quote(bind, MIGRATION_TABLE)} "
                    "WHERE version = :version"
                ),
                {"version": version},
            ).scalar()
        )


def _record_migration(bind: Engine, version: str) -> None:
    with bind.begin() as conn:
        insert_keyword = "INSERT OR IGNORE" if bind.dialect.name == "sqlite" else "INSERT IGNORE"
        conn.execute(
            text(
                f"{insert_keyword} INTO {_quote(bind, MIGRATION_TABLE)} (version) "
                "VALUES (:version)"
            ),
            {"version": version},
        )


def _create_declared_tables(bind: Engine) -> None:
    Base.metadata.create_all(bind)
    print("[tables] all declared ORM tables ensured")
    if bind.dialect.name == "mysql":
        with bind.begin() as conn:
            _ensure_office_layout_table(conn)


def _ensure_additive_columns(bind: Engine) -> None:
    dialect = bind.dialect.name
    with bind.begin() as conn:
        for migration in ADDITIVE_COLUMNS:
            if migration.table not in _table_names(conn):
                print(f"[columns] {migration.table} missing; skipped {migration.column}")
                continue
            if migration.column in _column_names(conn, migration.table):
                print(f"[columns] {migration.table}.{migration.column} exists")
                continue
            conn.execute(
                text(
                    f"ALTER TABLE {_quote(bind, migration.table)} "
                    f"ADD COLUMN {_quote(bind, migration.column)} {migration.ddl(dialect)}"
                )
            )
            print(f"[columns] added {migration.table}.{migration.column}")

        _backfill_compatibility_values(conn)

    if dialect == "mysql":
        _ensure_mysql_request_id_length(bind)


def _backfill_compatibility_values(conn: Connection) -> None:
    tables = _table_names(conn)
    if "order" in tables:
        columns = _column_names(conn, "order")
        order_table = _quote(conn, "order")
        if "source_type" in columns:
            conn.execute(
                text(
                    f"UPDATE {order_table} SET source_type = :source_type "
                    "WHERE source_type IS NULL OR source_type = ''"
                ),
                {"source_type": ORDER_SOURCE_WEB_DIALOG},
            )
        if {"payment_status", "status"}.issubset(columns):
            conn.execute(
                text(
                    f"UPDATE {order_table} SET payment_status = CASE "
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
        if {"total_amount", "amount"}.issubset(columns):
            conn.execute(
                text(
                    f"UPDATE {order_table} SET total_amount = amount "
                    "WHERE total_amount IS NULL AND amount IS NOT NULL"
                )
            )

    if "user_account" in tables and "role" in _column_names(conn, "user_account"):
        conn.execute(
            text(
                f"UPDATE {_quote(conn, 'user_account')} SET role = 'user' "
                "WHERE role IS NULL OR role = ''"
            )
        )
    if "user_account" in tables and "session_version" in _column_names(conn, "user_account"):
        conn.execute(
            text(
                f"UPDATE {_quote(conn, 'user_account')} SET session_version = 0 "
                "WHERE session_version IS NULL OR session_version < 0"
            )
        )

    if "office_layout" in tables and "version" in _column_names(conn, "office_layout"):
        conn.execute(
            text(
                f"UPDATE {_quote(conn, 'office_layout')} SET version = 1 "
                "WHERE version IS NULL OR version < 1"
            )
        )

    if "skill_order_ledger" in tables:
        columns = _column_names(conn, "skill_order_ledger")
        for column_name in ("version", "payment_attempts"):
            if column_name in columns:
                conn.execute(
                    text(
                        f"UPDATE {_quote(conn, 'skill_order_ledger')} "
                        f"SET {_quote(conn, column_name)} = 0 "
                        f"WHERE {_quote(conn, column_name)} IS NULL"
                    )
                )

    for table_name in (
        "order",
        "coffee_kb",
        "agent_profile",
        "visualization_event",
        "evomap_consumer",
    ):
        if table_name not in tables or "updated_at" not in _column_names(conn, table_name):
            continue
        conn.execute(
            text(
                f"UPDATE {_quote(conn, table_name)} SET updated_at = CURRENT_TIMESTAMP "
                "WHERE updated_at IS NULL"
            )
        )


def _ensure_mysql_request_id_length(bind: Engine) -> None:
    with bind.begin() as conn:
        if not _table_exists(conn, "order") or not _column_exists(conn, "order", "request_id"):
            return
        length = conn.execute(
            text(
                """
                SELECT CHARACTER_MAXIMUM_LENGTH
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'order'
                  AND COLUMN_NAME = 'request_id'
                """
            )
        ).scalar()
        if length is not None and int(length) >= 128:
            print("[columns] order.request_id length is current")
            return
        conn.execute(text("ALTER TABLE `order` MODIFY COLUMN `request_id` VARCHAR(128) NULL"))
        print("[columns] widened order.request_id to VARCHAR(128)")


def _create_declared_indexes(bind: Engine) -> None:
    for table in Base.metadata.sorted_tables:
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            index.create(bind=bind, checkfirst=True)
            print(f"[indexes] ensured {table.name}.{index.name}")

    with bind.begin() as conn:
        for table_name, indexes in CUSTOM_INDEXES.items():
            if table_name not in _table_names(conn):
                continue
            columns = _column_names(conn, table_name)
            existing = _index_names(conn, table_name)
            for index_name, index_columns in indexes.items():
                if index_name in existing or not set(index_columns).issubset(columns):
                    continue
                column_sql = ", ".join(_quote(conn, column) for column in index_columns)
                conn.execute(
                    text(
                        f"CREATE INDEX {_quote(conn, index_name)} "
                        f"ON {_quote(conn, table_name)} ({column_sql})"
                    )
                )
                print(f"[indexes] added {table_name}.{index_name}")

        _ensure_free_sequence_uniqueness(conn)


def _ensure_free_sequence_uniqueness(conn: Connection) -> None:
    table_name = "skill_order_ledger"
    index_name = "uq_skill_order_consumer_free_sequence"
    required = {"consumer_id", "free_order_sequence"}
    if table_name not in _table_names(conn) or not required.issubset(_column_names(conn, table_name)):
        return
    unique_constraints = inspect(conn).get_unique_constraints(table_name)
    unique_indexes = inspect(conn).get_indexes(table_name)
    already_unique = any(
        constraint.get("name") == index_name
        or constraint.get("column_names") == ["consumer_id", "free_order_sequence"]
        for constraint in unique_constraints
    ) or any(
        index.get("unique")
        and index.get("column_names") == ["consumer_id", "free_order_sequence"]
        for index in unique_indexes
    )
    if index_name in _index_names(conn, table_name) or already_unique:
        print(f"[indexes] {table_name}.{index_name} exists")
        return
    duplicate = conn.execute(
        text(
            f"SELECT consumer_id, free_order_sequence, COUNT(*) AS row_count "
            f"FROM {_quote(conn, table_name)} "
            "WHERE free_order_sequence IS NOT NULL "
            "GROUP BY consumer_id, free_order_sequence "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        print(
            "[warning] skipped free-order uniqueness; duplicate "
            "(consumer_id, free_order_sequence) rows must be reconciled manually"
        )
        return
    conn.execute(
        text(
            f"CREATE UNIQUE INDEX {_quote(conn, index_name)} "
            f"ON {_quote(conn, table_name)} (consumer_id, free_order_sequence)"
        )
    )
    print(f"[indexes] added {table_name}.{index_name}")


def _foreign_key_exists(
    conn: Connection,
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


def _orphan_count(
    conn: Connection,
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str,
) -> int:
    return int(
        conn.execute(
            text(
                f"SELECT COUNT(*) FROM {_quote(conn, table_name)} AS child "
                f"LEFT JOIN {_quote(conn, referred_table)} AS parent "
                f"ON child.{_quote(conn, column_name)} = "
                f"parent.{_quote(conn, referred_column)} "
                f"WHERE child.{_quote(conn, column_name)} IS NOT NULL "
                f"AND parent.{_quote(conn, referred_column)} IS NULL"
            )
        ).scalar()
        or 0
    )


def _ensure_mysql_foreign_keys(conn: Connection) -> None:
    tables = _table_names(conn)
    for constraint_name, definition in ORDER_FOREIGN_KEYS.items():
        table_name, column_name, referred_table, referred_column = definition
        if table_name not in tables or referred_table not in tables:
            print(f"[mysql-fk] {constraint_name} skipped; table missing")
            continue
        if column_name not in _column_names(conn, table_name):
            print(f"[mysql-fk] {constraint_name} skipped; column missing")
            continue
        if _foreign_key_exists(conn, table_name, column_name, referred_table, referred_column):
            print(f"[mysql-fk] {constraint_name} exists")
            continue
        count = _orphan_count(conn, table_name, column_name, referred_table, referred_column)
        if count:
            print(f"[warning] {constraint_name} skipped; {count} targeted orphan row(s)")
            continue
        conn.execute(
            text(
                f"ALTER TABLE {_quote(conn, table_name)} "
                f"ADD CONSTRAINT {_quote(conn, constraint_name)} "
                f"FOREIGN KEY ({_quote(conn, column_name)}) "
                f"REFERENCES {_quote(conn, referred_table)} ({_quote(conn, referred_column)})"
            )
        )
        print(f"[mysql-fk] added {constraint_name}")


def _mysql_check_clause(conn: Connection, table_name: str, constraint_name: str) -> str | None:
    row = conn.execute(
        text(
            """
            SELECT cc.CHECK_CLAUSE
            FROM information_schema.CHECK_CONSTRAINTS AS cc
            JOIN information_schema.TABLE_CONSTRAINTS AS tc
              ON tc.CONSTRAINT_SCHEMA = cc.CONSTRAINT_SCHEMA
             AND tc.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
            WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
              AND tc.TABLE_NAME = :table_name
              AND tc.CONSTRAINT_NAME = :constraint_name
              AND tc.CONSTRAINT_TYPE = 'CHECK'
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    ).first()
    return str(row[0]) if row else None


def _extract_check_values(clause: str | None) -> set[str]:
    if not clause:
        return set()
    match = re.search(r"\bIN\s*\(([^)]*)\)", clause, flags=re.IGNORECASE)
    if not match:
        return set()
    values: set[str] = set()
    for raw in match.group(1).split(","):
        value = raw.strip()
        value = re.sub(r"^_[A-Za-z0-9]+", "", value).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values.add(value)
    return values


def _ensure_mysql_check(
    conn: Connection,
    table_name: str,
    constraint_name: str,
    expression: str,
    expected_values: Iterable[object],
) -> None:
    if table_name not in _table_names(conn):
        return
    expected = {str(value) for value in expected_values}
    clause = _mysql_check_clause(conn, table_name, constraint_name)
    if _extract_check_values(clause) == expected:
        print(f"[mysql-check] {constraint_name} is current")
        return

    bad_rows = int(
        conn.execute(
            text(
                f"SELECT COUNT(*) FROM {_quote(conn, table_name)} "
                f"WHERE NOT ({expression})"
            )
        ).scalar()
        or 0
    )
    if bad_rows:
        print(f"[warning] {constraint_name} skipped; {bad_rows} row(s) violate target values")
        return
    if clause is not None:
        conn.execute(
            text(
                f"ALTER TABLE {_quote(conn, table_name)} "
                f"DROP CHECK {_quote(conn, constraint_name)}"
            )
        )
        print(f"[mysql-check] dropped stale {constraint_name}")
    conn.execute(
        text(
            f"ALTER TABLE {_quote(conn, table_name)} "
            f"ADD CONSTRAINT {_quote(conn, constraint_name)} CHECK ({expression})"
        )
    )
    print(f"[mysql-check] added {constraint_name}")


def _normalized_expression(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.replace("`", "").replace('"', "").lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("(", "").replace(")", "")
    return normalized


def _ensure_mysql_expression_check(
    conn: Connection,
    table_name: str,
    constraint_name: str,
    expression: str,
) -> None:
    if table_name not in _table_names(conn):
        return
    clause = _mysql_check_clause(conn, table_name, constraint_name)
    if _normalized_expression(clause) == _normalized_expression(expression):
        print(f"[mysql-check] {constraint_name} is current")
        return
    bad_rows = int(
        conn.execute(
            text(
                f"SELECT COUNT(*) FROM {_quote(conn, table_name)} "
                f"WHERE NOT ({expression})"
            )
        ).scalar()
        or 0
    )
    if bad_rows:
        print(f"[warning] {constraint_name} skipped; {bad_rows} row(s) violate target expression")
        return
    if clause is not None:
        conn.execute(
            text(
                f"ALTER TABLE {_quote(conn, table_name)} "
                f"DROP CHECK {_quote(conn, constraint_name)}"
            )
        )
        print(f"[mysql-check] dropped stale {constraint_name}")
    conn.execute(
        text(
            f"ALTER TABLE {_quote(conn, table_name)} "
            f"ADD CONSTRAINT {_quote(conn, constraint_name)} CHECK ({expression})"
        )
    )
    print(f"[mysql-check] added {constraint_name}")


def _ensure_mysql_constraints(bind: Engine) -> None:
    with bind.begin() as conn:
        _ensure_mysql_check(
            conn,
            "order",
            "ck_order_source_type",
            f"source_type IN ({_sql_strings(ORDER_SOURCE_TYPES)})",
            ORDER_SOURCE_TYPES,
        )
        _ensure_mysql_check(
            conn,
            "order",
            "ck_order_status",
            f"status IN ({', '.join(str(value) for value in sorted(ORDER_STATUSES))})",
            ORDER_STATUSES,
        )
        _ensure_mysql_check(
            conn,
            "order",
            "ck_order_payment_status",
            f"payment_status IN ({_sql_strings(ORDER_PAYMENT_STATUSES)})",
            ORDER_PAYMENT_STATUSES,
        )
        _ensure_mysql_check(
            conn,
            "skill_order_ledger",
            "ck_skill_order_ledger_payment_status",
            f"payment_status IN ({_sql_strings(LEDGER_PAYMENT_STATUSES)})",
            LEDGER_PAYMENT_STATUSES,
        )
        _ensure_mysql_expression_check(
            conn,
            "skill_order_ledger",
            "ck_skill_order_ledger_free_sequence",
            "free_order_sequence IS NULL OR free_order_sequence > 0",
        )
        _ensure_mysql_expression_check(
            conn,
            "skill_order_ledger",
            "ck_skill_order_ledger_amount_nonneg",
            "amount_credits >= 0",
        )
        _ensure_mysql_expression_check(
            conn,
            "skill_order_ledger",
            "ck_skill_order_ledger_attempts_nonneg",
            "payment_attempts >= 0",
        )
        if "stock_reservation_status" in _column_names(conn, "skill_order_ledger"):
            _ensure_mysql_check(
                conn,
                "skill_order_ledger",
                "ck_skill_order_ledger_stock_reservation",
                "stock_reservation_status IS NULL OR "
                f"stock_reservation_status IN ({_sql_strings(STOCK_RESERVATION_STATUSES)})",
                STOCK_RESERVATION_STATUSES,
            )
        _ensure_mysql_check(
            conn,
            "user_account",
            "ck_user_account_status",
            f"status IN ({_sql_strings(IDENTITY_STATUSES)})",
            IDENTITY_STATUSES,
        )
        if "role" in _column_names(conn, "user_account"):
            _ensure_mysql_check(
                conn,
                "user_account",
                "ck_user_account_role",
                f"role IN ({_sql_strings(ACCOUNT_ROLES)})",
                ACCOUNT_ROLES,
            )
        if "session_version" in _column_names(conn, "user_account"):
            _ensure_mysql_expression_check(
                conn,
                "user_account",
                "ck_user_account_session_version",
                "session_version >= 0",
            )
        _ensure_mysql_check(
            conn,
            "agent_profile",
            "ck_agent_profile_status",
            f"status IN ({_sql_strings(IDENTITY_STATUSES)})",
            IDENTITY_STATUSES,
        )
        _ensure_mysql_check(
            conn,
            "evomap_consumer",
            "ck_evomap_consumer_status",
            f"status IN ({_sql_strings(IDENTITY_STATUSES)})",
            IDENTITY_STATUSES,
        )
        _ensure_mysql_foreign_keys(conn)


def _sqlite_table_sql(conn: Connection, table_name: str) -> str:
    row = conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table_name},
    ).first()
    return str(row[0] or "") if row else ""


def _sqlite_check_values(table_sql: str, constraint_name: str) -> set[str]:
    pattern = rf"(?:CONSTRAINT\s+)?[\"`]?{re.escape(constraint_name)}[\"`]?\s+CHECK\s*\(\s*[^()]+?\s+IN\s*\(([^)]*)\)\s*\)"
    match = re.search(pattern, table_sql, flags=re.IGNORECASE | re.DOTALL)
    return _extract_check_values(f"IN ({match.group(1)})") if match else set()


def _sqlite_fk_target_exists(
    conn: Connection,
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str,
) -> bool:
    for fk in inspect(conn).get_foreign_keys(table_name):
        if (
            fk.get("referred_table") == referred_table
            and fk.get("constrained_columns") == [column_name]
            and fk.get("referred_columns") == [referred_column]
        ):
            return True
    return False


def _sqlite_foreign_key_violations(conn: Connection) -> set[tuple[object, ...]]:
    return {tuple(row) for row in conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()}


def _sqlite_rebuild_from_model(
    bind: Engine,
    table_name: str,
    *,
    column_type_overrides: dict[str, str] | None = None,
    omitted_constraints: set[str] | None = None,
) -> None:
    table = Base.metadata.tables.get(table_name)
    if table is None:
        raise RuntimeError(f"ORM metadata does not declare table {table_name!r}")

    with bind.connect() as conn:
        current_columns = _column_names(conn, table_name)
        target_columns = {column.name for column in table.columns}
        missing = target_columns - current_columns
        if missing:
            raise RuntimeError(
                f"Cannot rebuild {table_name}: target column(s) still missing: {sorted(missing)}"
            )

        tables = _table_names(conn)
        for foreign_key in table.foreign_keys:
            source_column = foreign_key.parent.name
            target_column = foreign_key.column.name
            target_table = foreign_key.column.table.name
            if target_table not in tables:
                raise RuntimeError(
                    f"Cannot rebuild {table_name}: referenced table {target_table!r} is missing"
                )
            count = _orphan_count(conn, table_name, source_column, target_table, target_column)
            if count:
                raise RuntimeError(
                    f"Cannot rebuild {table_name}: {count} targeted orphan row(s) in {source_column}"
                )

        before_violations = _sqlite_foreign_key_violations(conn)
        conn.commit()
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.commit()
        temporary_name = f"__migration_new_{table_name}"
        try:
            transaction = conn.begin()
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {_quote(conn, temporary_name)}")
            create_sql = str(CreateTable(table).compile(bind))
            source_prefix = f"CREATE TABLE {_quote(bind, table_name)}"
            target_prefix = f"CREATE TABLE {_quote(bind, temporary_name)}"
            if source_prefix not in create_sql:
                raise RuntimeError(f"Unable to compile rebuild DDL for {table_name}")
            create_sql = create_sql.replace(source_prefix, target_prefix, 1)
            for column_name, target_type in (column_type_overrides or {}).items():
                create_sql, replacements = re.subn(
                    rf"(\b{re.escape(column_name)}\b\s+)VARCHAR\(\d+\)",
                    rf"\g<1>{target_type}",
                    create_sql,
                    count=1,
                    flags=re.IGNORECASE,
                )
                if replacements != 1:
                    raise RuntimeError(
                        f"Unable to apply type override for {table_name}.{column_name}"
                    )
            for constraint_name in omitted_constraints or set():
                create_sql, replacements = re.subn(
                    rf",\s*CONSTRAINT\s+[\"`]?{re.escape(constraint_name)}[\"`]?\s+"
                    rf"UNIQUE\s*\([^)]*\)",
                    "",
                    create_sql,
                    count=1,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if replacements != 1:
                    raise RuntimeError(
                        f"Unable to omit constraint {constraint_name} while rebuilding {table_name}"
                    )
            conn.exec_driver_sql(create_sql)
            column_sql = ", ".join(_quote(conn, column.name) for column in table.columns)
            conn.exec_driver_sql(
                f"INSERT INTO {_quote(conn, temporary_name)} ({column_sql}) "
                f"SELECT {column_sql} FROM {_quote(conn, table_name)}"
            )
            conn.exec_driver_sql(f"DROP TABLE {_quote(conn, table_name)}")
            conn.exec_driver_sql(
                f"ALTER TABLE {_quote(conn, temporary_name)} "
                f"RENAME TO {_quote(conn, table_name)}"
            )
            after_violations = _sqlite_foreign_key_violations(conn)
            new_violations = after_violations - before_violations
            if new_violations:
                raise RuntimeError(
                    f"Rebuilding {table_name} would introduce {len(new_violations)} FK violation(s)"
                )
            transaction.commit()
            print(f"[sqlite] rebuilt {table_name} with current constraints")
        except Exception:
            if conn.in_transaction():
                conn.rollback()
            raise
        finally:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.commit()


def _ensure_sqlite_constraints(bind: Engine) -> None:
    rebuild_order = False
    rebuild_ledger = False
    rebuild_account = False
    rebuild_agent = False
    omit_ledger_constraints: set[str] = set()

    with bind.connect() as conn:
        order_sql = _sqlite_table_sql(conn, "order")
        if _sqlite_check_values(order_sql, "ck_order_status") != {
            str(value) for value in ORDER_STATUSES
        }:
            rebuild_order = True
        if _sqlite_check_values(order_sql, "ck_order_payment_status") != {
            str(value) for value in ORDER_PAYMENT_STATUSES
        }:
            rebuild_order = True
        request_column = next(
            (
                column
                for column in inspect(conn).get_columns("order")
                if column["name"] == "request_id"
            ),
            None,
        )
        request_length = getattr(request_column.get("type"), "length", None) if request_column else None
        if request_length is not None and request_length < 128:
            rebuild_order = True
        if rebuild_order:
            invalid_order_rows = int(
                conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {_quote(conn, 'order')} "
                        f"WHERE status NOT IN ({', '.join(str(value) for value in sorted(ORDER_STATUSES))}) "
                        f"OR payment_status NOT IN ({_sql_strings(ORDER_PAYMENT_STATUSES)})"
                    )
                ).scalar()
                or 0
            )
            if invalid_order_rows:
                print(
                    f"[warning] SQLite order constraint rebuild skipped; "
                    f"{invalid_order_rows} row(s) violate target status values"
                )
                rebuild_order = False

        ledger_sql = _sqlite_table_sql(conn, "skill_order_ledger")
        if _sqlite_check_values(ledger_sql, "ck_skill_order_ledger_payment_status") != {
            str(value) for value in LEDGER_PAYMENT_STATUSES
        }:
            rebuild_ledger = True
        for constraint_name in (
            "ck_skill_order_ledger_free_sequence",
            "ck_skill_order_ledger_amount_nonneg",
            "ck_skill_order_ledger_attempts_nonneg",
            "ck_skill_order_ledger_stock_reservation",
        ):
            if constraint_name.lower() not in ledger_sql.lower():
                rebuild_ledger = True
        if rebuild_ledger:
            invalid_ledger_rows = int(
                conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {_quote(conn, 'skill_order_ledger')} "
                        f"WHERE payment_status NOT IN ({_sql_strings(LEDGER_PAYMENT_STATUSES)}) "
                        "OR (free_order_sequence IS NOT NULL AND free_order_sequence <= 0) "
                        "OR amount_credits < 0 OR payment_attempts < 0 "
                        "OR (stock_reservation_status IS NOT NULL AND "
                        f"stock_reservation_status NOT IN ({_sql_strings(STOCK_RESERVATION_STATUSES)}))"
                    )
                ).scalar()
                or 0
            )
            if invalid_ledger_rows:
                print(
                    f"[warning] SQLite ledger constraint rebuild skipped; "
                    f"{invalid_ledger_rows} row(s) violate target constraints"
                )
                rebuild_ledger = False
            else:
                duplicate_free_rows = conn.execute(
                    text(
                        f"SELECT 1 FROM {_quote(conn, 'skill_order_ledger')} "
                        "WHERE free_order_sequence IS NOT NULL "
                        "GROUP BY consumer_id, free_order_sequence "
                        "HAVING COUNT(*) > 1 LIMIT 1"
                    )
                ).first()
                if duplicate_free_rows is not None:
                    omit_ledger_constraints.add("uq_skill_order_consumer_free_sequence")
                    print(
                        "[warning] rebuilding ledger without free-order uniqueness; "
                        "duplicate rows require manual reconciliation"
                    )

        account_table = Base.metadata.tables.get("user_account")
        if account_table is not None and "role" in account_table.columns:
            account_sql = _sqlite_table_sql(conn, "user_account")
            if _sqlite_check_values(account_sql, "ck_user_account_role") != set(ACCOUNT_ROLES):
                rebuild_account = True
            if "ck_user_account_session_version" not in account_sql.lower():
                rebuild_account = True
            if rebuild_account:
                invalid_account_rows = int(
                    conn.execute(
                        text(
                            f"SELECT COUNT(*) FROM {_quote(conn, 'user_account')} "
                            f"WHERE role NOT IN ({_sql_strings(ACCOUNT_ROLES)}) "
                            f"OR status NOT IN ({_sql_strings(IDENTITY_STATUSES)}) "
                            "OR session_version < 0"
                        )
                    ).scalar()
                    or 0
                )
                if invalid_account_rows:
                    print(
                        f"[warning] SQLite user_account constraint rebuild skipped; "
                        f"{invalid_account_rows} row(s) violate target values"
                    )
                    rebuild_account = False

        agent_table = Base.metadata.tables.get("agent_profile")
        if agent_table is not None and "consumer_id" in agent_table.columns:
            rebuild_agent = not _sqlite_fk_target_exists(
                conn,
                "agent_profile",
                "consumer_id",
                "evomap_consumer",
                "consumer_id",
            )
            if rebuild_agent:
                invalid_agent_rows = int(
                    conn.execute(
                        text(
                            f"SELECT COUNT(*) FROM {_quote(conn, 'agent_profile')} "
                            f"WHERE status NOT IN ({_sql_strings(IDENTITY_STATUSES)})"
                        )
                    ).scalar()
                    or 0
                )
                if invalid_agent_rows:
                    print(
                        f"[warning] SQLite agent_profile constraint rebuild skipped; "
                        f"{invalid_agent_rows} row(s) violate target status values"
                    )
                    rebuild_agent = False

    if rebuild_order:
        _sqlite_rebuild_from_model(
            bind,
            "order",
            column_type_overrides={"request_id": "VARCHAR(128)"},
        )
    if rebuild_ledger:
        _sqlite_rebuild_from_model(
            bind,
            "skill_order_ledger",
            omitted_constraints=omit_ledger_constraints,
        )
    if rebuild_account:
        _sqlite_rebuild_from_model(bind, "user_account")
    if rebuild_agent:
        _sqlite_rebuild_from_model(bind, "agent_profile")


def _ensure_constraints(bind: Engine) -> None:
    if bind.dialect.name == "mysql":
        _ensure_mysql_constraints(bind)
    elif bind.dialect.name == "sqlite":
        _ensure_sqlite_constraints(bind)
    else:
        raise RuntimeError(f"Unsupported database dialect: {bind.dialect.name}")


def _verify_schema(bind: Engine) -> None:
    required_columns: dict[str, set[str]] = {}
    for migration in ADDITIVE_COLUMNS:
        required_columns.setdefault(migration.table, set()).add(migration.column)

    with bind.connect() as conn:
        for table_name, columns in required_columns.items():
            missing = columns - _column_names(conn, table_name)
            if missing:
                raise RuntimeError(f"Schema verification failed: {table_name} missing {sorted(missing)}")
        if bind.dialect.name == "sqlite":
            violations = _sqlite_foreign_key_violations(conn)
            if violations:
                print(
                    f"[warning] SQLite foreign_key_check reports {len(violations)} existing violation(s); "
                    "no rows were changed automatically"
                )
            else:
                print("[verify] SQLite foreign_key_check clean")
        print("[verify] required additive columns present")


def _ensure_constraints_and_indexes(bind: Engine) -> None:
    _ensure_constraints(bind)
    _create_declared_indexes(bind)


MigrationStep = tuple[str, Callable[[Engine], None]]
MIGRATIONS: tuple[MigrationStep, ...] = (
    ("20260712_001_create_declared_schema", _create_declared_tables),
    ("20260712_002_additive_columns", _ensure_additive_columns),
    ("20260712_003_constraints_and_indexes", _ensure_constraints_and_indexes),
    ("20260712_004_verify_schema", _verify_schema),
    ("20260719_005_skill_account_auth_schema", _create_declared_tables),
    ("20260723_006_demand_schema", _create_declared_tables),
)


def run_migrations(bind: Engine = engine) -> None:
    if bind.dialect.name not in {"sqlite", "mysql"}:
        raise RuntimeError(f"Unsupported database dialect: {bind.dialect.name}")
    _ensure_migration_table(bind)
    for version, migration in MIGRATIONS:
        already_recorded = _migration_recorded(bind, version)
        action = "rechecking" if already_recorded else "applying"
        print(f"[migration] {action} {version}")
        # Every step remains idempotent and is rechecked on startup. The version
        # table is an audit trail, not a reason to hide partial/manual drift.
        migration(bind)
        _record_migration(bind, version)
        print(f"[migration] complete {version}")


def main() -> None:
    print(f"[schema] dialect={engine.dialect.name}")
    run_migrations(engine)
    print("[schema] canonical migration complete")


if __name__ == "__main__":
    main()
