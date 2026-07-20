"""Explicit one-time administrator bootstrap command.

Examples::

    python scripts/bootstrap_admin.py --username cafe-admin
    secret-tool lookup service coffee-admin | python scripts/bootstrap_admin.py \
        --username cafe-admin --password-stdin
    python scripts/bootstrap_admin.py --username existing-user --promote-existing

Passwords are never accepted as command-line values and are never printed.
Existing accounts are not promoted unless ``--promote-existing`` is supplied.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import service as auth_service  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import User, UserAccount  # noqa: E402
from app.domain_constants import (  # noqa: E402
    ACCOUNT_ROLE_ADMIN,
    IDENTITY_STATUS_ACTIVE,
)
from scripts.migrate_order_sources import main as migrate_schema  # noqa: E402


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin and args.password_file:
        raise ValueError("Choose only one of --password-stdin or --password-file")
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    elif args.password_file:
        password = Path(args.password_file).read_text(encoding="utf-8").splitlines()[0]
    else:
        password = getpass.getpass("New admin password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Password confirmation does not match")
    return auth_service.validate_password(password)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or explicitly promote one admin account")
    parser.add_argument(
        "--username",
        default=settings.admin_bootstrap_username,
        help="admin username; defaults to ADMIN_BOOTSTRAP_USERNAME",
    )
    parser.add_argument("--nickname", default="Administrator")
    parser.add_argument(
        "--promote-existing",
        action="store_true",
        help="explicitly promote an existing active account without changing its password",
    )
    secret_source = parser.add_mutually_exclusive_group()
    secret_source.add_argument(
        "--password-stdin",
        action="store_true",
        help="read a new-account password from one stdin line",
    )
    secret_source.add_argument(
        "--password-file",
        help="read a new-account password from the first line of a protected file",
    )
    args = parser.parse_args(argv)

    try:
        username = auth_service.validate_username(args.username)
    except ValueError as exc:
        parser.error(str(exc))

    migrate_schema()
    db = SessionLocal()
    try:
        account = db.query(UserAccount).filter(UserAccount.username == username).first()
        if account is not None:
            if account.role == ACCOUNT_ROLE_ADMIN:
                print(f"Admin account {username!r} already exists; no changes made.")
                return 0
            if not args.promote_existing:
                print(
                    f"Account {username!r} already exists as role={account.role!r}; "
                    "rerun with --promote-existing to grant admin explicitly.",
                    file=sys.stderr,
                )
                return 2
            if account.status != IDENTITY_STATUS_ACTIVE:
                print(
                    f"Account {username!r} is not active; reactivate it through an audited "
                    "account-management workflow before promotion.",
                    file=sys.stderr,
                )
                return 3
            account.role = ACCOUNT_ROLE_ADMIN
            # Privilege changes revoke every previously issued user session so
            # an old or stolen cookie cannot silently inherit admin access.
            account.session_version = int(account.session_version or 0) + 1
            account.updated_at = datetime.utcnow()
            db.commit()
            print(f"Promoted existing account {username!r} to admin.")
            return 0

        try:
            password = _read_password(args)
        except (OSError, IndexError, ValueError) as exc:
            print(f"Unable to read a valid admin password: {exc}", file=sys.stderr)
            return 4

        now = datetime.utcnow()
        user = User(
            nickname=(args.nickname or username).strip()[:64] or username,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        account = UserAccount(
            username=username,
            password_hash=auth_service.hash_password(password),
            nickname=user.nickname,
            role=ACCOUNT_ROLE_ADMIN,
            user_id=user.user_id,
            status=IDENTITY_STATUS_ACTIVE,
            created_at=now,
            updated_at=now,
        )
        db.add(account)
        db.commit()
        print(f"Created admin account {username!r}. No demo balance or seed data was added.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
