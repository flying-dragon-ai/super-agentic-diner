from __future__ import annotations

import socket
import re
import unittest
from pathlib import Path

import _test_env


class LiveTestGateTests(unittest.TestCase):
    def test_default_live_gate_is_disabled_without_network_probe(self) -> None:
        config = _test_env.live_test_config({})
        self.assertFalse(config.enabled)
        self.assertIn("RUN_LIVE_TESTS=1", config.reason)

    def test_live_gate_requires_url_instance_and_non_default_port(self) -> None:
        missing_url = _test_env.live_test_config({"RUN_LIVE_TESTS": "1"})
        self.assertFalse(missing_url.enabled)
        self.assertIn("LIVE_TEST_BASE_URL", missing_url.reason)

        normal_dev = _test_env.live_test_config(
            {
                "RUN_LIVE_TESTS": "1",
                "LIVE_TEST_BASE_URL": "http://127.0.0.1:8000",
                "LIVE_TEST_INSTANCE_ID": "unsafe-dev",
            }
        )
        self.assertFalse(normal_dev.enabled)
        self.assertIn("8000", normal_dev.reason)

        missing_instance = _test_env.live_test_config(
            {
                "RUN_LIVE_TESTS": "1",
                "LIVE_TEST_BASE_URL": "http://127.0.0.1:8022",
            }
        )
        self.assertFalse(missing_instance.enabled)
        self.assertIn("LIVE_TEST_INSTANCE_ID", missing_instance.reason)

    def test_live_gate_accepts_explicit_disposable_target(self) -> None:
        config = _test_env.live_test_config(
            {
                "RUN_LIVE_TESTS": "1",
                "LIVE_TEST_BASE_URL": "http://127.0.0.1:8022/",
                "LIVE_TEST_INSTANCE_ID": "bugfix-20260712",
            }
        )
        self.assertTrue(config.enabled)
        self.assertEqual(config.base_url, "http://127.0.0.1:8022")


class MysqlTestGateTests(unittest.TestCase):
    def test_mysql_gate_is_disabled_by_default(self) -> None:
        config = _test_env.mysql_test_config({})
        self.assertFalse(config.enabled)
        self.assertIn("RUN_MYSQL_INTEGRATION=1", config.reason)

    def test_mysql_gate_requires_mysql_mode_and_test_suffix(self) -> None:
        sqlite_mode = _test_env.mysql_test_config(
            {
                "RUN_MYSQL_INTEGRATION": "1",
                "DB_MODE": "sqlite",
                "MYSQL_DATABASE": "coffee_ai_test",
            }
        )
        self.assertFalse(sqlite_mode.enabled)
        self.assertIn("DB_MODE=mysql", sqlite_mode.reason)

        production_name = _test_env.mysql_test_config(
            {
                "RUN_MYSQL_INTEGRATION": "1",
                "DB_MODE": "mysql",
                "MYSQL_DATABASE": "coffee_ai",
            }
        )
        self.assertFalse(production_name.enabled)
        self.assertIn("_test", production_name.reason)

    def test_mysql_gate_accepts_explicit_test_database(self) -> None:
        config = _test_env.mysql_test_config(
            {
                "RUN_MYSQL_INTEGRATION": "1",
                "DB_MODE": "mysql",
                "MYSQL_DATABASE": "coffee_ai_integration_test",
            }
        )
        self.assertTrue(config.enabled)
        self.assertEqual(config.database, "coffee_ai_integration_test")


class DefaultIsolationTests(unittest.TestCase):
    def test_default_database_is_process_scoped_and_outside_repo(self) -> None:
        test_db = _test_env.default_sqlite_path().resolve()
        repo = Path(__file__).resolve().parents[1]
        self.assertNotEqual(test_db.name, "coffee_ai.db")
        self.assertNotIn(repo, test_db.parents)

    def test_default_network_access_is_blocked_before_connect(self) -> None:
        self.assertTrue(_test_env.network_is_blocked())
        with self.assertRaises(_test_env.UnexpectedNetworkAccess):
            socket.create_connection(("127.0.0.1", 8000), timeout=0.01)

    def test_every_default_test_bootstraps_before_app_imports(self) -> None:
        tests_dir = Path(__file__).resolve().parent
        missing: list[str] = []
        late: list[str] = []
        for path in sorted(tests_dir.glob("test_*.py")):
            if path.name == Path(__file__).name:
                continue
            source = path.read_text(encoding="utf-8")
            app_positions = [
                match.start()
                for match in re.finditer(
                    r"(?m)^\s*(?:from\s+app\b|import\s+app\b)", source
                )
            ]
            if not app_positions:
                continue
            bootstrap_match = re.search(r"(?m)^import _test_env\b", source)
            if bootstrap_match is None:
                missing.append(path.name)
            elif bootstrap_match.start() > min(app_positions):
                late.append(path.name)
        self.assertEqual(missing, [], f"missing _test_env bootstrap: {missing}")
        self.assertEqual(late, [], f"late _test_env bootstrap: {late}")


if __name__ == "__main__":
    unittest.main()
