from __future__ import annotations

import _test_env  # noqa: F401 - isolate SQLite/fakeredis before app imports

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import rate_limit
from app.db.database import SessionLocal
from app.db.models import (
    AgentProfile,
    EvomapConsumer,
    Order,
    Product,
    SkillDeviceAuthorization,
    UserAccount,
)
from app.main import app


@pytest.fixture(autouse=True)
def _isolate_rate_limits() -> None:
    """Keep this module's independent TestClient cases out of one shared IP bucket."""
    with rate_limit._local_lock:
        rate_limit._local_windows.clear()


def _register(client: TestClient, prefix: str) -> str:
    username = f"{prefix}_{uuid4().hex[:8]}"
    response = client.post(
        "/auth/register",
        json={"username": username, "password": "safe-password-123", "nickname": prefix},
    )
    assert response.status_code == 200, response.text
    return username


def _start(client: TestClient, node_id: str) -> dict:
    response = client.post(
        "/skill/auth/device/start",
        headers={"X-Evomap-Node-Secret": "local-dev"},
        json={
            "tool_name": "codex",
            "display_name": "Codex Test",
            "evomap_node_id": node_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _authorize(client: TestClient, node_id: str) -> dict:
    started = _start(client, node_id)
    pending = client.post(
        "/skill/auth/device/token", json={"device_code": started["device_code"]}
    )
    assert pending.status_code == 202
    approved = client.post(
        "/skill/auth/device/approve", json={"user_code": started["user_code"]}
    )
    assert approved.status_code == 200, approved.text
    token = client.post(
        "/skill/auth/device/token", json={"device_code": started["device_code"]}
    )
    assert token.status_code == 200, token.text
    replay = client.post(
        "/skill/auth/device/token", json={"device_code": started["device_code"]}
    )
    assert replay.status_code == 409
    return token.json()


def test_device_login_me_menu_and_logout() -> None:
    with TestClient(app) as client:
        username = _register(client, "skill_login")
        token_data = _authorize(client, f"node-{uuid4().hex}")
        headers = {"Authorization": f"Bearer {token_data['api_token']}"}

        me = client.get("/skill/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["username"] == username
        assert me.json()["currency"] == "CNY"
        assert me.json()["balance"] == 50.0

        assert client.get("/skill/menu").status_code == 401
        assert client.get("/skill/menu", headers=headers).status_code == 200

        assert client.post("/skill/logout", headers=headers).status_code == 200
        assert client.get("/skill/me", headers=headers).status_code == 401


def test_skill_discovery_is_anonymous_and_identifies_service() -> None:
    with TestClient(app) as client:
        response = client.get("/skill/discovery")
    assert response.status_code == 200
    assert response.json() == {
        "service": "crossroads-agent-cafe",
        "protocol_version": 1,
        "name": "Crossroads Agent Café",
    }


def test_skill_order_debits_cny_once() -> None:
    product_name = f"测试咖啡-{uuid4().hex[:6]}"
    with SessionLocal() as db:
        db.add(
            Product(
                sku=f"test-{uuid4().hex}",
                name=product_name,
                category="test",
                description="device auth integration product",
                base_price=Decimal("12.00"),
                tags="test",
                status="available",
                stock=5,
            )
        )
        db.commit()

    with TestClient(app) as client:
        _register(client, "skill_order")
        token_data = _authorize(client, f"node-{uuid4().hex}")
        headers = {"Authorization": f"Bearer {token_data['api_token']}"}
        payload = {
            "consumer_id": token_data["consumer_id"],
            "agent_id": token_data["agent_id"],
            "message": f"一杯{product_name}",
            "request_id": f"req-{uuid4().hex}",
            "auto_confirm": True,
        }

        first = client.post("/skill/orders", json=payload, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["amount_cny"] == 12.0
        assert first.json()["amount_credits"] == 0
        assert first.json()["balance_after"] == 38.0
        assert first.json()["free_orders_remaining"] == 0

        retry = client.post("/skill/orders", json=payload, headers=headers)
        assert retry.status_code == 200, retry.text
        assert retry.json()["order_ids"] == first.json()["order_ids"]
        assert retry.json()["balance_after"] == 38.0


def test_node_cannot_be_rebound_to_another_account() -> None:
    node_id = f"node-{uuid4().hex}"
    with TestClient(app) as owner:
        _register(owner, "owner")
        _authorize(owner, node_id)

    with TestClient(app) as other:
        _register(other, "other")
        started = _start(other, node_id)
        denied = other.post(
            "/skill/auth/device/approve", json={"user_code": started["user_code"]}
        )
        assert denied.status_code == 409
        assert denied.json()["detail"]["code"] == "node_bound_to_another_account"
        unbind = other.post(
            "/skill/auth/device/unbind", json={"user_code": started["user_code"]}
        )
        assert unbind.status_code == 403
        assert unbind.json()["detail"]["code"] == "node_binding_owner_required"


def test_binding_owner_can_unbind_and_switch_account() -> None:
    node_id = f"node-{uuid4().hex}"
    with TestClient(app) as client:
        owner_username = _register(client, "switch_owner")
        first = _authorize(client, node_id)
        first_headers = {"Authorization": f"Bearer {first['api_token']}"}

        with SessionLocal() as db:
            owner_account = db.query(UserAccount).filter(
                UserAccount.username == owner_username
            ).one()
            historical_user_id = owner_account.user_id
            historical = Order(
                user_id=historical_user_id,
                coffee_name="历史 Skill 订单",
                amount=Decimal("1.00"),
                total_amount=Decimal("1.00"),
                status=1,
                request_id=f"history-{uuid4().hex}",
                source_type="skill",
                payment_status="paid",
                consumer_id=first["consumer_id"],
                agent_id=first["agent_id"],
            )
            db.add(historical)
            db.commit()
            historical_order_id = historical.order_id

        pending = _start(client, node_id)
        unbind = client.post(
            "/skill/auth/device/unbind", json={"user_code": pending["user_code"]}
        )
        assert unbind.status_code == 200, unbind.text
        assert unbind.json()["status"] == "unbound"
        assert client.get("/skill/me", headers=first_headers).status_code == 401

        with SessionLocal() as db:
            consumer = db.query(EvomapConsumer).filter(
                EvomapConsumer.evomap_node_id == node_id
            ).one()
            assert consumer.local_user_id is None
            assert db.query(AgentProfile).filter(
                AgentProfile.consumer_id == consumer.consumer_id,
                AgentProfile.status == "active",
            ).count() == 0

        assert client.post("/auth/logout").status_code == 200
        replacement = _register(client, "switch_replacement")
        approved = client.post(
            "/skill/auth/device/approve", json={"user_code": pending["user_code"]}
        )
        assert approved.status_code == 200, approved.text
        exchanged = client.post(
            "/skill/auth/device/token", json={"device_code": pending["device_code"]}
        )
        assert exchanged.status_code == 200, exchanged.text
        assert exchanged.json()["username"] == replacement

        with SessionLocal() as db:
            historical = db.query(Order).filter(
                Order.order_id == historical_order_id
            ).one()
            consumer = db.query(EvomapConsumer).filter(
                EvomapConsumer.evomap_node_id == node_id
            ).one()
            replacement_account = db.query(UserAccount).filter(
                UserAccount.username == replacement
            ).one()
            assert historical.user_id == historical_user_id
            assert consumer.local_user_id == replacement_account.user_id


def test_unbind_allows_switch_when_node_has_no_existing_binding() -> None:
    with TestClient(app) as client:
        _register(client, "switch_unbound")
        pending = _start(client, f"node-{uuid4().hex}")
        response = client.post(
            "/skill/auth/device/unbind", json={"user_code": pending["user_code"]}
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "not_bound"


def test_insufficient_cny_does_not_consume_stock() -> None:
    product_name = f"高价测试咖啡-{uuid4().hex[:6]}"
    sku = f"test-{uuid4().hex}"
    with SessionLocal() as db:
        db.add(
            Product(
                sku=sku,
                name=product_name,
                category="test",
                description="insufficient balance product",
                base_price=Decimal("80.00"),
                tags="test",
                status="available",
                stock=3,
            )
        )
        db.commit()

    with TestClient(app) as client:
        _register(client, "low_balance")
        token_data = _authorize(client, f"node-{uuid4().hex}")
        headers = {"Authorization": f"Bearer {token_data['api_token']}"}
        response = client.post(
            "/skill/orders",
            headers=headers,
            json={
                "consumer_id": token_data["consumer_id"],
                "agent_id": token_data["agent_id"],
                "message": f"一杯{product_name}",
                "request_id": f"req-{uuid4().hex}",
                "auto_confirm": True,
            },
        )
        assert response.status_code == 402
        assert response.json()["detail"]["code"] == "insufficient_balance"
        assert client.get("/skill/me", headers=headers).json()["balance"] == 50.0

    with SessionLocal() as db:
        product = db.query(Product).filter(Product.sku == sku).one()
        assert product.stock == 3


def test_device_denial_expiry_and_token_rotation() -> None:
    node_id = f"node-{uuid4().hex}"
    with TestClient(app) as client:
        _register(client, "device_edges")
        first = _authorize(client, node_id)
        first_headers = {"Authorization": f"Bearer {first['api_token']}"}

        second = _authorize(client, node_id)
        second_headers = {"Authorization": f"Bearer {second['api_token']}"}
        assert client.get("/skill/me", headers=first_headers).status_code == 401
        assert client.get("/skill/me", headers=second_headers).status_code == 200

        denied = _start(client, f"node-{uuid4().hex}")
        assert client.post(
            "/skill/auth/device/deny", json={"user_code": denied["user_code"]}
        ).status_code == 200
        denied_exchange = client.post(
            "/skill/auth/device/token", json={"device_code": denied["device_code"]}
        )
        assert denied_exchange.status_code == 403

        expired = _start(client, f"node-{uuid4().hex}")
        with SessionLocal() as db:
            row = db.query(SkillDeviceAuthorization).filter(
                SkillDeviceAuthorization.status == "pending"
            ).order_by(SkillDeviceAuthorization.authorization_id.desc()).first()
            assert row is not None
            row.expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        expired_exchange = client.post(
            "/skill/auth/device/token", json={"device_code": expired["device_code"]}
        )
        assert expired_exchange.status_code == 410
