"""Account auth service: bcrypt password hashing + signed-cookie sessions.

Sessions are signed with itsdangerous using settings.auth_secret_key. The
cookie carries the account_id; the actual account row is re-read on /auth/me.
"""
from __future__ import annotations

import re
from datetime import datetime

import bcrypt
from decimal import Decimal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import User, UserAccount
from app.domain_constants import IDENTITY_STATUS_ACTIVE, IDENTITY_STATUSES, WALLET_CURRENCY_CNY
from app.services import wallet_service

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.auth_secret_key, salt="coffee-session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (TypeError, ValueError, UnicodeEncodeError):
        return False


def make_session_token(account_id: int) -> str:
    return _serializer().dumps({"aid": account_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer().loads(token, max_age=settings.auth_cookie_max_age_seconds)
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    aid = data.get("aid") if isinstance(data, dict) else None
    return int(aid) if aid is not None else None


def validate_username(username: str) -> str:
    name = (username or "").strip()
    if not _USERNAME_RE.match(name):
        raise ValueError("用户名需为 3-32 位字母数字、下划线、点或连字符")
    return name


def validate_password(password: str) -> str:
    pw = password or ""
    if len(pw) < 6 or len(pw) > 64:
        raise ValueError("密码长度需在 6-64 位之间")
    if len(pw.encode("utf-8")) > 72:
        raise ValueError("密码 UTF-8 编码后不能超过 72 字节")
    return pw


def register_account(
    db: Session,
    username: str,
    password: str,
    nickname: str | None,
    gender: str | None = None,
    specialty: str | None = None,
    profession: str | None = None,
) -> UserAccount:
    name = validate_username(username)
    pw = validate_password(password)
    existing = db.query(UserAccount).filter(UserAccount.username == name).first()
    if existing:
        raise ValueError("用户名已存在")
    user = User(nickname=(nickname or name)[:64] or None, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(user)
    db.flush()
    # username "001" gets default specialty "首席战略咨询"
    default_specialty = "首席战略咨询" if name == "001" else specialty
    account = UserAccount(
        username=name,
        password_hash=hash_password(pw),
        nickname=(nickname or name)[:64] or None,
        gender=(gender[:16] if gender else None),
        specialty=(default_specialty[:128] if default_specialty else None),
        profession=(profession[:128] if profession else None),
        user_id=user.user_id,
        status=IDENTITY_STATUS_ACTIVE,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(account)
    # 新用户注册赠送 ¥50 CNY 钱包（仅新注册触发，已有用户余额不变）
    wallet_service.topup(
        db,
        user_id=user.user_id,
        amount=Decimal("50.00"),
        currency=WALLET_CURRENCY_CNY,
        note="新用户注册赠送",
    )
    db.commit()
    db.refresh(account)
    return account


def authenticate(db: Session, username: str, password: str) -> UserAccount:
    name = (username or "").strip()
    account = db.query(UserAccount).filter(UserAccount.username == name).first()
    if not account or account.status not in IDENTITY_STATUSES or account.status != IDENTITY_STATUS_ACTIVE:
        raise ValueError("用户名或密码错误")
    if not verify_password(password, account.password_hash):
        raise ValueError("用户名或密码错误")
    return account


def get_account_by_id(db: Session, account_id: int) -> UserAccount | None:
    return db.query(UserAccount).filter(UserAccount.account_id == account_id).first()


def update_profile(
    db: Session,
    account: UserAccount,
    *,
    nickname: str | None = None,
    gender: str | None = None,
    specialty: str | None = None,
    profession: str | None = None,
) -> UserAccount:
    """Update editable profile fields. None = leave unchanged, empty string = clear."""
    if nickname is not None:
        account.nickname = nickname.strip()[:64] or None
    if gender is not None:
        g = gender.strip().lower()
        if g and g not in ("male", "female", "other"):
            raise ValueError("gender 需为 male / female / other")
        account.gender = g or None
    if specialty is not None:
        account.specialty = specialty.strip()[:128] or None
    if profession is not None:
        account.profession = profession.strip()[:128] or None
    account.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(account)
    return account


def public_account(account: UserAccount) -> dict:
    return {
        "user_id": account.user_id,
        "account_id": account.account_id,
        "username": account.username,
        "nickname": account.nickname,
        "gender": getattr(account, "gender", None),
        "specialty": getattr(account, "specialty", None),
        "profession": getattr(account, "profession", None),
    }
