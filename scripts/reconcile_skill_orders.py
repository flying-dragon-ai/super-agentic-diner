"""Retry local persistence for already-paid EvoMap Skill ledgers.

This command never calls the external payment API. It only processes ledgers in
``needs_reconcile`` (or a stale ``reconciling`` claim) and uses the stored proof
and stock reservation to finish the local order atomically.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.db.database import SessionLocal, engine
from app.db.models import SkillOrderLedger
from app.domain_constants import (
    PAYMENT_STATUS_NEEDS_RECONCILE,
    PAYMENT_STATUS_RECONCILING,
)
from app.services.skill_order_service import SkillOrderError, reconcile_skill_ledger
from scripts.migrate_order_sources import run_migrations


def _candidate_ids(limit: int) -> list[int]:
    db = SessionLocal()
    try:
        return [
            int(row[0])
            for row in (
                db.query(SkillOrderLedger.ledger_id)
                .filter(
                    SkillOrderLedger.payment_status.in_(
                        {PAYMENT_STATUS_NEEDS_RECONCILE, PAYMENT_STATUS_RECONCILING}
                    )
                )
                .order_by(SkillOrderLedger.updated_at.asc())
                .limit(limit)
                .all()
            )
        ]
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finish local orders for externally paid Skill ledgers"
    )
    parser.add_argument("--ledger-id", type=int)
    parser.add_argument("--limit", type=int, default=settings.skill_reconcile_batch_size)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 100:
        parser.error("--limit must be between 1 and 100")

    run_migrations(engine)
    ledger_ids = [args.ledger_id] if args.ledger_id else _candidate_ids(args.limit)
    if not ledger_ids:
        print("No Skill ledgers require reconciliation.")
        return 0

    completed = 0
    failed = 0
    for ledger_id in ledger_ids:
        db = SessionLocal()
        try:
            result = reconcile_skill_ledger(db, int(ledger_id))
            completed += 1
            print(
                f"ledger_id={ledger_id} status={result.get('payment_status')} "
                f"orders={len(result.get('order_ids') or [])}"
            )
        except SkillOrderError as exc:
            failed += 1
            print(f"ledger_id={ledger_id} deferred code={exc.code}")
        finally:
            db.close()

    print(f"Reconciliation complete: completed={completed} deferred={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
