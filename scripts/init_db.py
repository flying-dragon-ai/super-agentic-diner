"""Initialize the schema, with demo data available only by explicit opt-in.

Usage::

    python scripts/init_db.py
    python scripts/init_db.py --seed-demo

``SEED_DEMO_DATA=true`` is also accepted for local demo environments. The
default path is deliberately schema-only: production startup must never create
the fixed demo account, wallet top-up, or sample order data implicitly.
"""
import argparse
import os
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，方便直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.migrate_order_sources import main as migrate_schema


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Initialize the Crossroads Agent Cafe database")
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="explicitly add local demo products, user, wallet credit, and login account",
    )
    args = parser.parse_args(argv)

    print("Initializing and migrating schema ...")
    migrate_schema()

    if args.seed_demo or _env_flag("SEED_DEMO_DATA"):
        from app.db.seed import seed

        print("SEED_DEMO_DATA enabled; adding demo data ...")
        seed()
    else:
        print("Schema ready. Demo data was not created.")

    print("Done. Start with: uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
