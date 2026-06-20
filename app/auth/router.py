"""Auth API router: register/login/logout/me with signed httpOnly cookie session.

Existing /chat ordering keeps working anonymously; this only adds account auth
for the 3D office app. Cookies use SameSite=lax, httponly, signed.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.auth import service as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    nickname: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_cookie_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")


def current_account(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    account_id = auth_service.read_session_token(token)
    if account_id is None:
        return None
    return auth_service.get_account_by_id(db, account_id)


@router.post("/register")
def register(req: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    try:
        account = auth_service.register_account(db, req.username, req.password, req.nickname)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _set_session_cookie(response, auth_service.make_session_token(account.account_id))
    return auth_service.public_account(account)


@router.post("/login")
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    try:
        account = auth_service.authenticate(db, req.username, req.password)
    except ValueError:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    _set_session_cookie(response, auth_service.make_session_token(account.account_id))
    return auth_service.public_account(account)


@router.post("/logout")
def logout(response: Response):
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    account = current_account(request, db)
    if not account:
        raise HTTPException(status_code=401, detail="未登录")
    return auth_service.public_account(account)
