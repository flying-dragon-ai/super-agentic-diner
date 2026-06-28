from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_migration(db_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "DB_MODE": "sqlite",
            "SQLITE_PATH": str(db_path),
            "USE_FAKEREDIS": "true",
            "PYTHONPATH": str(ROOT),
        }
    )
    return subprocess.run(
        [sys.executable, "scripts/migrate_schema_consistency.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )


def _tables(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def _columns(db_path: Path, table_name: str) -> set[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return {row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")')}


class SchemaConsistencyMigrationSqliteTests(unittest.TestCase):
    def test_fresh_sqlite_creates_declared_tables_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "coffee_ai_schema_test.db"

            first = _run_migration(db_path)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            second = _run_migration(db_path)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)

            expected_tables = {
                "user",
                "user_account",
                "order",
                "order_item",
                "order_item_option",
                "coffee_kb",
                "product",
                "product_option_group",
                "product_option",
                "user_wallet",
                "balance_transaction",
                "agent_profile",
                "evomap_consumer",
                "skill_order_ledger",
                "visualization_event",
                "office_layout",
                "chat_message",
                "user_profile",
                "agent_experience",
                "visitor_insight",
            }
            self.assertTrue(expected_tables.issubset(_tables(db_path)))

    def test_legacy_sqlite_order_columns_and_dead_tables_are_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "coffee_ai_legacy_test.db"
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE "order" (
                        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id BIGINT NOT NULL,
                        coffee_name VARCHAR(128) NOT NULL,
                        amount DECIMAL(10, 2) NOT NULL,
                        status SMALLINT NOT NULL DEFAULT 1,
                        request_id VARCHAR(64),
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO "order"
                    (user_id, coffee_name, amount, status, request_id)
                    VALUES (1, 'Americano', 12.50, 1, 'legacy-req-1')
                    """
                )
                conn.execute("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, content TEXT)")
                conn.execute("CREATE TABLE pending_orders (id INTEGER PRIMARY KEY, content TEXT)")
                conn.commit()

            result = _run_migration(db_path)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            tables = _tables(db_path)
            self.assertNotIn("chat_messages", tables)
            self.assertNotIn("pending_orders", tables)
            self.assertIn("chat_messages_deprecated", tables)
            self.assertIn("pending_orders_deprecated", tables)

            order_columns = _columns(db_path, "order")
            for column in (
                "source_type",
                "payment_status",
                "consumer_url",
                "consumer_id",
                "agent_id",
                "ledger_id",
                "correlation_id",
                "total_amount",
                "cancelled_at",
                "refunded_at",
                "updated_at",
            ):
                self.assertIn(column, order_columns)

            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute(
                    'SELECT source_type, payment_status, total_amount FROM "order"'
                ).fetchone()
            self.assertEqual(row[0], "web_dialog")
            self.assertEqual(row[1], "paid")
            self.assertEqual(float(row[2]), 12.5)


if __name__ == "__main__":
    unittest.main()
