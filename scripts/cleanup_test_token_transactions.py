"""Safely remove rows created by the live token transaction test.

The default mode is read-only.  Destructive execution requires an explicit
time window plus the exact expected row counts printed by the dry-run.  The
script only supports the local SQLite database because it is intended to
repair accidental writes made by ``tests/test_token_transaction_flow.py``.

Examples::

    python scripts/cleanup_test_token_transactions.py \
        --created-from "2026-07-12 06:10:00" \
        --created-to "2026-07-12 06:16:00"

    python scripts/cleanup_test_token_transactions.py \
        --created-from "2026-07-12 06:10:00" \
        --created-to "2026-07-12 06:16:00" \
        --execute --expected-consumers 30 --expected-agents 35 \
        --expected-ledgers 40 --expected-orders 35
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


CONSUMER_PREFIX = "test-token-tx-%"
AGENT_PREFIX = "token-test-test-token-tx-%"
REQUEST_PREFIX = "token-tx-%"


@dataclass(frozen=True)
class CleanupScope:
    consumer_ids: tuple[int, ...]
    user_ids: tuple[int, ...]
    agent_ids: tuple[int, ...]
    ledger_ids: tuple[int, ...]
    order_ids: tuple[int, ...]
    request_ids: tuple[str, ...]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "consumers": len(self.consumer_ids),
            "users": len(self.user_ids),
            "agents": len(self.agent_ids),
            "ledgers": len(self.ledger_ids),
            "orders": len(self.order_ids),
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="coffee_ai.db")
    parser.add_argument("--created-from", required=True)
    parser.add_argument("--created-to", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-consumers", type=int)
    parser.add_argument("--expected-agents", type=int)
    parser.add_argument("--expected-ledgers", type=int)
    parser.add_argument("--expected-orders", type=int)
    parser.add_argument("--backup-dir", default="logs/backups")
    return parser.parse_args()


def _validate_timestamp(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return value


def _placeholders(values: Sequence[object]) -> str:
    if not values:
        return "NULL"
    return ",".join("?" for _ in values)


def _scalar(conn: sqlite3.Connection, sql: str, params: Iterable[object] = ()) -> int:
    row = conn.execute(sql, tuple(params)).fetchone()
    return int(row[0] or 0)


def _load_scope(
    conn: sqlite3.Connection,
    created_from: str,
    created_to: str,
) -> CleanupScope:
    consumers = conn.execute(
        """
        SELECT consumer_id, local_user_id
        FROM evomap_consumer
        WHERE evomap_node_id LIKE ?
          AND created_at >= ?
          AND created_at < ?
        ORDER BY consumer_id
        """,
        (CONSUMER_PREFIX, created_from, created_to),
    ).fetchall()
    consumer_ids = tuple(int(row[0]) for row in consumers)
    user_ids = tuple(int(row[1]) for row in consumers if row[1] is not None)

    agent_rows = conn.execute(
        """
        SELECT agent_id
        FROM agent_profile
        WHERE tool_name LIKE ?
          AND created_at >= ?
          AND created_at < ?
        ORDER BY agent_id
        """,
        (AGENT_PREFIX, created_from, created_to),
    ).fetchall()
    agent_ids = tuple(int(row[0]) for row in agent_rows)

    ledger_rows = conn.execute(
        f"""
        SELECT ledger_id, request_id
        FROM skill_order_ledger
        WHERE request_id LIKE ?
          AND created_at >= ?
          AND created_at < ?
          AND consumer_id IN ({_placeholders(consumer_ids)})
        ORDER BY ledger_id
        """,
        (REQUEST_PREFIX, created_from, created_to, *consumer_ids),
    ).fetchall()
    ledger_ids = tuple(int(row[0]) for row in ledger_rows)
    request_ids = tuple(str(row[1]) for row in ledger_rows)

    order_rows = conn.execute(
        f"""
        SELECT order_id
        FROM [order]
        WHERE request_id LIKE ?
          AND created_at >= ?
          AND created_at < ?
          AND consumer_id IN ({_placeholders(consumer_ids)})
        ORDER BY order_id
        """,
        (REQUEST_PREFIX, created_from, created_to, *consumer_ids),
    ).fetchall()
    order_ids = tuple(int(row[0]) for row in order_rows)

    return CleanupScope(
        consumer_ids=consumer_ids,
        user_ids=user_ids,
        agent_ids=agent_ids,
        ledger_ids=ledger_ids,
        order_ids=order_ids,
        request_ids=request_ids,
    )


def _assert_closed_scope(conn: sqlite3.Connection, scope: CleanupScope) -> None:
    if not scope.consumer_ids or not scope.agent_ids:
        raise RuntimeError("No matching test-token transaction rows were found")
    if len(scope.user_ids) != len(scope.consumer_ids):
        raise RuntimeError("Every selected test consumer must have one local user")
    if len(set(scope.user_ids)) != len(scope.user_ids):
        raise RuntimeError("Selected test consumers do not have unique local users")

    consumer_ph = _placeholders(scope.consumer_ids)
    user_ph = _placeholders(scope.user_ids)
    agent_ph = _placeholders(scope.agent_ids)
    ledger_ph = _placeholders(scope.ledger_ids)
    order_ph = _placeholders(scope.order_ids)

    checks = {
        "non_test_orders_for_selected_users": (
            f"SELECT COUNT(*) FROM [order] WHERE user_id IN ({user_ph}) "
            f"AND order_id NOT IN ({order_ph})",
            (*scope.user_ids, *scope.order_ids),
        ),
        "user_accounts": (
            f"SELECT COUNT(*) FROM user_account WHERE user_id IN ({user_ph})",
            scope.user_ids,
        ),
        "chat_messages": (
            f"SELECT COUNT(*) FROM chat_message WHERE user_id IN ({user_ph})",
            scope.user_ids,
        ),
        "user_profiles": (
            f"SELECT COUNT(*) FROM user_profile WHERE user_id IN ({user_ph})",
            scope.user_ids,
        ),
        "visitor_insights": (
            f"SELECT COUNT(*) FROM visitor_insight WHERE user_id IN ({user_ph})",
            scope.user_ids,
        ),
        "foreign_ledgers": (
            f"SELECT COUNT(*) FROM skill_order_ledger WHERE consumer_id IN ({consumer_ph}) "
            f"AND ledger_id NOT IN ({ledger_ph})",
            (*scope.consumer_ids, *scope.ledger_ids),
        ),
        "foreign_orders": (
            f"SELECT COUNT(*) FROM [order] WHERE consumer_id IN ({consumer_ph}) "
            f"AND order_id NOT IN ({order_ph})",
            (*scope.consumer_ids, *scope.order_ids),
        ),
        "foreign_agent_ledgers": (
            f"SELECT COUNT(*) FROM skill_order_ledger WHERE agent_id IN ({agent_ph}) "
            f"AND ledger_id NOT IN ({ledger_ph})",
            (*scope.agent_ids, *scope.ledger_ids),
        ),
        "foreign_agent_orders": (
            f"SELECT COUNT(*) FROM [order] WHERE agent_id IN ({agent_ph}) "
            f"AND order_id NOT IN ({order_ph})",
            (*scope.agent_ids, *scope.order_ids),
        ),
    }
    failed = {
        name: _scalar(conn, sql, params)
        for name, (sql, params) in checks.items()
        if _scalar(conn, sql, params) != 0
    }
    if failed:
        raise RuntimeError(f"Cleanup scope is not isolated: {failed}")

    unexpected_transactions = _scalar(
        conn,
        f"""
        SELECT COUNT(*)
        FROM balance_transaction
        WHERE (user_id IN ({user_ph})
               OR order_id IN ({order_ph})
               OR ledger_id IN ({ledger_ph}))
          AND NOT (currency = 'credits' AND type = 'free_order' AND amount = 0)
        """,
        (*scope.user_ids, *scope.order_ids, *scope.ledger_ids),
    )
    if unexpected_transactions:
        raise RuntimeError(
            f"Found {unexpected_transactions} unexpected non-zero/non-test wallet transactions"
        )

    unexpected_wallets = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM user_wallet
        WHERE user_id IN ({user_ph})
          AND NOT (currency = 'credits' AND balance = 0)
        """,
        scope.user_ids,
    )
    if unexpected_wallets:
        raise RuntimeError(f"Found {unexpected_wallets} unexpected test-user wallets")


def _stock_compensation(conn: sqlite3.Connection, scope: CleanupScope) -> list[dict[str, int]]:
    rows = conn.execute(
        f"""
        SELECT product_id, SUM(quantity) AS quantity
        FROM order_item
        WHERE order_id IN ({_placeholders(scope.order_ids)})
        GROUP BY product_id
        ORDER BY product_id
        """,
        scope.order_ids,
    ).fetchall()
    return [
        {"product_id": int(row[0]), "quantity": int(row[1])}
        for row in rows
        if row[0] is not None
    ]


def _print_report(
    conn: sqlite3.Connection,
    scope: CleanupScope,
    stock: list[dict[str, int]],
) -> None:
    event_count = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM visualization_event
        WHERE agent_id IN ({_placeholders(scope.agent_ids)})
           OR correlation_id IN ({_placeholders(scope.request_ids)})
        """,
        (*scope.agent_ids, *scope.request_ids),
    )
    item_count = _scalar(
        conn,
        f"SELECT COUNT(*) FROM order_item WHERE order_id IN ({_placeholders(scope.order_ids)})",
        scope.order_ids,
    )
    transaction_count = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM balance_transaction
        WHERE user_id IN ({_placeholders(scope.user_ids)})
           OR order_id IN ({_placeholders(scope.order_ids)})
           OR ledger_id IN ({_placeholders(scope.ledger_ids)})
        """,
        (*scope.user_ids, *scope.order_ids, *scope.ledger_ids),
    )
    report = {
        **scope.counts,
        "order_items": item_count,
        "balance_transactions": transaction_count,
        "visualization_events": event_count,
        "stock_compensation": stock,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _backup_database(database: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{database.stem}-pre-test-cleanup-{stamp}.db"
    source = sqlite3.connect(database)
    target = sqlite3.connect(backup_path)
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()
    check = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
    try:
        result = check.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        backup_path.unlink(missing_ok=True)
        raise RuntimeError(f"Backup quick_check failed: {result}")
    return backup_path


def _delete_selected(conn: sqlite3.Connection, scope: CleanupScope) -> None:
    user_ph = _placeholders(scope.user_ids)
    agent_ph = _placeholders(scope.agent_ids)
    ledger_ph = _placeholders(scope.ledger_ids)
    order_ph = _placeholders(scope.order_ids)
    request_ph = _placeholders(scope.request_ids)
    consumer_ph = _placeholders(scope.consumer_ids)

    conn.execute("BEGIN IMMEDIATE")
    try:
        stock = _stock_compensation(conn, scope)
        for row in stock:
            conn.execute(
                "UPDATE product SET stock = stock + ? WHERE product_id = ?",
                (row["quantity"], row["product_id"]),
            )

        conn.execute(
            f"DELETE FROM agent_experience WHERE user_id IN ({user_ph}) "
            f"OR order_id IN ({order_ph}) OR correlation_id IN ({request_ph})",
            (*scope.user_ids, *scope.order_ids, *scope.request_ids),
        )
        conn.execute(
            f"DELETE FROM visualization_event WHERE agent_id IN ({agent_ph}) "
            f"OR correlation_id IN ({request_ph})",
            (*scope.agent_ids, *scope.request_ids),
        )
        conn.execute(
            f"DELETE FROM order_item_option WHERE item_id IN "
            f"(SELECT item_id FROM order_item WHERE order_id IN ({order_ph}))",
            scope.order_ids,
        )
        conn.execute(
            f"DELETE FROM balance_transaction WHERE user_id IN ({user_ph}) "
            f"OR order_id IN ({order_ph}) OR ledger_id IN ({ledger_ph})",
            (*scope.user_ids, *scope.order_ids, *scope.ledger_ids),
        )
        conn.execute(f"DELETE FROM order_item WHERE order_id IN ({order_ph})", scope.order_ids)
        conn.execute(f"DELETE FROM [order] WHERE order_id IN ({order_ph})", scope.order_ids)
        conn.execute(
            f"DELETE FROM skill_order_ledger WHERE ledger_id IN ({ledger_ph})",
            scope.ledger_ids,
        )
        conn.execute(f"DELETE FROM user_wallet WHERE user_id IN ({user_ph})", scope.user_ids)
        conn.execute(
            f"DELETE FROM agent_profile WHERE agent_id IN ({agent_ph})",
            scope.agent_ids,
        )
        conn.execute(
            f"DELETE FROM evomap_consumer WHERE consumer_id IN ({consumer_ph})",
            scope.consumer_ids,
        )
        conn.execute(f"DELETE FROM [user] WHERE user_id IN ({user_ph})", scope.user_ids)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def main() -> None:
    args = _parse_args()
    created_from = _validate_timestamp(args.created_from)
    created_to = _validate_timestamp(args.created_to)
    if created_from >= created_to:
        raise SystemExit("--created-from must be before --created-to")

    database = Path(args.database).resolve()
    if database.suffix.lower() != ".db" or not database.is_file():
        raise SystemExit(f"SQLite database not found: {database}")

    conn = sqlite3.connect(database)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("SQLite foreign key enforcement could not be enabled")
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Source database quick_check failed")

        scope = _load_scope(conn, created_from, created_to)
        _assert_closed_scope(conn, scope)
        stock = _stock_compensation(conn, scope)
        _print_report(conn, scope, stock)

        if not args.execute:
            print("DRY-RUN ONLY: no rows were changed")
            return

        expected = {
            "consumers": args.expected_consumers,
            "agents": args.expected_agents,
            "ledgers": args.expected_ledgers,
            "orders": args.expected_orders,
        }
        if any(value is None for value in expected.values()):
            raise RuntimeError("--execute requires every --expected-* count")
        actual = {
            key: scope.counts[key]
            for key in ("consumers", "agents", "ledgers", "orders")
        }
        if actual != expected:
            raise RuntimeError(f"Expected row counts {expected}, found {actual}")

        backup_path = _backup_database(database, Path(args.backup_dir).resolve())
        print(f"backup={backup_path}")
        _delete_selected(conn, scope)

        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Database quick_check failed after cleanup")
        remaining = _load_scope(conn, created_from, created_to)
        if any(remaining.counts.values()):
            raise RuntimeError(f"Selected rows remain after cleanup: {remaining.counts}")
        print("cleanup=complete")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
