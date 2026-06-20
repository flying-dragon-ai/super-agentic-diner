"""Account auth service: bcrypt password hashing + signed-cookie sessions.

Sessions are signed with itsdangerous using settings.auth_secret_key. The
cookie carries the account_id; the actual account row is re-read on /auth/me.
"""
from __future__ import annotations

import re
from datetime import datetime

from decimal import Decimal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import User, UserAccount
from app.domain_constants import IDENTITY_STATUS_ACTIVE, IDENTITY_STATUSES, WALLET_CURRENCY_CNY
from app.services import wallet_service

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# passlib 1.7 probes a bcrypt __about__ attr removed in bcrypt>=4; the hash/verify
# still works, so silence the noisy internal version probe warning.
try:
    import bcrypt as _bcrypt
    if not hasattr(_bcrypt, "__about__"):
        _bcrypt.__about__ = type("X", (), {"__version__": getattr(_bcrypt, "__version__", "4.0")})()
except Exception:
    pass


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.auth_secret_key, salt="coffee-session")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:
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
    return pw


def register_account(db: Session, username: str, password: str, nickname: str | None) -> UserAccount:
    name = validate_username(username)
    pw = validate_password(password)
    existing = db.query(UserAccount).filter(UserAccount.username == name).first()
    if existing:
        raise ValueError("用户名已存在")
    user = User(nickname=(nickname or name)[:64] or None, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(user)
    db.flush()
    account = UserAccount(
        username=name,
        password_hash=hash_password(pw),
        nickname=(nickname or name)[:64] or None,
        user_id=user.user_id,
        status=IDENTITY_STATUS_ACTIVE,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(account)
    # 新用户注册赠送 ¥100 CNY 钱包（仅新注册触发，已有用户余额不变）
    wallet_service.topup(
        db,
        user_id=user.user_id,
        amount=Decimal("100.00"),
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


def public_account(account: UserAccount) -> dict:
    return {
        "user_id": account.user_id,
        "account_id": account.account_id,
        "username": account.username,
        "nickname": account.nickname,
    }
