from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports

import asyncio
import json
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fakeredis
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import main as app_main
from app import rate_limit
from app.auth import service as auth_service
from app.config import Settings, settings
from app.db.database import Base
from app.db.models import (
    AgentProfile,
    BalanceTransaction,
    EvomapConsumer,
    OfficeLayout,
    Order,
    OrderItem,
    Product,
    SkillOrderLedger,
    User,
    UserAccount,
    UserWallet,
)
from app.domain_constants import (
    ACCOUNT_ROLE_ADMIN,
    ACCOUNT_ROLE_USER,
    IDENTITY_STATUS_ACTIVE,
    PAYMENT_STATUS_NEEDS_RECONCILE,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PAYMENT_PROCESSING,
    PAYMENT_STATUS_PAYMENT_REQUIRED,
    PRODUCT_STATUS_AVAILABLE,
    PRODUCT_STATUS_SOLD_OUT,
    STOCK_RESERVATION_CONSUMED,
    STOCK_RESERVATION_RESERVED,
    WALLET_CURRENCY_CNY,
    WALLET_CURRENCY_CREDITS,
)
from app.memory import _redis_client, chat_history
from app.request_limits import RequestBodyLimitMiddleware
from app.services import (
    catalog_service,
    evomap_evolution_service,
    skill_order_service,
    user_profile_service,
    wallet_service,
)
from app.services.visualization_service import encode_json, hash_agent_token


def _reset_process_local_state() -> None:
    """Give every test a private FakeRedis server and empty local fallbacks."""

    _redis_client._fake_server = fakeredis.FakeServer()
    with rate_limit._local_lock:
        rate_limit._local_windows.clear()
    with app_main._visitor_chat_lock:
        app_main._visitor_chat_buffer.clear()
    app_main._online_visitors.clear()


@contextmanager
def _quiet_chat_runtime():
    """Disable best-effort visualization/profile side effects in API tests."""

    with ExitStack() as stack:
        stack.enter_context(patch.object(app_main, "add_message", return_value=None))
        stack.enter_context(patch.object(app_main, "get_history", return_value=[]))
        stack.enter_context(
            patch.object(app_main, "_publish_web_restaurant_event", return_value=None)
        )
        stack.enter_context(
            patch.object(
                app_main, "_try_publish_visualization_event", return_value=None
            )
        )
        stack.enter_context(
            patch.object(app_main, "_publish_web_completion_flow", return_value=None)
        )
        stack.enter_context(
            patch.object(app_main.staff_service, "ensure_staff_agents", return_value={})
        )
        stack.enter_context(
            patch.object(
                app_main.staff_service, "orchestrate_staff_node", return_value=None
            )
        )
        stack.enter_context(
            patch.object(
                app_main.staff_service,
                "ensure_web_customer_agent",
                return_value=SimpleNamespace(agent_id=None),
            )
        )
        stack.enter_context(
            patch.object(
                app_main.staff_service, "customer_enter_scene", return_value=None
            )
        )
        stack.enter_context(
            patch.object(
                app_main.visitor_analytics_service,
                "record_visit",
                return_value=None,
            )
        )
        stack.enter_context(
            patch.object(
                app_main.visitor_analytics_service,
                "update_visit_intent",
                return_value=None,
            )
        )
        stack.enter_context(
            patch.object(
                app_main.visitor_analytics_service,
                "mark_ordered",
                return_value=None,
            )
        )
        yield


class PendingOrderAtomicityTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_process_local_state()

    def test_claim_pending_order_has_exactly_one_concurrent_winner(self) -> None:
        user_id = f"claim-{uuid.uuid4().hex}"
        payload = {
            "checkout_id": f"checkout-{uuid.uuid4().hex}",
            "coffees": [{"name": "Atomic Espresso", "price": 9.0}],
            "total": 9.0,
        }
        chat_history.set_pending_order(user_id, payload)

        workers = 16
        barrier = threading.Barrier(workers)

        def claim_once():
            barrier.wait(timeout=10)
            return chat_history.claim_pending_order(user_id)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = [
                future.result()
                for future in [pool.submit(claim_once) for _ in range(workers)]
            ]

        winners = [result for result in results if result is not None]
        self.assertEqual(winners, [payload])
        self.assertIsNone(chat_history.get_pending_order(user_id))

    def test_migrate_pending_order_is_once_only_and_never_overwrites_target(
        self,
    ) -> None:
        blocked_source = f"guest-{uuid.uuid4().hex}"
        occupied_target = f"account-{uuid.uuid4().hex}"
        guest_payload = {"checkout_id": "guest-checkout", "coffees": [], "total": 0}
        account_payload = {"checkout_id": "account-checkout", "coffees": [], "total": 0}
        chat_history.set_pending_order(blocked_source, guest_payload)
        chat_history.set_pending_order(occupied_target, account_payload)

        self.assertFalse(
            chat_history.migrate_pending_order(blocked_source, occupied_target)
        )
        self.assertEqual(chat_history.get_pending_order(blocked_source), guest_payload)
        self.assertEqual(
            chat_history.get_pending_order(occupied_target), account_payload
        )

        source = f"guest-{uuid.uuid4().hex}"
        target = f"account-{uuid.uuid4().hex}"
        payload = {"checkout_id": "move-once", "coffees": [], "total": 0}
        chat_history.set_pending_order(source, payload)
        redis_client = _redis_client.get_redis_client(decode_responses=True)
        ttl_before = redis_client.ttl(f"chat:pending:{source}")

        self.assertTrue(chat_history.migrate_pending_order(source, target))
        self.assertFalse(chat_history.migrate_pending_order(source, target))
        self.assertIsNone(chat_history.get_pending_order(source))
        self.assertEqual(chat_history.get_pending_order(target), payload)
        ttl_after = redis_client.ttl(f"chat:pending:{target}")
        self.assertGreater(ttl_after, 0)
        self.assertLessEqual(ttl_after, ttl_before)


class ProductionConfigurationSecurityTests(unittest.TestCase):
    def test_production_rejects_long_documented_placeholder_secret(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            Settings(
                _env_file=None,
                environment="production",
                auth_secret_key="change-me-to-a-random-long-string-in-production",
                auth_cookie_secure=True,
                registration_bonus_cny=0,
            )
        self.assertIn("AUTH_SECRET_KEY", str(raised.exception))

        configured = Settings(
            _env_file=None,
            environment="production",
            auth_secret_key="unit-test-random-secret-0123456789abcdef",
            auth_cookie_secure=True,
            registration_bonus_cny=0,
        )
        self.assertEqual(configured.environment, "production")


class _IsolatedDatabaseCase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_process_local_state()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="coffee-security-tests-")
        db_path = Path(self._temp_dir.name) / "security.sqlite3"
        self.engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
            echo=False,
        )

        @event.listens_for(self.engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        self._missing_override = object()
        self._previous_override = app_main.app.dependency_overrides.get(
            app_main.get_db,
            self._missing_override,
        )

        session_factory = self.Session

        def _get_test_db():
            db = session_factory()
            try:
                yield db
            finally:
                db.close()

        app_main.app.dependency_overrides[app_main.get_db] = _get_test_db
        self.client = TestClient(app_main.app)

    def tearDown(self) -> None:
        self.client.close()
        if self._previous_override is self._missing_override:
            app_main.app.dependency_overrides.pop(app_main.get_db, None)
        else:
            app_main.app.dependency_overrides[app_main.get_db] = self._previous_override
        self.engine.dispose()
        self._temp_dir.cleanup()

    def _seed_account(
        self,
        *,
        role: str = ACCOUNT_ROLE_USER,
        nickname: str | None = None,
    ) -> dict[str, object]:
        unique = uuid.uuid4().hex[:12]
        db = self.Session()
        try:
            user = User(nickname=nickname or f"user-{unique}")
            db.add(user)
            db.flush()
            account = UserAccount(
                username=f"acct-{unique}",
                password_hash="unused-cookie-test-hash",
                nickname=nickname or f"user-{unique}",
                role=role,
                session_version=0,
                user_id=user.user_id,
                status=IDENTITY_STATUS_ACTIVE,
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            return {
                "account_id": int(account.account_id),
                "user_id": int(account.user_id),
                "username": account.username,
                "nickname": account.nickname,
                "token": auth_service.make_session_token(
                    account.account_id,
                    account.session_version,
                ),
            }
        finally:
            db.close()

    def _seed_product(
        self,
        name: str,
        *,
        price: Decimal = Decimal("9.00"),
        stock: int = 1,
    ) -> int:
        db = self.Session()
        try:
            product = Product(
                sku=f"sku-{uuid.uuid4().hex}",
                name=name,
                description=f"test product {name}",
                base_price=price,
                status=PRODUCT_STATUS_AVAILABLE,
                stock=stock,
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            return int(product.product_id)
        finally:
            db.close()

    def _seed_skill_identity(
        self,
        *,
        free_orders_used: int = 0,
        with_user: bool = True,
    ) -> dict[str, object]:
        unique = uuid.uuid4().hex
        token = f"agent-token-{unique}"
        db = self.Session()
        try:
            user_id = None
            if with_user:
                user = User(nickname=f"skill-user-{unique[:8]}")
                db.add(user)
                db.flush()
                user_id = int(user.user_id)
            consumer = EvomapConsumer(
                evomap_node_id=f"node-{unique}",
                display_name=f"consumer-{unique[:8]}",
                local_user_id=user_id,
                free_orders_used=free_orders_used,
                status=IDENTITY_STATUS_ACTIVE,
            )
            db.add(consumer)
            db.flush()
            agent = AgentProfile(
                consumer_id=consumer.consumer_id,
                tool_name=f"tool-{unique[:12]}",
                display_name=f"agent-{unique[:8]}",
                role_type="customer",
                api_token_hash=hash_agent_token(token),
                status=IDENTITY_STATUS_ACTIVE,
            )
            db.add(agent)
            db.commit()
            db.refresh(consumer)
            db.refresh(agent)
            return {
                "user_id": user_id,
                "consumer_id": int(consumer.consumer_id),
                "agent_id": int(agent.agent_id),
                "token": token,
            }
        finally:
            db.close()

    def _new_client_with_token(self, token: str) -> TestClient:
        client = TestClient(app_main.app)
        client.cookies.set(settings.auth_cookie_name, token)
        return client


class ApiSecurityContractTests(_IsolatedDatabaseCase):
    def test_anonymous_checkout_requires_login_then_registration_migrates_and_confirms(
        self,
    ) -> None:
        product_name = f"Security Espresso {uuid.uuid4().hex[:6]}"
        self._seed_product(product_name, price=Decimal("12.00"), stock=2)

        with _quiet_chat_runtime():
            prepared = self.client.post(
                "/chat",
                json={
                    "user_id": 987654321,
                    "message": f"I want {product_name}",
                    "request_id": "guest-prepare",
                },
            )
            self.assertEqual(prepared.status_code, 200, prepared.text)
            checkout_id = prepared.json().get("checkout_id")
            self.assertTrue(checkout_id)

            guest_cookie_name = f"{settings.auth_cookie_name}_guest"
            guest_token = self.client.cookies.get(guest_cookie_name)
            self.assertIsNotNone(guest_token)
            guest_id = auth_service.read_guest_token(guest_token)
            self.assertIsNotNone(guest_id)
            guest_user_id = app_main._guest_numeric_id(guest_id)
            self.assertEqual(
                chat_history.get_pending_order(guest_user_id)["checkout_id"],
                checkout_id,
            )

            guest_confirm = self.client.post(
                "/chat",
                json={"message": "确认", "request_id": "guest-confirm"},
            )
            self.assertEqual(guest_confirm.status_code, 200, guest_confirm.text)
            self.assertEqual(guest_confirm.json().get("code"), "login_required")
            self.assertTrue(guest_confirm.json().get("requires_login"))
            self.assertEqual(
                chat_history.get_pending_order(guest_user_id)["checkout_id"],
                checkout_id,
            )

            username = f"guest{uuid.uuid4().hex[:10]}"
            registered = self.client.post(
                "/auth/register",
                json={
                    "username": username,
                    "password": "safe-password-123",
                    "nickname": "Migrated Guest",
                },
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            account_user_id = int(registered.json()["user_id"])

            confirmed = self.client.post(
                "/chat",
                json={"message": "确认", "request_id": "account-confirm"},
            )
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            self.assertIsNotNone(confirmed.json().get("order_id"))

        db = self.Session()
        try:
            orders = db.query(Order).all()
            self.assertEqual(len(orders), 1)
            self.assertEqual(int(orders[0].user_id), account_user_id)
            self.assertEqual(orders[0].coffee_name, product_name)
            self.assertEqual(db.query(OrderItem).count(), 1)
        finally:
            db.close()
        self.assertIsNone(chat_history.get_pending_order(guest_user_id))
        self.assertIsNone(chat_history.get_pending_order(account_user_id))

    def test_user_resources_are_bound_to_self_or_admin(self) -> None:
        first = self._seed_account(nickname="First")
        second = self._seed_account(nickname="Second")
        admin = self._seed_account(role=ACCOUNT_ROLE_ADMIN, nickname="Admin")
        paths = (
            f"/user/{second['user_id']}",
            f"/history/{second['user_id']}",
            f"/orders/{second['user_id']}",
        )

        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401, (path, response.text))

        first_client = self._new_client_with_token(str(first["token"]))
        try:
            for path in paths:
                response = first_client.get(path)
                self.assertEqual(response.status_code, 403, (path, response.text))
            for path in (
                f"/user/{first['user_id']}",
                f"/history/{first['user_id']}",
                f"/orders/{first['user_id']}",
            ):
                response = first_client.get(path)
                self.assertEqual(response.status_code, 200, (path, response.text))
        finally:
            first_client.close()

        admin_client = self._new_client_with_token(str(admin["token"]))
        try:
            for path in paths:
                response = admin_client.get(path)
                self.assertEqual(response.status_code, 200, (path, response.text))
        finally:
            admin_client.close()

    def test_all_admin_routes_require_admin_role(self) -> None:
        admin_get_paths = (
            "/visualization/events",
            "/admin/autonomous-agent/status",
            "/admin/restaurant-state",
            "/admin/agent-collaboration",
            "/admin/evomap/status",
            "/admin/visitor-analytics",
            "/admin/churn-analysis",
            "/admin/online-visitors",
            "/admin/visitor-chat",
            "/admin/today-topics",
        )
        for path in admin_get_paths:
            with self.subTest(authentication="anonymous", path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401, (path, response.text))
        reconcile = self.client.post(
            "/admin/skill-orders/reconcile",
            json={"ledger_id": 1},
        )
        self.assertEqual(reconcile.status_code, 401, reconcile.text)

        regular = self._seed_account(role=ACCOUNT_ROLE_USER)
        regular_client = self._new_client_with_token(str(regular["token"]))
        try:
            for path in (
                "/admin/restaurant-state",
                "/admin/online-visitors",
                "/admin/visitor-chat",
                "/admin/today-topics",
            ):
                with self.subTest(authentication="regular", path=path):
                    response = regular_client.get(path)
                    self.assertEqual(response.status_code, 403, (path, response.text))
            response = regular_client.post(
                "/admin/skill-orders/reconcile",
                json={"ledger_id": 1},
            )
            self.assertEqual(response.status_code, 403, response.text)
        finally:
            regular_client.close()

        admin = self._seed_account(role=ACCOUNT_ROLE_ADMIN)
        admin_client = self._new_client_with_token(str(admin["token"]))
        try:
            response = admin_client.get("/admin/restaurant-state")
            self.assertEqual(response.status_code, 200, response.text)
        finally:
            admin_client.close()

    def test_admin_can_list_agents_without_server_error(self) -> None:
        identity = self._seed_skill_identity()
        admin = self._seed_account(role=ACCOUNT_ROLE_ADMIN)
        admin_client = self._new_client_with_token(str(admin["token"]))
        try:
            response = admin_client.get("/agents")
        finally:
            admin_client.close()
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertIsInstance(rows, list)
        self.assertIn(identity["agent_id"], {row["agent_id"] for row in rows})

    def test_agent_heartbeat_and_action_rate_limits_use_verified_identity(self) -> None:
        identity = self._seed_skill_identity()
        headers = {"x-agent-token": str(identity["token"])}
        with (
            patch.object(app_main, "enforce_rate_limit") as limiter,
            patch.object(
                app_main,
                "_publish_visualization_event",
                side_effect=[{"event_id": 11}, {"event_id": 12}],
            ),
        ):
            heartbeat = self.client.post(
                f"/agents/{identity['agent_id']}/heartbeat",
                headers=headers,
            )
            action = self.client.post(
                f"/agents/{identity['agent_id']}/actions",
                headers=headers,
                json={"action_type": "walk_to_counter"},
            )
            rejected = self.client.post(
                f"/agents/{identity['agent_id']}/heartbeat",
                headers={"x-agent-token": "wrong-token"},
            )

        self.assertEqual(heartbeat.status_code, 200, heartbeat.text)
        self.assertEqual(action.status_code, 200, action.text)
        self.assertEqual(rejected.status_code, 401, rejected.text)
        self.assertEqual(limiter.call_count, 2)
        self.assertEqual(limiter.call_args_list[0].kwargs["scope"], "agent-heartbeat")
        self.assertEqual(limiter.call_args_list[0].kwargs["limit"], 120)
        self.assertEqual(
            limiter.call_args_list[0].kwargs["identity"],
            f"agent:{identity['agent_id']}",
        )
        self.assertEqual(limiter.call_args_list[1].kwargs["scope"], "agent-action")
        self.assertEqual(limiter.call_args_list[1].kwargs["limit"], 60)
        self.assertEqual(
            limiter.call_args_list[1].kwargs["identity"],
            f"agent:{identity['agent_id']}",
        )

    def test_public_visitor_aliases_are_anonymous_and_redacted(self) -> None:
        stable_user_id = 424242
        app_main._register_online_visitor(
            agent_id=77,
            display_name="Visible Visitor",
            user_id=stable_user_id,
        )
        app_main._add_visitor_chat(
            {
                "message_id": "public-redaction-test",
                "client_message_id": None,
                "user_id": stable_user_id,
                "display_name": "Visible Visitor",
                "message": "redacted replay",
                "created_at": "2026-07-12T00:00:00+00:00",
            }
        )

        online = self.client.get("/api/online-visitors")
        history = self.client.get("/api/visitor-chat/history")
        topics = self.client.get("/api/today-topics")
        self.assertEqual(online.status_code, 200, online.text)
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(topics.status_code, 200, topics.text)
        self.assertEqual(online.json()["visitors"][0]["user_id"], None)
        self.assertEqual(history.json()["messages"][0]["user_id"], None)
        self.assertNotIn("user_id", topics.json())

    def test_service_catalog_get_is_read_only(self) -> None:
        self._seed_product(
            f"Coffee {uuid.uuid4().hex[:8]}",
            price=Decimal("8.00"),
            stock=3,
        )
        db = self.Session()
        try:
            before = db.query(Product).count()
        finally:
            db.close()

        services = self.client.get("/api/services")
        self.assertEqual(services.status_code, 200, services.text)
        self.assertGreater(services.json()["total"], 0)
        metrics = self.client.get("/api/economy/metrics")
        self.assertEqual(metrics.status_code, 200, metrics.text)

        db = self.Session()
        try:
            after = db.query(Product).count()
        finally:
            db.close()
        self.assertEqual(after, before)

    def test_skill_registration_fails_closed_without_persisting_identity(self) -> None:
        payload = {
            "tool_name": "codex-security-test",
            "display_name": "Security Test Agent",
            "evomap_node_id": f"node-{uuid.uuid4().hex}",
            "role_type": "customer",
            # A body field must never substitute for the protected header.
            "evomap_node_secret": "body-secret-is-ignored",
        }

        with patch.object(
            evomap_evolution_service,
            "verify_node_identity",
        ) as verify:
            missing = self.client.post("/skill/register", json=payload)
        self.assertEqual(missing.status_code, 401, missing.text)
        self.assertEqual(missing.json()["detail"]["code"], "missing_evomap_node_secret")
        verify.assert_not_called()

        with patch.object(
            evomap_evolution_service,
            "verify_node_identity",
            return_value=False,
        ):
            invalid = self.client.post(
                "/skill/register",
                json=payload,
                headers={"x-evomap-node-secret": "invalid-test-secret"},
            )
        self.assertEqual(invalid.status_code, 401, invalid.text)
        self.assertEqual(
            invalid.json()["detail"]["code"], "invalid_evomap_node_identity"
        )

        with patch.object(evomap_evolution_service, "_post_json", return_value=None):
            self.assertFalse(
                evomap_evolution_service.verify_node_identity(
                    str(payload["evomap_node_id"]),
                    "unavailable-upstream",
                )
            )
        with patch.object(
            evomap_evolution_service,
            "_post_json",
            return_value={"node_id": "a-different-node"},
        ):
            self.assertFalse(
                evomap_evolution_service.verify_node_identity(
                    str(payload["evomap_node_id"]),
                    "mismatched-identity",
                )
            )

        db = self.Session()
        try:
            self.assertEqual(db.query(EvomapConsumer).count(), 0)
            self.assertEqual(db.query(AgentProfile).count(), 0)
        finally:
            db.close()

    def test_skill_agent_cannot_order_for_another_consumer(self) -> None:
        first = self._seed_skill_identity()
        second = self._seed_skill_identity()
        with patch.object(skill_order_service, "process_skill_order") as process:
            response = self.client.post(
                "/skill/orders",
                headers={"x-agent-token": str(first["token"])},
                json={
                    "consumer_id": second["consumer_id"],
                    "agent_id": first["agent_id"],
                    "message": "one espresso",
                    "request_id": f"binding-{uuid.uuid4().hex}",
                    "auto_confirm": True,
                },
            )
        self.assertEqual(response.status_code, 403, response.text)
        process.assert_not_called()
        db = self.Session()
        try:
            self.assertEqual(db.query(SkillOrderLedger).count(), 0)
            self.assertEqual(db.query(Order).count(), 0)
        finally:
            db.close()

    def test_visitor_identity_ignores_spoofed_user_and_display_name(self) -> None:
        spoofed_user_id = 123456789
        with patch.object(
            app_main, "broadcast_visualization_message", return_value=None
        ):
            first = self.client.post(
                "/api/visitor-chat",
                json={
                    "user_id": spoofed_user_id,
                    "display_name": "Forged Admin",
                    "message": "hello",
                    "client_message_id": "visitor-one",
                },
            )
            second = self.client.post(
                "/api/visitor-chat",
                json={
                    "user_id": spoofed_user_id + 1,
                    "display_name": "Another Forgery",
                    "message": "still me",
                    "client_message_id": "visitor-two",
                },
            )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        first_message = first.json()["message"]
        second_message = second.json()["message"]
        self.assertLess(first_message["user_id"], 0)
        self.assertNotEqual(first_message["user_id"], spoofed_user_id)
        self.assertEqual(first_message["user_id"], second_message["user_id"])
        self.assertEqual(first_message["display_name"], second_message["display_name"])
        self.assertTrue(first_message["display_name"].startswith("Guest "))
        self.assertNotIn("Forged", first_message["display_name"])

        account = self._seed_account(nickname="Canonical Visitor")
        authenticated = self._new_client_with_token(str(account["token"]))
        try:
            with patch.object(
                app_main,
                "broadcast_visualization_message",
                return_value=None,
            ):
                response = authenticated.post(
                    "/api/visitor-chat",
                    json={
                        "user_id": -999,
                        "display_name": "Spoofed Name",
                        "message": "authenticated",
                    },
                )
            self.assertEqual(response.status_code, 200, response.text)
            message = response.json()["message"]
            self.assertEqual(message["user_id"], account["user_id"])
            self.assertEqual(message["display_name"], "Canonical Visitor")
        finally:
            authenticated.close()

    def test_layout_write_is_admin_only_and_stale_version_returns_409(self) -> None:
        namespace = f"layout-{uuid.uuid4().hex[:8]}"
        anonymous = self.client.put(
            "/api/office/layout",
            json={"namespace": namespace, "version": 0, "items": [{"id": "one"}]},
        )
        self.assertEqual(anonymous.status_code, 401, anonymous.text)

        regular = self._seed_account()
        regular_client = self._new_client_with_token(str(regular["token"]))
        try:
            forbidden = regular_client.put(
                "/api/office/layout",
                json={"namespace": namespace, "version": 0, "items": [{"id": "one"}]},
            )
            self.assertEqual(forbidden.status_code, 403, forbidden.text)
        finally:
            regular_client.close()

        admin = self._seed_account(role=ACCOUNT_ROLE_ADMIN)
        admin_client = self._new_client_with_token(str(admin["token"]))
        try:
            created = admin_client.put(
                "/api/office/layout",
                json={"namespace": namespace, "version": 0, "items": [{"id": "one"}]},
            )
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.json()["version"], 1)
            blind_overwrite = admin_client.put(
                "/api/office/layout",
                json={"namespace": namespace, "items": [{"id": "blind"}]},
            )
            self.assertEqual(blind_overwrite.status_code, 409, blind_overwrite.text)
            self.assertEqual(
                blind_overwrite.json()["detail"]["code"],
                "layout_version_conflict",
            )
            updated = admin_client.put(
                "/api/office/layout",
                json={"namespace": namespace, "version": 1, "items": [{"id": "two"}]},
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["version"], 2)
            stale = admin_client.put(
                "/api/office/layout",
                json={"namespace": namespace, "version": 1, "items": [{"id": "stale"}]},
            )
            self.assertEqual(stale.status_code, 409, stale.text)
            self.assertEqual(stale.json()["detail"]["code"], "layout_version_conflict")
            invalid_namespace = admin_client.put(
                "/api/office/layout",
                json={"namespace": "../unsafe", "version": 0, "items": []},
            )
            self.assertEqual(invalid_namespace.status_code, 422, invalid_namespace.text)
            too_many_items = admin_client.put(
                "/api/office/layout",
                json={
                    "namespace": f"{namespace}-large",
                    "version": 0,
                    "items": [None] * 2001,
                },
            )
            self.assertEqual(too_many_items.status_code, 422, too_many_items.text)
        finally:
            admin_client.close()

        current = self.client.get(f"/api/office/layout?namespace={namespace}")
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()["version"], 2)
        self.assertEqual(current.json()["items"], [{"id": "two"}])
        db = self.Session()
        try:
            self.assertEqual(db.query(OfficeLayout).count(), 1)
        finally:
            db.close()

    def test_logout_increments_session_version_and_rejects_token_replay(self) -> None:
        account = self._seed_account()
        old_token = str(account["token"])
        client = self._new_client_with_token(old_token)
        try:
            before = client.get("/auth/me")
            self.assertEqual(before.status_code, 200, before.text)
            logout = client.post("/auth/logout", json={})
            self.assertEqual(logout.status_code, 200, logout.text)
        finally:
            client.close()

        db = self.Session()
        try:
            row = db.get(UserAccount, int(account["account_id"]))
            self.assertEqual(row.session_version, 1)
        finally:
            db.close()

        replay = self._new_client_with_token(old_token)
        try:
            response = replay.get("/auth/me")
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(response.json()["detail"]["code"], "login_required")
        finally:
            replay.close()

    def test_request_size_validation_and_rate_limit_statuses(self) -> None:
        declared_too_large = self.client.post(
            "/auth/login",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": "262145",
            },
        )
        self.assertEqual(declared_too_large.status_code, 413, declared_too_large.text)
        self.assertEqual(
            declared_too_large.json()["detail"]["code"],
            "request_too_large",
        )

        actual_too_large = self.client.post(
            "/auth/login",
            content=b"x" * 262_145,
            headers={"content-type": "application/octet-stream"},
        )
        self.assertEqual(actual_too_large.status_code, 413, actual_too_large.text)

        async def consume_body(_scope, receive, send):
            while True:
                message = await receive()
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        chunked_guard = RequestBodyLimitMiddleware(
            consume_body,
            max_body_size=262_144,
        )
        incoming = iter(
            [
                {
                    "type": "http.request",
                    "body": b"x" * 131_072,
                    "more_body": True,
                },
                {
                    "type": "http.request",
                    "body": b"y" * 131_074,
                    "more_body": False,
                },
            ]
        )
        sent = []

        async def receive_chunk():
            return next(incoming)

        async def capture(message):
            sent.append(message)

        asyncio.run(
            chunked_guard(
                {"type": "http", "headers": []},
                receive_chunk,
                capture,
            )
        )
        response_start = next(
            message for message in sent if message["type"] == "http.response.start"
        )
        response_body = next(
            message for message in sent if message["type"] == "http.response.body"
        )
        self.assertEqual(response_start["status"], 413)
        self.assertEqual(
            json.loads(response_body["body"])["detail"]["code"],
            "request_too_large",
        )

        invalid = self.client.post(
            "/auth/register",
            json={"username": "x", "password": "short"},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)

        attempts = [
            self.client.post(
                "/auth/login",
                json={"username": "missing-user", "password": "wrong-password"},
            )
            for _ in range(10)
        ]
        self.assertTrue(all(response.status_code == 401 for response in attempts))
        limited = self.client.post(
            "/auth/login",
            json={"username": "missing-user", "password": "wrong-password"},
        )
        self.assertEqual(limited.status_code, 429, limited.text)
        self.assertEqual(limited.json()["detail"]["code"], "rate_limited")
        self.assertIn("Retry-After", limited.headers)


class DatabaseConcurrencyContractTests(_IsolatedDatabaseCase):
    def test_free_quota_cas_allows_only_configured_number_of_winners(self) -> None:
        identity = self._seed_skill_identity(free_orders_used=0)
        consumer_id = int(identity["consumer_id"])
        workers = 4
        barrier = threading.Barrier(workers)

        def reserve_slot():
            db = self.Session()
            try:
                consumer = db.get(EvomapConsumer, consumer_id)
                barrier.wait(timeout=10)
                sequence = skill_order_service._reserve_free_order_slot(db, consumer)
                if sequence is not None:
                    db.commit()
                return sequence
            finally:
                db.close()

        original_limit = settings.skill_free_order_limit
        settings.skill_free_order_limit = 2
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = [
                    future.result()
                    for future in [pool.submit(reserve_slot) for _ in range(workers)]
                ]
        finally:
            settings.skill_free_order_limit = original_limit

        self.assertEqual(
            sorted(result for result in results if result is not None), [1, 2]
        )
        db = self.Session()
        try:
            consumer = db.get(EvomapConsumer, consumer_id)
            self.assertEqual(consumer.free_orders_used, 2)
        finally:
            db.close()

    def test_payment_attempt_cas_has_one_external_payment_owner(self) -> None:
        identity = self._seed_skill_identity()
        db = self.Session()
        try:
            ledger = SkillOrderLedger(
                consumer_id=identity["consumer_id"],
                agent_id=identity["agent_id"],
                request_id=f"payment-cas-{uuid.uuid4().hex}",
                coffee_items_json=encode_json([{"name": "Paid", "price": 1}]),
                amount_credits=1,
                payment_status=PAYMENT_STATUS_PAYMENT_REQUIRED,
                version=0,
                payment_attempts=0,
            )
            db.add(ledger)
            db.commit()
            db.refresh(ledger)
            ledger_id = int(ledger.ledger_id)
        finally:
            db.close()

        workers = 4
        barrier = threading.Barrier(workers)

        def claim_payment():
            session = self.Session()
            try:
                row = session.get(SkillOrderLedger, ledger_id)
                barrier.wait(timeout=10)
                _current, claimed = skill_order_service._claim_payment_attempt(
                    session, row
                )
                return claimed
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = [
                future.result()
                for future in [pool.submit(claim_payment) for _ in range(workers)]
            ]
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), workers - 1)
        db = self.Session()
        try:
            ledger = db.get(SkillOrderLedger, ledger_id)
            self.assertEqual(ledger.payment_status, PAYMENT_STATUS_PAYMENT_PROCESSING)
            self.assertEqual(ledger.payment_attempts, 1)
            self.assertEqual(ledger.version, 1)
        finally:
            db.close()

    def test_stock_reservation_cas_decrements_inventory_once(self) -> None:
        identity = self._seed_skill_identity()
        product_name = f"Reservation {uuid.uuid4().hex[:8]}"
        product_id = self._seed_product(product_name, stock=1)
        db = self.Session()
        try:
            ledger = SkillOrderLedger(
                consumer_id=identity["consumer_id"],
                agent_id=identity["agent_id"],
                request_id=f"stock-reservation-{uuid.uuid4().hex}",
                coffee_items_json=encode_json([{"name": product_name, "price": 1}]),
                amount_credits=1,
                payment_status=PAYMENT_STATUS_PAYMENT_PROCESSING,
                version=0,
                payment_attempts=1,
            )
            db.add(ledger)
            db.commit()
            db.refresh(ledger)
            ledger_id = int(ledger.ledger_id)
        finally:
            db.close()

        workers = 2
        barrier = threading.Barrier(workers)
        items = [{"name": product_name, "price": Decimal("1.00")}]

        def reserve_stock():
            session = self.Session()
            try:
                row = session.get(SkillOrderLedger, ledger_id)
                barrier.wait(timeout=10)
                try:
                    skill_order_service._reserve_stock_for_ledger(session, row, items)
                    return "ok"
                except skill_order_service.SkillOrderError as exc:
                    return exc.code
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = [
                future.result()
                for future in [pool.submit(reserve_stock) for _ in range(workers)]
            ]
        self.assertIn("ok", results)
        self.assertTrue(
            all(result in {"ok", "stock_reservation_processing"} for result in results)
        )

        db = self.Session()
        try:
            product = db.get(Product, product_id)
            ledger = db.get(SkillOrderLedger, ledger_id)
            self.assertEqual(product.stock, 0)
            self.assertEqual(product.status, PRODUCT_STATUS_SOLD_OUT)
            self.assertEqual(
                ledger.stock_reservation_status, STOCK_RESERVATION_RESERVED
            )
            entries = json.loads(ledger.stock_reservation_json)
            self.assertEqual(
                entries,
                [{"product_id": product_id, "name": product_name, "quantity": 1}],
            )
        finally:
            db.close()

    def test_atomic_stock_decrement_prevents_oversell(self) -> None:
        product_id = self._seed_product(f"Last Cup {uuid.uuid4().hex[:8]}", stock=1)
        workers = 2
        barrier = threading.Barrier(workers)

        def buy_last_item():
            db = self.Session()
            try:
                barrier.wait(timeout=10)
                try:
                    catalog_service.decrement_stock(db, product_id, 1)
                    db.commit()
                    return "ok"
                except catalog_service.OutOfStockError:
                    db.rollback()
                    return "out_of_stock"
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = [
                future.result()
                for future in [pool.submit(buy_last_item) for _ in range(workers)]
            ]
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("out_of_stock"), 1)
        db = self.Session()
        try:
            product = db.get(Product, product_id)
            self.assertEqual(product.stock, 0)
            self.assertEqual(product.status, PRODUCT_STATUS_SOLD_OUT)
        finally:
            db.close()

    def test_atomic_wallet_debit_prevents_negative_balance(self) -> None:
        identity = self._seed_skill_identity()
        user_id = int(identity["user_id"])
        db = self.Session()
        try:
            db.add(
                UserWallet(
                    user_id=user_id,
                    currency=WALLET_CURRENCY_CNY,
                    balance=Decimal("10.0000"),
                )
            )
            db.commit()
        finally:
            db.close()

        workers = 2
        barrier = threading.Barrier(workers)

        def debit():
            session = self.Session()
            try:
                barrier.wait(timeout=10)
                try:
                    wallet_service.apply_transaction(
                        session,
                        user_id=user_id,
                        currency=WALLET_CURRENCY_CNY,
                        type_="consume",
                        amount=Decimal("-7.0000"),
                        correlation_id=f"wallet-{uuid.uuid4().hex}",
                    )
                    session.commit()
                    return "ok"
                except wallet_service.InsufficientBalanceError:
                    session.rollback()
                    return "insufficient"
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = [
                future.result()
                for future in [pool.submit(debit) for _ in range(workers)]
            ]
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("insufficient"), 1)

        db = self.Session()
        try:
            wallet = db.get(UserWallet, (user_id, WALLET_CURRENCY_CNY))
            transactions = (
                db.query(BalanceTransaction)
                .filter(BalanceTransaction.user_id == user_id)
                .all()
            )
            self.assertEqual(Decimal(wallet.balance), Decimal("3.0000"))
            self.assertEqual(len(transactions), 1)
            self.assertEqual(Decimal(transactions[0].amount), Decimal("-7.0000"))
            self.assertEqual(Decimal(transactions[0].balance_after), Decimal("3.0000"))
        finally:
            db.close()

    def test_reconcile_is_idempotent_and_multi_item_payment_writes_one_credit_ledger(
        self,
    ) -> None:
        identity = self._seed_skill_identity()
        first_name = f"Reconcile A {uuid.uuid4().hex[:6]}"
        second_name = f"Reconcile B {uuid.uuid4().hex[:6]}"
        first_product_id = self._seed_product(
            first_name, price=Decimal("1.25"), stock=1
        )
        second_product_id = self._seed_product(
            second_name, price=Decimal("1.75"), stock=1
        )
        db = self.Session()
        try:
            ledger = SkillOrderLedger(
                consumer_id=identity["consumer_id"],
                agent_id=identity["agent_id"],
                request_id=f"reconcile-{uuid.uuid4().hex}",
                coffee_items_json=encode_json(
                    [
                        {"name": first_name, "price": 1.25},
                        {"name": second_name, "price": 1.75},
                    ]
                ),
                amount_credits=3,
                payment_status=PAYMENT_STATUS_NEEDS_RECONCILE,
                payment_proof_json=encode_json(
                    {"evomap_order_id": f"proof-{uuid.uuid4().hex}"}
                ),
                version=0,
                payment_attempts=1,
            )
            db.add(ledger)
            db.commit()
            db.refresh(ledger)
            ledger_id = int(ledger.ledger_id)
        finally:
            db.close()

        with (
            patch.object(
                skill_order_service, "_publish_skill_completion_flow", return_value=None
            ),
            patch.object(
                skill_order_service,
                "try_publish_visualization_event",
                return_value=None,
            ),
            patch.object(user_profile_service, "summarize_async", return_value=None),
            patch.object(
                skill_order_service, "place_service_order"
            ) as external_payment,
        ):
            first_session = self.Session()
            try:
                first_result = skill_order_service.reconcile_skill_ledger(
                    first_session,
                    ledger_id,
                )
            finally:
                first_session.close()
            second_session = self.Session()
            try:
                second_result = skill_order_service.reconcile_skill_ledger(
                    second_session,
                    ledger_id,
                )
            finally:
                second_session.close()
        external_payment.assert_not_called()
        self.assertEqual(first_result["order_ids"], second_result["order_ids"])
        self.assertEqual(len(first_result["order_ids"]), 2)

        db = self.Session()
        try:
            ledger = db.get(SkillOrderLedger, ledger_id)
            orders = db.query(Order).filter(Order.ledger_id == ledger_id).all()
            items = (
                db.query(OrderItem)
                .join(Order, Order.order_id == OrderItem.order_id)
                .filter(Order.ledger_id == ledger_id)
                .all()
            )
            transactions = (
                db.query(BalanceTransaction)
                .filter(BalanceTransaction.ledger_id == ledger_id)
                .all()
            )
            self.assertEqual(ledger.payment_status, PAYMENT_STATUS_PAID)
            self.assertEqual(
                ledger.stock_reservation_status,
                STOCK_RESERVATION_CONSUMED,
            )
            self.assertEqual(len(orders), 2)
            self.assertEqual(len(items), 2)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(transactions[0].currency, WALLET_CURRENCY_CREDITS)
            self.assertEqual(transactions[0].type, "consume")
            self.assertEqual(Decimal(transactions[0].amount), Decimal("-3.0000"))
            first_product = db.get(Product, first_product_id)
            second_product = db.get(Product, second_product_id)
            self.assertEqual((first_product.stock, second_product.stock), (0, 0))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
