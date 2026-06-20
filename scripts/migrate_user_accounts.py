"""Idempotent migration for the user_account login table.

Safe to run more than once: creates the table if missing, and adds the
username unique index if absent. Never drops data. Does NOT touch the existing
order/user/agent_profile tables.

Usage: python -m scripts.migrate_user_accounts
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.database import engine
from app.db.models import UserAccount


def main() -> None:
    inspector = inspect(engine)
    table_name = UserAccount.__tablename__
    if table_name not in inspector.get_table_names():
        print(f"[migrate] creating table {table_name}")
        UserAccount.__table__.create(engine, checkfirst=True)
    else:
        print(f"[migrate] table {table_name} already exists")
    # username uniqueness is already enforced by the column (unique=True at
    # create time); nothing extra to do for a fresh table.
    indexes = inspector.get_indexes(table_name)
    print(f"[migrate] existing indexes: {[i['name'] for i in indexes]}")


if __name__ == "__main__":
    main()
