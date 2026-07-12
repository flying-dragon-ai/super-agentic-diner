from __future__ import annotations

import _test_env  # noqa: F401 - install repository-wide isolated test defaults first

import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def _sqlite_env(db_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "test",
            "DB_MODE": "sqlite",
            "SQLITE_PATH": str(db_path),
            "USE_FAKEREDIS": "true",
            "SEED_DEMO_DATA": "false",
            "PYTHONPATH": str(ROOT),
        }
    )
    return env


class SettingsFoundationTests(unittest.TestCase):
    def test_invalid_database_mode_is_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, db_mode="postgres")

    def test_mysql_url_preserves_special_character_password(self):
        settings = Settings(
            _env_file=None,
            db_mode="mysql",
            mysql_user="coffee-user",
            mysql_password="p@ss:/?# word",
            mysql_host="db.internal",
            mysql_database="coffee_test",
        )
        self.assertEqual(settings.database_url.password, "p@ss:/?# word")
        rendered = settings.database_url.render_as_string(hide_password=False)
        self.assertIn("p%40ss%3A%2F%3F%23 word", rendered)
        self.assertNotIn("p@ss:/?#", rendered)

    def test_production_rejects_default_secret_and_insecure_cookie(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                environment="production",
                auth_cookie_secure=True,
            )
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                environment="production",
                auth_secret_key="x" * 48,
                auth_cookie_secure=False,
            )

    def test_skill_payment_processing_timeout_has_safe_minimum(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, skill_payment_processing_timeout_seconds=29)
        self.assertEqual(
            Settings(_env_file=None).skill_payment_processing_timeout_seconds,
            120,
        )

    def test_cors_defaults_are_local_only_and_production_can_be_same_origin(self):
        local = Settings(_env_file=None)
        self.assertEqual(
            local.cors_allowed_origin_list,
            [
                "http://localhost:5174",
                "http://127.0.0.1:5174",
                "http://localhost:5175",
                "http://127.0.0.1:5175",
            ],
        )
        production = Settings(
            _env_file=None,
            environment="production",
            auth_secret_key="x" * 48,
            auth_cookie_secure=True,
            registration_bonus_cny=0,
        )
        self.assertEqual(production.cors_allowed_origin_list, [])
        configured = Settings(
            _env_file=None,
            environment="production",
            auth_secret_key="x" * 48,
            auth_cookie_secure=True,
            registration_bonus_cny=0,
            cors_allowed_origins="https://cafe.example, https://admin.example,https://cafe.example",
        )
        self.assertEqual(
            configured.cors_allowed_origin_list,
            ["https://cafe.example", "https://admin.example"],
        )


class DatabaseRuntimeFoundationTests(unittest.TestCase):
    def test_sqlite_connection_enforces_foreign_keys_and_busy_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "runtime.db"
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from app.db.database import engine; "
                        "c=engine.raw_connection(); "
                        "print(c.execute('PRAGMA foreign_keys').fetchone()[0]); "
                        "print(c.execute('PRAGMA busy_timeout').fetchone()[0]); "
                        "c.close(); print(engine.url.database)"
                    ),
                ],
                cwd=ROOT,
                env=_sqlite_env(db_path),
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.strip().splitlines()
            self.assertEqual(lines[0], "1")
            self.assertEqual(lines[1], "5000")
            self.assertEqual(Path(lines[2]), db_path)

    def test_canonical_migration_is_idempotent_and_does_not_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "schema.db"
            env = _sqlite_env(db_path)
            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, "scripts/migrate_order_sources.py"],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM "user"').fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM product").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM user_account").fetchone()[0], 0)

                account_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(user_account)")
                }
                self.assertTrue(
                    {
                        "gender",
                        "specialty",
                        "profession",
                        "role",
                        "session_version",
                    }.issubset(account_columns)
                )
                agent_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(agent_profile)")
                }
                self.assertIn("consumer_id", agent_columns)
                ledger_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(skill_order_ledger)")
                }
                self.assertTrue(
                    {
                        "version",
                        "payment_attempts",
                        "stock_reservation_json",
                        "stock_reservation_status",
                    }.issubset(ledger_columns)
                )

                request_type = next(
                    row[2]
                    for row in conn.execute('PRAGMA table_info("order")')
                    if row[1] == "request_id"
                )
                self.assertEqual(request_type.upper(), "VARCHAR(128)")

                order_sql = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='order'"
                ).fetchone()[0]
                self.assertIn("status IN (0, 1, 2, 3, 4)", order_sql)
                self.assertIn("payment_processing", order_sql)
                self.assertNotIn("reconciling", order_sql)

                account_sql = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_account'"
                ).fetchone()[0]
                self.assertIn("ck_user_account_session_version", account_sql)

                ledger_sql = conn.execute(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='table' AND name='skill_order_ledger'"
                ).fetchone()[0]
                self.assertIn("ck_skill_order_ledger_stock_reservation", ledger_sql)
                self.assertIn("reconciling", ledger_sql)

                agent_fks = conn.execute("PRAGMA foreign_key_list(agent_profile)").fetchall()
                self.assertTrue(
                    any(row[2] == "evomap_consumer" and row[3] == "consumer_id" for row in agent_fks)
                )

                unique_columns = []
                for index_row in conn.execute("PRAGMA index_list(skill_order_ledger)"):
                    if index_row[2]:
                        unique_columns.append(
                            tuple(
                                column[2]
                                for column in conn.execute(
                                    f'PRAGMA index_info("{index_row[1]}")'
                                )
                            )
                        )
                self.assertIn(("consumer_id", "free_order_sequence"), unique_columns)
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0],
                    4,
                )

    def test_legacy_schema_is_upgraded_without_deleting_unrelated_fk_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            with closing(sqlite3.connect(db_path)) as conn:
                conn.executescript(
                    """
                    PRAGMA foreign_keys=OFF;
                    CREATE TABLE "user" (
                        user_id INTEGER PRIMARY KEY AUTOINCREMENT
                    );
                    INSERT INTO "user" (user_id) VALUES (1);

                    CREATE TABLE user_account (
                        account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username VARCHAR(64) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        nickname VARCHAR(64),
                        user_id INTEGER NOT NULL UNIQUE,
                        status VARCHAR(16) NOT NULL DEFAULT 'active',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT ck_user_account_status
                            CHECK (status IN ('active', 'inactive', 'disabled')),
                        FOREIGN KEY(user_id) REFERENCES "user" (user_id)
                    );
                    INSERT INTO user_account
                        (username, password_hash, user_id, status)
                    VALUES ('legacy-user', 'not-a-real-hash', 1, 'active');

                    CREATE TABLE "order" (
                        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id BIGINT NOT NULL,
                        coffee_name VARCHAR(128),
                        amount DECIMAL(10, 2),
                        status SMALLINT NOT NULL DEFAULT 0,
                        request_id VARCHAR(64) UNIQUE,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    INSERT INTO "order"
                        (user_id, coffee_name, amount, status, request_id)
                    VALUES (1, 'Legacy Americano', 12.50, 1, 'legacy-request');

                    CREATE TABLE office_layout (
                        layout_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        namespace VARCHAR(32) NOT NULL UNIQUE,
                        layout_json TEXT NOT NULL,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    INSERT INTO office_layout (namespace, layout_json)
                    VALUES ('default', '[]');

                    CREATE TABLE legacy_orphan (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES "user" (user_id)
                    );
                    INSERT INTO legacy_orphan (id, user_id) VALUES (1, 999);
                    """
                )
                conn.commit()

            result = subprocess.run(
                [sys.executable, "scripts/migrate_order_sources.py"],
                cwd=ROOT,
                env=_sqlite_env(db_path),
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("existing violation(s)", result.stdout)

            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(
                    conn.execute('SELECT request_id FROM "order"').fetchone()[0],
                    "legacy-request",
                )
                self.assertEqual(
                    conn.execute("SELECT username, role FROM user_account").fetchone(),
                    ("legacy-user", "user"),
                )
                self.assertEqual(
                    conn.execute("SELECT user_id FROM legacy_orphan").fetchone()[0],
                    999,
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT version FROM office_layout WHERE namespace='default'"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(len(conn.execute("PRAGMA foreign_key_check").fetchall()), 1)

    def test_init_db_is_schema_only_without_explicit_seed_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "init.db"
            result = subprocess.run(
                [sys.executable, "scripts/init_db.py"],
                cwd=ROOT,
                env=_sqlite_env(db_path),
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Demo data was not created", result.stdout)
            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM "user"').fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM user_account").fetchone()[0], 0)

    def test_admin_bootstrap_is_explicit_and_does_not_seed_balance(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "admin.db"
            env = _sqlite_env(db_path)
            create = subprocess.run(
                [
                    sys.executable,
                    "scripts/bootstrap_admin.py",
                    "--username",
                    "ops-admin",
                    "--password-stdin",
                ],
                cwd=ROOT,
                env=env,
                input="a-strong-bootstrap-password\n",
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(create.returncode, 0, create.stderr + create.stdout)
            self.assertNotIn("a-strong-bootstrap-password", create.stdout + create.stderr)

            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT username, role, status FROM user_account"
                    ).fetchone(),
                    ("ops-admin", "admin", "active"),
                )
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM user_wallet").fetchone()[0], 0)
                conn.execute("UPDATE user_account SET role='user' WHERE username='ops-admin'")
                conn.commit()

            refused = subprocess.run(
                [
                    sys.executable,
                    "scripts/bootstrap_admin.py",
                    "--username",
                    "ops-admin",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(refused.returncode, 2, refused.stderr + refused.stdout)

            promoted = subprocess.run(
                [
                    sys.executable,
                    "scripts/bootstrap_admin.py",
                    "--username",
                    "ops-admin",
                    "--promote-existing",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(promoted.returncode, 0, promoted.stderr + promoted.stdout)
            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT role FROM user_account WHERE username='ops-admin'"
                    ).fetchone()[0],
                    "admin",
                )

    def test_duplicate_free_sequences_are_reported_without_destructive_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "duplicate-free.db"
            env = _sqlite_env(db_path)
            initial = subprocess.run(
                [sys.executable, "scripts/migrate_order_sources.py"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute("PRAGMA foreign_keys=OFF")
                now = "2026-07-12 00:00:00"
                conn.execute(
                    """
                    INSERT INTO evomap_consumer
                    (consumer_id, evomap_node_id, display_name, free_orders_used,
                     status, created_at, last_seen_at, updated_at)
                    VALUES (1, 'node-duplicate-test', 'duplicate test', 0,
                            'active', ?, ?, ?)
                    """,
                    (now, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO agent_profile
                    (agent_id, consumer_id, tool_name, display_name, role_type,
                     api_token_hash, sprite_seed, status, created_at, last_seen_at, updated_at)
                    VALUES (1, 1, 'test-tool', 'test agent', 'waiter',
                            'not-a-token', 0, 'active', ?, ?, ?)
                    """,
                    (now, now, now),
                )
                ledger_sql = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' "
                    "AND name='skill_order_ledger'"
                ).fetchone()[0]
                legacy_sql = ledger_sql.replace(
                    "CREATE TABLE skill_order_ledger",
                    "CREATE TABLE skill_order_ledger_legacy",
                    1,
                )
                legacy_sql = re.sub(
                    r",\s*CONSTRAINT\s+uq_skill_order_consumer_free_sequence\s+"
                    r"UNIQUE\s*\([^)]*\)",
                    "",
                    legacy_sql,
                    count=1,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                legacy_sql = legacy_sql.replace("'payment_processing', ", "", 1)
                conn.execute(legacy_sql)
                conn.execute("DROP TABLE skill_order_ledger")
                conn.execute(
                    "ALTER TABLE skill_order_ledger_legacy RENAME TO skill_order_ledger"
                )
                for ledger_id, request_id in ((1, "dup-free-1"), (2, "dup-free-2")):
                    conn.execute(
                        """
                        INSERT INTO skill_order_ledger
                        (ledger_id, consumer_id, agent_id, request_id, coffee_items_json,
                         amount_credits, payment_status, free_order_sequence,
                         version, payment_attempts, created_at, updated_at)
                        VALUES (?, 1, 1, ?, '[]', 0, 'free', 1, 0, 0, ?, ?)
                        """,
                        (ledger_id, request_id, now, now),
                    )
                conn.commit()

            migrated = subprocess.run(
                [sys.executable, "scripts/migrate_order_sources.py"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(migrated.returncode, 0, migrated.stderr + migrated.stdout)
            self.assertIn("duplicate rows require manual reconciliation", migrated.stdout)
            self.assertIn("skipped free-order uniqueness", migrated.stdout)

            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM skill_order_ledger "
                        "WHERE consumer_id=1 AND free_order_sequence=1"
                    ).fetchone()[0],
                    2,
                )


if __name__ == "__main__":
    unittest.main()
