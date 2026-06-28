from __future__ import annotations

import unittest
from unittest.mock import Mock, call

from sqlalchemy import text

from scripts import migrate_order_sources


class _ScalarResult:
    def __init__(self, value: int):
        self.value = value

    def scalar(self) -> int:
        return self.value


class OfficeLayoutMysqlMigrationTests(unittest.TestCase):
    def test_missing_table_creates_office_layout(self):
        conn = Mock()

        def execute(statement, params=None):
            sql = str(statement)
            if "information_schema.TABLES" in sql and params == {"table_name": "office_layout"}:
                return _ScalarResult(0)
            return _ScalarResult(0)

        conn.execute.side_effect = execute

        migrate_order_sources._ensure_office_layout_table(conn)

        executed_sql = "\n".join(str(args[0]) for args, _ in conn.execute.call_args_list)
        self.assertIn("CREATE TABLE `office_layout`", executed_sql)
        self.assertIn("UNIQUE KEY `uq_office_layout_namespace`", executed_sql)
        self.assertIn("KEY `idx_office_layout_namespace`", executed_sql)

    def test_existing_table_adds_missing_unique_and_index(self):
        conn = Mock()

        def execute(statement, params=None):
            sql = str(statement)
            if "information_schema.TABLES" in sql and params == {"table_name": "office_layout"}:
                return _ScalarResult(1)
            if "information_schema.STATISTICS" in sql:
                return _ScalarResult(0)
            return _ScalarResult(0)

        conn.execute.side_effect = execute

        migrate_order_sources._ensure_office_layout_table(conn)

        executed_sql = "\n".join(str(args[0]) for args, _ in conn.execute.call_args_list)
        self.assertIn("ALTER TABLE `office_layout`", executed_sql)
        self.assertIn("ADD CONSTRAINT `uq_office_layout_namespace`", executed_sql)
        self.assertIn("CREATE INDEX `idx_office_layout_namespace`", executed_sql)

    def test_existing_table_with_constraints_is_noop_after_checks(self):
        conn = Mock()

        def execute(statement, params=None):
            sql = str(statement)
            if "information_schema.TABLES" in sql and params == {"table_name": "office_layout"}:
                return _ScalarResult(1)
            if "information_schema.STATISTICS" in sql:
                return _ScalarResult(1)
            return _ScalarResult(0)

        conn.execute.side_effect = execute

        migrate_order_sources._ensure_office_layout_table(conn)

        executed_sql = [str(args[0]) for args, _ in conn.execute.call_args_list]
        self.assertEqual(
            executed_sql,
            [
                str(
                    text(
                        """
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
            """
                    )
                ),
                str(
                    text(
                        """
            SELECT COUNT(*)
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
              AND NON_UNIQUE = 0
            """
                    )
                ),
                str(
                    text(
                        """
            SELECT COUNT(*)
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND INDEX_NAME = :index_name
            """
                    )
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
