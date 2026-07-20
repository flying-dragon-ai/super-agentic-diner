"""Auth API router: register/login/logout/me with signed httpOnly cookie session.

Existing /chat ordering keeps working anonymously; this only adds account auth
for the 3D office app. Cookies use SameSite=lax, httponly, signed.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.auth import service as auth_service
from app.domain_constants import ACCOUNT_ROLE_ADMIN, IDENTITY_STATUS_ACTIVE
from app.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=64)
    nickname: Optional[str] = Field(default=None, max_length=64)
    gender: Optional[str] = Field(default=None, max_length=16)
    specialty: Optional[str] = Field(default=None, max_length=128)
    profession: Optional[str] = Field(default=None, max_length=128)


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=64)
    gender: Optional[str] = Field(default=None, max_length=16)
    specialty: Optional[str] = Field(default=None, max_length=128)
    profession: Optional[str] = Field(default=None, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=72)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_cookie_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=bool(getattr(settings, "auth_cookie_secure", False)),
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")


def current_account(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    claims = auth_service.read_session_claims(token)
    if claims is None:
        return None
    account_id, session_version = claims
    account = auth_service.get_account_by_id(db, account_id)
    if (
        not account
        or account.status != IDENTITY_STATUS_ACTIVE
        or int(getattr(account, "session_version", 0) or 0) != session_version
    ):
        return None
    return account


def require_account(request: Request, db: Session = Depends(get_db)):
    account = current_account(request, db)
    if not account:
        raise HTTPException(status_code=401, detail={"code": "login_required"})
    return account


def require_admin(request: Request, db: Session = Depends(get_db)):
    account = require_account(request, db)
    if getattr(account, "role", None) != ACCOUNT_ROLE_ADMIN:
        raise HTTPException(status_code=403, detail={"code": "forbidden"})
    return account


@router.post("/register")
def register(
    req: RegisterRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, scope="auth-register", limit=5, window_seconds=300)
    try:
        account = auth_service.register_account(
            db, req.username, req.password, req.nickname,
            gender=req.gender, specialty=req.specialty, profession=req.profession,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _set_session_cookie(
        response,
        auth_service.make_session_token(account.account_id, account.session_version),
    )
    return auth_service.public_account(account)


@router.post("/login")
def login(
    req: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, scope="auth-login", limit=10, window_seconds=300)
    try:
        account = auth_service.authenticate(db, req.username, req.password)
    except ValueError:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    _set_session_cookie(
        response,
        auth_service.make_session_token(account.account_id, account.session_version),
    )
    return auth_service.public_account(account)


@router.post("/logout")
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.auth_cookie_name)
    claims = auth_service.read_session_claims(token) if token else None
    if claims is not None:
        account = auth_service.get_account_by_id(db, claims[0])
        if account is not None and int(account.session_version or 0) == claims[1]:
            account.session_version = int(account.session_version or 0) + 1
            db.commit()
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    account = require_account(request, db)
    return auth_service.public_account(account)


@router.put("/profile")
def update_profile(req: UpdateProfileRequest, request: Request, db: Session = Depends(get_db)):
    account = require_account(request, db)
    try:
        updated = auth_service.update_profile(
            db, account,
            nickname=req.nickname,
            gender=req.gender,
            specialty=req.specialty,
            profession=req.profession,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return auth_service.public_account(updated)
