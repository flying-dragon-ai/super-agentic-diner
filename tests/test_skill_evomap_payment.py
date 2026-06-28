from __future__ import annotations

import json
import unittest
from decimal import Decimal
from urllib.error import HTTPError
from unittest.mock import patch

from app.config import settings
from app.db.models import (
    AgentProfile,
    BalanceTransaction,
    CoffeeKB,
    EvomapConsumer,
    Order,
    OrderItem,
    Product,
    SkillOrderLedger,
    UserWallet,
)
from app.services.skill_order_service import (
    SkillOrderError,
    SkillPaymentRequired,
    process_skill_order,
)


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload

    def close(self):
        return None


class _FakeHTTPError(HTTPError):
    def __init__(self, code: int, payload: dict):
        Exception.__init__(self, f"HTTP Error {code}")
        self.code = code
        self.msg = "Payment Required"
        self.hdrs = None
        self.fp = None
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload


class _FakeQuery:
    def __init__(self, session: "_FakeSession", model):
        self.session = session
        self.model = model

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        if self.model is CoffeeKB:
            return list(self.session.coffees)
        if self.model is Product:
            return list(self.session.products)
        return []

    def first(self):
        if self.model is SkillOrderLedger:
            return self.session.existing_ledger
        if self.model is CoffeeKB:
            return self.session.coffees[0] if self.session.coffees else None
        if self.model is Product:
            return self.session.products[0] if self.session.products else None
        if self.model is Order:
            return None
        if self.model is OrderItem:
            return None
        return None


class _FakeSelectResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value


class _FakeSession:
    def __init__(self):
        self.coffees = [
            CoffeeKB(id=1, coffee_name="榛果拿铁", content="香甜坚果风味", price=Decimal("28.00"))
        ]
        self.products = [
            Product(
                product_id=1,
                sku="HAZELNUT-LATTE",
                name="榛果拿铁",
                description="香甜坚果风味",
                base_price=Decimal("28.00"),
                tags="坚果,拿铁",
                status="available",
                stock=10,
            )
        ]
        self.wallets: dict[tuple[int, str], UserWallet] = {(17, "credits"): UserWallet(user_id=17, currency="credits", balance=Decimal("100"))}
        self.existing_ledger = None
        self.ledgers: list[SkillOrderLedger] = []
        self.orders: list[Order] = []
        self.commits = 0
        self.rollbacks = 0
        self._next_ledger_id = 100
        self._next_order_id = 200
        self.fail_order_add = False

    def query(self, model):
        return _FakeQuery(self, model)

    def execute(self, statement):
        # The new skill path executes SELECT statements for Product (stock),
        # UserWallet, and OrderItem lookups. Resolve against the in-memory state.
        model = getattr(statement, "column_descriptions", None)
        try:
            target = model[0]["entity"] if model else None
        except Exception:
            target = None
        if target is Product:
            return _FakeSelectResult(self.products[0] if self.products else None)
        if target is UserWallet:
            # user_id/currency key lookups: return the matching wallet if present.
            return _FakeSelectResult(None)
        return _FakeSelectResult(None)

    def add(self, obj):
        if isinstance(obj, SkillOrderLedger) and obj not in self.ledgers:
            self.ledgers.append(obj)
        if isinstance(obj, Order) and obj not in self.orders:
            if self.fail_order_add:
                raise RuntimeError("order write failed")
            self.orders.append(obj)

    def flush(self):
        for ledger in self.ledgers:
            if ledger.ledger_id is None:
                ledger.ledger_id = self._next_ledger_id
                self._next_ledger_id += 1
        for order in self.orders:
            if order.order_id is None:
                order.order_id = self._next_order_id
                self._next_order_id += 1

    def commit(self):
        self.commits += 1
        self.flush()

    def refresh(self, _obj):
        self.flush()

    def rollback(self):
        self.rollbacks += 1


class SkillEvoMapPaymentTests(unittest.TestCase):
    def _published_event_types(self, *publish_mocks):
        event_types = []
        for publish_mock in publish_mocks:
            for call in publish_mock.call_args_list:
                if len(call.args) > 1 and isinstance(call.args[1], list):
                    event_types.extend(event["event_type"] for event in call.args[1])
                elif len(call.args) > 1:
                    event_types.append(call.args[1])
        return event_types

    def setUp(self):
        self._settings = {
            "skill_free_order_limit": settings.skill_free_order_limit,
            "evomap_service_listing_id": settings.evomap_service_listing_id,
            "evomap_hub_url": settings.evomap_hub_url,
            "evomap_payment_mode": settings.evomap_payment_mode,
            "evomap_order_credits": settings.evomap_order_credits,
            "evomap_request_timeout_seconds": settings.evomap_request_timeout_seconds,
        }
        settings.skill_free_order_limit = 2
        settings.evomap_service_listing_id = "listing-coffee-001"
        settings.evomap_hub_url = "https://evomap.test"
        settings.evomap_payment_mode = "service_order"
        settings.evomap_order_credits = 3
        settings.evomap_request_timeout_seconds = 1

        self.consumer = EvomapConsumer(
            consumer_id=7,
            evomap_node_id="node-consumer-7",
            display_name="Codex",
            local_user_id=17,
            free_orders_used=2,
            status="active",
        )
        self.agent = AgentProfile(
            agent_id=9,
            tool_name="codex",
            display_name="Codex",
            role_type="customer",
            api_token_hash="hash",
            sprite_seed=1,
            status="active",
        )

        # The new skill-order path writes a credits wallet transaction + order
        # item + stock decrement. Patch the wallet service so the fake session
        # does not have to implement a full SQLAlchemy execute() path.
        self._wallet_patch = patch("app.services.skill_order_service.wallet_service")
        self._wallet_mock = self._wallet_patch.start()
        self._wallet_mock.WALLET_CURRENCY_CREDITS = "credits"
        self._wallet_mock.BalanceTransaction = BalanceTransaction
        self._wallet_mock.apply_transaction.return_value = BalanceTransaction(
            transaction_id=1, user_id=17, currency="credits", type="consume", amount=Decimal("-3")
        )
        # Stock decrement goes through catalog_service.decrement_stock which uses
        # db.execute(select(Product)); patch it to mutate the fake product stock.
        self._stock_patch = patch(
            "app.services.skill_order_service.decrement_stock",
            side_effect=self._fake_decrement_stock,
        )
        self._stock_patch.start()

    def _fake_decrement_stock(self, db, product_id, quantity):
        for product in db.products:
            if product.product_id == product_id:
                product.stock = max(0, (product.stock or 0) - quantity)
                return product
        return None

    def tearDown(self):
        self._stock_patch.stop()
        self._wallet_patch.stop()
        for key, value in self._settings.items():
            setattr(settings, key, value)

    def test_paid_skill_order_posts_mocked_service_order_and_persists_paid_ledger(self):
        db = _FakeSession()
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse({"order_id": "evomap-order-123", "status": "created"})

        def fake_batch_publish(db, events):
            for event in events:
                publish_mock(
                    db,
                    event["event_type"],
                    event.get("payload") or {},
                    agent_id=event.get("agent_id"),
                    correlation_id=event.get("correlation_id"),
                )

        with (
            patch("app.services.skill_order_service.try_publish_visualization_event") as publish_mock,
            patch(
                "app.services.skill_order_service.try_publish_visualization_events",
                side_effect=fake_batch_publish,
            ),
            patch("app.services.evomap_payment_service.urlopen", side_effect=fake_urlopen) as urlopen_mock,
        ):
            result = process_skill_order(
                db,
                consumer=self.consumer,
                agent=self.agent,
                message="来一杯榛果拿铁",
                request_id="req-paid-1",
                evomap_node_secret="secret-used-only-in-mock",
                payment_proof=None,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["payment_status"], "paid")
        self.assertEqual(result["evomap_order_id"], "evomap-order-123")
        self.assertEqual(result["amount_credits"], 3)
        self.assertEqual(len(db.ledgers), 1)
        self.assertEqual(db.ledgers[0].payment_status, "paid")
        self.assertEqual(db.ledgers[0].evomap_order_id, "evomap-order-123")
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(db.orders[0].source_type, "skill")
        self.assertEqual(db.orders[0].payment_status, "paid")
        self.assertEqual(db.orders[0].consumer_id, self.consumer.consumer_id)
        self.assertEqual(db.orders[0].agent_id, self.agent.agent_id)
        self.assertEqual(db.orders[0].ledger_id, db.ledgers[0].ledger_id)

        urlopen_mock.assert_called_once()
        self.assertEqual(captured["timeout"], 1)
        request = captured["request"]
        self.assertEqual(request.full_url, "https://evomap.test/a2a/service/order")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-used-only-in-mock")
        self.assertEqual(
            {key.lower(): value for key, value in request.header_items()}["X-correlation-id".lower()],
            "req-paid-1",
        )
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["sender_id"], "node-consumer-7")
        self.assertEqual(body["listing_id"], "listing-coffee-001")
        self.assertIn("request_id=req-paid-1", body["question"])
        self.assertIn("credits=3", body["question"])
        event_types = self._published_event_types(publish_mock)
        for event_type in (
            "restaurant.customer_entered",
            "restaurant.order_ticketed",
            "restaurant.payment_processing",
            "restaurant.payment_completed",
            "restaurant.preparation_progress",
            "restaurant.order_ready",
            "restaurant.order_delivered",
            "restaurant.customer_reviewed",
            "restaurant.customer_left",
            "order.paid",
        ):
            self.assertIn(event_type, event_types)
        self.assertLess(
            event_types.index("restaurant.payment_completed"),
            event_types.index("restaurant.preparation_progress"),
        )
        self.assertLess(event_types.index("restaurant.customer_left"), event_types.index("order.paid"))

    def test_paid_skill_order_without_secret_returns_payment_required_without_http(self):
        db = _FakeSession()

        with (
            patch("app.services.skill_order_service.try_publish_visualization_event") as publish_mock,
            patch("app.services.evomap_payment_service.urlopen") as urlopen_mock,
        ):
            with self.assertRaises(SkillPaymentRequired) as raised:
                process_skill_order(
                    db,
                    consumer=self.consumer,
                    agent=self.agent,
                    message="来一杯榛果拿铁",
                    request_id="req-payment-required",
                    evomap_node_secret=None,
                    payment_proof=None,
                )

        urlopen_mock.assert_not_called()
        payload = raised.exception.payload
        self.assertEqual(payload["status"], "payment_required")
        self.assertEqual(payload["amount_credits"], 3)
        self.assertIsNone(payload["payment_request"])
        self.assertEqual(payload["payment_method"], "evomap_service_order")
        self.assertEqual(payload["service_order_request"]["sender_id"], "node-consumer-7")
        self.assertEqual(payload["service_order_request"]["listing_id"], "listing-coffee-001")
        self.assertEqual(len(db.ledgers), 1)
        self.assertEqual(db.ledgers[0].payment_status, "payment_required")
        event_types = self._published_event_types(publish_mock)
        self.assertIn("restaurant.customer_entered", event_types)
        self.assertIn("restaurant.order_ticketed", event_types)
        self.assertIn("restaurant.payment_requested", event_types)
        self.assertIn("order.payment_required", event_types)
        self.assertLess(
            event_types.index("restaurant.payment_requested"),
            event_types.index("order.payment_required"),
        )

    def test_evomap_insufficient_credits_marks_ledger_failed_without_real_http(self):
        db = _FakeSession()

        def fake_urlopen(_request, timeout):
            self.assertEqual(timeout, 1)
            raise _FakeHTTPError(402, {"message": "not enough credits"})

        with (
            patch("app.services.skill_order_service.try_publish_visualization_event") as publish_mock,
            patch("app.services.evomap_payment_service.urlopen", side_effect=fake_urlopen),
        ):
            with self.assertRaises(SkillOrderError) as raised:
                process_skill_order(
                    db,
                    consumer=self.consumer,
                    agent=self.agent,
                    message="来一杯榛果拿铁",
                    request_id="req-paid-fail",
                    evomap_node_secret="secret-used-only-in-mock",
                    payment_proof=None,
                )

        self.assertEqual(raised.exception.code, "evomap_insufficient_credits")
        self.assertEqual(raised.exception.http_status, 402)
        self.assertEqual(len(db.ledgers), 1)
        self.assertEqual(db.ledgers[0].payment_status, "payment_failed")
        failure_proof = json.loads(db.ledgers[0].payment_proof_json)
        self.assertEqual(failure_proof["code"], "evomap_insufficient_credits")
        event_types = self._published_event_types(publish_mock)
        self.assertIn("restaurant.payment_processing", event_types)
        self.assertIn("restaurant.payment_failed", event_types)
        self.assertIn("restaurant.order_failed", event_types)
        self.assertIn("order.payment_failed", event_types)

    def test_unverified_payment_proof_is_rejected_without_marking_paid(self):
        db = _FakeSession()
        proof = {
            "evomap_order_id": "forged-order",
            "credits": 3,
            "request_id": "req-forged-proof",
            "consumer_node_id": "node-consumer-7",
            "status": "settled",
        }

        with (
            patch("app.services.skill_order_service.try_publish_visualization_event") as publish_mock,
            patch("app.services.evomap_payment_service.urlopen") as urlopen_mock,
        ):
            with self.assertRaises(SkillPaymentRequired) as raised:
                process_skill_order(
                    db,
                    consumer=self.consumer,
                    agent=self.agent,
                    message="来一杯榛果拿铁",
                    request_id="req-forged-proof",
                    evomap_node_secret=None,
                    payment_proof=proof,
                )

        urlopen_mock.assert_not_called()
        payload = raised.exception.payload
        self.assertEqual(payload["code"], "payment_proof_unverifiable")
        self.assertEqual(payload["status"], "payment_required")
        self.assertIsNone(payload["payment_request"])
        self.assertEqual(len(db.orders), 0)
        self.assertEqual(len(db.ledgers), 1)
        self.assertEqual(db.ledgers[0].payment_status, "payment_required")
        self.assertIsNone(db.ledgers[0].evomap_order_id)
        event_types = self._published_event_types(publish_mock)
        self.assertIn("restaurant.payment_requested", event_types)
        self.assertIn("order.payment_required", event_types)

    def test_paid_request_id_retry_does_not_charge_or_create_duplicate_order(self):
        db = _FakeSession()
        db.existing_ledger = SkillOrderLedger(
            ledger_id=101,
            consumer_id=self.consumer.consumer_id,
            agent_id=self.agent.agent_id,
            request_id="req-paid-existing",
            order_ids_json=json.dumps([200]),
            coffee_items_json=json.dumps([{"name": "榛果拿铁", "price": 28.0}]),
            amount_credits=3,
            payment_status="paid",
            evomap_order_id="evomap-order-123",
        )

        with (
            patch("app.services.skill_order_service.try_publish_visualization_event"),
            patch("app.services.evomap_payment_service.urlopen") as urlopen_mock,
        ):
            result = process_skill_order(
                db,
                consumer=self.consumer,
                agent=self.agent,
                message="来一杯榛果拿铁",
                request_id="req-paid-existing",
                evomap_node_secret="secret-used-only-in-mock",
                payment_proof=None,
            )

        urlopen_mock.assert_not_called()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["payment_status"], "paid")
        self.assertEqual(result["evomap_order_id"], "evomap-order-123")
        self.assertEqual(result["order_ids"], [200])
        self.assertEqual(len(db.orders), 0)

    def test_paid_evomap_success_local_order_failure_marks_needs_reconcile(self):
        db = _FakeSession()
        db.fail_order_add = True

        def fake_urlopen(_request, timeout):
            self.assertEqual(timeout, 1)
            return _FakeResponse({"order_id": "evomap-order-needs-reconcile", "status": "created"})

        with (
            patch("app.services.skill_order_service.try_publish_visualization_event") as publish_mock,
            patch("app.services.evomap_payment_service.urlopen", side_effect=fake_urlopen),
        ):
            with self.assertRaises(SkillOrderError) as raised:
                process_skill_order(
                    db,
                    consumer=self.consumer,
                    agent=self.agent,
                    message="来一杯榛果拿铁",
                    request_id="req-reconcile",
                    evomap_node_secret="secret-used-only-in-mock",
                    payment_proof=None,
                )

        self.assertEqual(raised.exception.code, "local_order_reconcile_required")
        self.assertEqual(raised.exception.http_status, 500)
        self.assertEqual(len(db.ledgers), 1)
        ledger = db.ledgers[0]
        self.assertEqual(ledger.payment_status, "needs_reconcile")
        self.assertEqual(ledger.evomap_order_id, "evomap-order-needs-reconcile")
        proof = json.loads(ledger.payment_proof_json)
        self.assertEqual(proof["evomap_order_id"], "evomap-order-needs-reconcile")
        self.assertEqual(proof["credits"], 3)
        self.assertEqual(len(db.orders), 0)
        self.assertGreaterEqual(db.rollbacks, 1)
        event_types = self._published_event_types(publish_mock)
        self.assertIn("order.failed", event_types)


if __name__ == "__main__":
    unittest.main()
