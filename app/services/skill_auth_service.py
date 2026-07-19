"""Browser device authorization for the A2A ordering Skill.

Passwords remain in the existing web account flow.  The CLI receives only a
short-lived opaque device code and, after browser approval, a scoped Agent
token that can be revoked independently of the web session.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import (
    AgentProfile,
    EvomapConsumer,
    SkillDeviceAuthorization,
    UserAccount,
)
from app.domain_constants import (
    DEVICE_AUTH_STATUS_APPROVED,
    DEVICE_AUTH_STATUS_CONSUMED,
    DEVICE_AUTH_STATUS_DENIED,
    DEVICE_AUTH_STATUS_EXPIRED,
    DEVICE_AUTH_STATUS_PENDING,
    IDENTITY_STATUS_ACTIVE,
    IDENTITY_STATUS_INACTIVE,
    WALLET_CURRENCY_CNY,
)
from app.services import wallet_service
from app.services.visualization_service import (
    generate_agent_token,
    hash_agent_token,
    make_sprite_seed,
)


DEVICE_AUTH_TTL_SECONDS = 600
DEVICE_AUTH_POLL_INTERVAL_SECONDS = 2
SKILL_SCOPES = ("profile:read", "wallet:read", "order:create")
_USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class SkillAuthError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_user_code() -> str:
    raw = "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _normalize_user_code(value: str) -> str:
    compact = "".join(ch for ch in value.upper() if ch.isalnum())
    if len(compact) != 8:
        raise SkillAuthError("invalid_user_code", "授权码格式无效")
    return f"{compact[:4]}-{compact[4:]}"


def start_authorization(
    db: Session,
    *,
    evomap_node_id: str,
    evomap_did: str | None,
    tool_name: str,
    display_name: str,
) -> tuple[SkillDeviceAuthorization, str, str]:
    now = datetime.utcnow()
    for _ in range(8):
        device_code = secrets.token_urlsafe(32)
        user_code = _new_user_code()
        if not db.query(SkillDeviceAuthorization).filter(
            SkillDeviceAuthorization.device_code_hash == _hash(device_code)
        ).first() and not db.query(SkillDeviceAuthorization).filter(
            SkillDeviceAuthorization.user_code_hash == _hash(user_code)
        ).first():
            break
    else:
        raise SkillAuthError("code_generation_failed", "无法生成授权码", http_status=503)

    row = SkillDeviceAuthorization(
        device_code_hash=_hash(device_code),
        user_code_hash=_hash(user_code),
        evomap_node_id=evomap_node_id.strip(),
        evomap_did=(evomap_did or "").strip() or None,
        tool_name=tool_name.strip(),
        display_name=display_name.strip(),
        scopes_json=json.dumps(SKILL_SCOPES),
        status=DEVICE_AUTH_STATUS_PENDING,
        expires_at=now + timedelta(seconds=DEVICE_AUTH_TTL_SECONDS),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, device_code, user_code


def _active_authorization_by_user_code(
    db: Session, user_code: str
) -> SkillDeviceAuthorization:
    normalized = _normalize_user_code(user_code)
    row = db.query(SkillDeviceAuthorization).filter(
        SkillDeviceAuthorization.user_code_hash == _hash(normalized)
    ).first()
    if row is None:
        raise SkillAuthError("invalid_user_code", "授权码不存在", http_status=404)
    if row.expires_at <= datetime.utcnow():
        if row.status == DEVICE_AUTH_STATUS_PENDING:
            row.status = DEVICE_AUTH_STATUS_EXPIRED
            row.updated_at = datetime.utcnow()
            db.commit()
        raise SkillAuthError("authorization_expired", "授权码已过期", http_status=410)
    return row


def approve_authorization(
    db: Session, *, user_code: str, account: UserAccount
) -> SkillDeviceAuthorization:
    row = _active_authorization_by_user_code(db, user_code)
    if row.status != DEVICE_AUTH_STATUS_PENDING:
        raise SkillAuthError("authorization_not_pending", "授权请求已处理", http_status=409)

    consumer = db.query(EvomapConsumer).filter(
        EvomapConsumer.evomap_node_id == row.evomap_node_id
    ).first()
    if consumer is not None and consumer.local_user_id is not None:
        linked = db.query(UserAccount).filter(
            UserAccount.user_id == consumer.local_user_id
        ).first()
        if linked is not None and linked.account_id != account.account_id:
            raise SkillAuthError(
                "node_bound_to_another_account",
                "该 EvoMap 节点已绑定其他账号，不能直接换绑",
                http_status=409,
            )

    row.account_id = account.account_id
    row.status = DEVICE_AUTH_STATUS_APPROVED
    row.approved_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def deny_authorization(
    db: Session, *, user_code: str, account: UserAccount
) -> SkillDeviceAuthorization:
    row = _active_authorization_by_user_code(db, user_code)
    if row.status != DEVICE_AUTH_STATUS_PENDING:
        raise SkillAuthError("authorization_not_pending", "授权请求已处理", http_status=409)
    row.account_id = account.account_id
    row.status = DEVICE_AUTH_STATUS_DENIED
    row.updated_at = datetime.utcnow()
    db.commit()
    return row


def exchange_device_code(
    db: Session, *, device_code: str
) -> tuple[str, AgentProfile, EvomapConsumer, UserAccount] | None:
    row = db.query(SkillDeviceAuthorization).filter(
        SkillDeviceAuthorization.device_code_hash == _hash(device_code)
    ).first()
    if row is None:
        raise SkillAuthError("invalid_device_code", "设备授权请求不存在", http_status=404)
    now = datetime.utcnow()
    if row.expires_at <= now:
        if row.status in {DEVICE_AUTH_STATUS_PENDING, DEVICE_AUTH_STATUS_APPROVED}:
            row.status = DEVICE_AUTH_STATUS_EXPIRED
            row.updated_at = now
            db.commit()
        raise SkillAuthError("authorization_expired", "设备授权已过期", http_status=410)
    if row.status == DEVICE_AUTH_STATUS_PENDING:
        return None
    if row.status == DEVICE_AUTH_STATUS_DENIED:
        raise SkillAuthError("authorization_denied", "用户拒绝了授权", http_status=403)
    if row.status == DEVICE_AUTH_STATUS_CONSUMED:
        raise SkillAuthError("device_code_consumed", "设备授权码已兑换", http_status=409)
    if row.status != DEVICE_AUTH_STATUS_APPROVED or row.account_id is None:
        raise SkillAuthError("authorization_invalid", "设备授权状态无效", http_status=409)

    account = db.query(UserAccount).filter(
        UserAccount.account_id == row.account_id,
        UserAccount.status == IDENTITY_STATUS_ACTIVE,
    ).first()
    if account is None:
        raise SkillAuthError("account_unavailable", "授权账号不可用", http_status=403)

    consumer = db.query(EvomapConsumer).filter(
        EvomapConsumer.evomap_node_id == row.evomap_node_id
    ).first()
    display_name = account.nickname or account.username
    if consumer is None:
        consumer = EvomapConsumer(
            evomap_node_id=row.evomap_node_id,
            evomap_did=row.evomap_did,
            display_name=display_name,
            local_user_id=account.user_id,
            free_orders_used=0,
            status=IDENTITY_STATUS_ACTIVE,
            created_at=now,
            last_seen_at=now,
        )
        db.add(consumer)
        db.flush()
    else:
        linked = None
        if consumer.local_user_id is not None:
            linked = db.query(UserAccount).filter(
                UserAccount.user_id == consumer.local_user_id
            ).first()
        if linked is not None and linked.account_id != account.account_id:
            raise SkillAuthError(
                "node_bound_to_another_account",
                "该 EvoMap 节点已绑定其他账号",
                http_status=409,
            )
        consumer.local_user_id = account.user_id
        consumer.display_name = display_name
        consumer.evomap_did = row.evomap_did or consumer.evomap_did
        consumer.status = IDENTITY_STATUS_ACTIVE
        consumer.last_seen_at = now

    # A legacy /skill/register token must not become account-capable merely
    # because its consumer was later linked. Reauthorization rotates the node's
    # Skill credential and revokes every previously issued Agent token.
    db.query(AgentProfile).filter(
        AgentProfile.consumer_id == consumer.consumer_id,
        AgentProfile.status == IDENTITY_STATUS_ACTIVE,
    ).update({AgentProfile.status: IDENTITY_STATUS_INACTIVE}, synchronize_session=False)

    token = generate_agent_token()
    agent = AgentProfile(
        consumer_id=consumer.consumer_id,
        tool_name=row.tool_name,
        display_name=display_name,
        role_type="customer",
        capabilities_json=json.dumps(["a2a_super_order", *SKILL_SCOPES]),
        metadata_json=json.dumps(
            {"source": "a2a-super-order-skill", "account_id": account.account_id}
        ),
        api_token_hash=hash_agent_token(token),
        sprite_seed=make_sprite_seed(),
        status=IDENTITY_STATUS_ACTIVE,
        created_at=now,
        last_seen_at=now,
    )
    db.add(agent)
    db.flush()
    row.consumer_id = consumer.consumer_id
    row.agent_id = agent.agent_id
    row.status = DEVICE_AUTH_STATUS_CONSUMED
    row.consumed_at = now
    row.updated_at = now
    db.commit()
    db.refresh(agent)
    db.refresh(consumer)
    return token, agent, consumer, account


def account_for_agent(
    db: Session, agent: AgentProfile
) -> tuple[EvomapConsumer, UserAccount]:
    if agent.consumer_id is None:
        raise SkillAuthError("account_login_required", "Skill 尚未绑定用户账号", http_status=401)
    consumer = db.query(EvomapConsumer).filter(
        EvomapConsumer.consumer_id == agent.consumer_id,
        EvomapConsumer.status == IDENTITY_STATUS_ACTIVE,
    ).first()
    if consumer is None or consumer.local_user_id is None:
        raise SkillAuthError("account_login_required", "Skill 尚未绑定用户账号", http_status=401)
    account = db.query(UserAccount).filter(
        UserAccount.user_id == consumer.local_user_id,
        UserAccount.status == IDENTITY_STATUS_ACTIVE,
    ).first()
    if account is None:
        raise SkillAuthError("account_login_required", "Skill 尚未绑定用户账号", http_status=401)
    return consumer, account


def public_skill_account(
    db: Session, *, agent: AgentProfile, consumer: EvomapConsumer, account: UserAccount
) -> dict:
    balance = wallet_service.get_balance(db, account.user_id, WALLET_CURRENCY_CNY)
    return {
        "authenticated": True,
        "username": account.username,
        "nickname": account.nickname,
        "display_name": account.nickname or account.username,
        "currency": WALLET_CURRENCY_CNY,
        "balance": float(Decimal(balance)),
        "consumer_id": consumer.consumer_id,
        "agent_id": agent.agent_id,
        "evomap_node_id": consumer.evomap_node_id,
        "scopes": list(SKILL_SCOPES),
    }
