"""Schema consistency migration (audit 2026-06-21).

Idempotent + reversible. Dead tables are soft-retired (RENAME TO *_deprecated,
data preserved) rather than DROPped, so the change is recoverable.

  W1  skill_order_ledger.payment_status CHECK: add missing 'refunded'
      (ORM LEDGER_PAYMENT_STATUSES has 8 values; DB CHECK had only 7)
  W2  chat_messages (dead — history moved to Redis): RENAME -> _deprecated
  W3  pending_orders (dead — moved to Redis): RENAME -> _deprecated
  I1  user_account.status: add CHECK for IDENTITY_STATUSES consistency

Run: python scripts/migrate_schema_consistency.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.db.database import SessionLocal


def _check_clause(db, name):
    row = db.execute(
        text(
            "SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = :n"
        ),
        {"n": name},
    ).fetchone()
    return row[0] if row else None


def _table_exists(db, name):
    row = db.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = :n"
        ),
        {"n": name},
    ).fetchone()
    return bool(row)


def fix_ledger_check(db):
    """W1: add 'refunded' to skill_order_ledger.payment_status CHECK."""
    clause = _check_clause(db, "ck_skill_order_ledger_payment_status")
    if clause and "refunded" in clause:
        print("[W1] ledger CHECK already has 'refunded' — skip")
        return
    values = "('free','needs_reconcile','paid','payment_failed','payment_pending','payment_required','pending','refunded')"
    db.execute(
        text("ALTER TABLE skill_order_ledger DROP CHECK ck_skill_order_ledger_payment_status")
    )
    db.execute(
        text(
            "ALTER TABLE skill_order_ledger ADD CONSTRAINT ck_skill_order_ledger_payment_status "
            f"CHECK (payment_status IN {values})"
        )
    )
    print("[W1] ledger CHECK updated (added 'refunded')")


def add_user_account_check(db):
    """I1: add status CHECK to user_account (after validating existing rows)."""
    if _check_clause(db, "ck_user_account_status"):
        print("[I1] ck_user_account_status already exists — skip")
        return
    bad = db.execute(
        text(
            "SELECT COUNT(*) FROM user_account "
            "WHERE status NOT IN ('active','inactive','disabled')"
        )
    ).scalar()
    if bad:
        print(f"[I1] SKIP — {bad} user_account rows violate IDENTITY_STATUSES; fix data first")
        return
    db.execute(
        text(
            "ALTER TABLE user_account ADD CONSTRAINT ck_user_account_status "
            "CHECK (status IN ('active','inactive','disabled'))"
        )
    )
    print("[I1] ck_user_account_status added")


def soft_retire(db, table):
    """W2/W3: RENAME dead table TO <table>_deprecated (data preserved, reversible)."""
    if not _table_exists(db, table):
        print(f"[{table}] not found — skip")
        return
    deprecated = f"{table}_deprecated"
    if _table_exists(db, deprecated):
        print(f"[{table}] already retired -> {deprecated} — skip")
        return
    db.execute(text(f"RENAME TABLE {table} TO {deprecated}"))
    print(f"[{table}] soft-retired -> {deprecated} (data preserved)")


def main():
    db = SessionLocal()
    try:
        fix_ledger_check(db)
        add_user_account_check(db)
        soft_retire(db, "chat_messages")
        soft_retire(db, "pending_orders")
        print("\nDone.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
