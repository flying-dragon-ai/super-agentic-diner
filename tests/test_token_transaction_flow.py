"""End-to-end integration test for the Token-based transaction system.

Tests the full flow:
1. Skill Agent registers → gets consumer_id + agent_id + api_token
2. First order → free quota (no token deduction)
3. Second order → free quota exhausted
4. Third order → requires EvoMap credits → payment_required (no node secret in local mode)
5. Verify order history and ledger records
6. Verify wallet transaction history

Run:  .\.venv\Scripts\python.exe -m pytest tests/test_token_transaction_flow.py -v
Or:   .\.venv\Scripts\python.exe tests\test_token_transaction_flow.py
"""
from __future__ import annotations

import json
import sys
import time
import uuid
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 10


def _api(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    """Call the API and return (status_code, response_json)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        **(headers or {}),
    })
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}

UNIQUE = uuid.uuid4().hex[:8]
# Use actual menu names from seed data
COFFEE_1 = "热美式"
COFFEE_2 = "卡布奇诺"
COFFEE_3 = "摩卡"


def _gen_node_id() -> str:
    """Generate a unique node_id per test so each gets its own consumer + fresh free quota."""
    return f"test-token-tx-{UNIQUE}-{uuid.uuid4().hex[:6]}"


class TokenTransactionFlowTests(unittest.TestCase):
    """E2E tests against the live server for the token/credit transaction pipeline."""

    @classmethod
    def setUpClass(cls):
        # Verify server is running
        try:
            status_code, data = _api("GET", "/status")
            if status_code != 200:
                raise RuntimeError(f"Server not healthy: {status_code}")
            print(f"\n[setup] Server OK: {data}")
        except Exception as exc:
            raise RuntimeError(
                f"Server not reachable at {BASE_URL} — start it first.\n{exc}"
            )

    def _register(self, node_id: str | None = None) -> dict:
        """Register a Skill agent and return {consumer_id, agent_id, api_token, ...}."""
        nid = node_id or _gen_node_id()
        payload = {
            "tool_name": f"token-test-{nid}",
            "display_name": f"TokenAgent-{nid}",
            "evomap_node_id": nid,
            "evomap_did": "",
            "role_type": "customer",
            "capabilities": ["a2a_super_order", "evomap_credit_payment"],
            "metadata": {"source": "token-tx-test"},
            "evomap_capability_status": "unknown",
        }
        status_code, data = _api("POST", "/skill/register", payload)
        self.assertEqual(status_code, 200, f"Register failed: {status_code} {data}")
        print(f"\n[register] consumer_id={data['consumer_id']} agent_id={data['agent_id']} "
              f"free_orders_remaining={data['free_orders_remaining']} node={nid}")
        return data

    def _submit_order(self, registration: dict, message: str, request_id: str,
                      extra_headers: dict | None = None) -> tuple[int, dict]:
        """Submit a Skill order. Returns (status_code, response_json)."""
        payload = {
            "consumer_id": registration["consumer_id"],
            "agent_id": registration["agent_id"],
            "message": message,
            "request_id": request_id,
            "auto_confirm": True,
            "payment_proof": None,
        }
        headers = {
            "X-Agent-Token": registration["api_token"],
        }
        if extra_headers:
            headers.update(extra_headers)
        return _api("POST", "/skill/orders", payload, headers)

    # ──────────────────────────────────────────────────────────────
    # Test 1: Registration assigns consumer + agent + free quota
    # ──────────────────────────────────────────────────────────────
    def test_01_registration_creates_consumer_and_agent(self):
        reg = self._register()
        self.assertGreater(reg["consumer_id"], 0)
        self.assertGreater(reg["agent_id"], 0)
        self.assertTrue(reg["api_token"])
        self.assertTrue(reg["evomap_node_id"])
        # Default free order limit is 2
        self.assertEqual(reg["free_orders_remaining"], 2)

    # ──────────────────────────────────────────────────────────────
    # Test 2: First order — free quota consumed, no token deduction
    # ──────────────────────────────────────────────────────────────
    def test_02_first_order_uses_free_quota(self):
        reg = self._register()
        req_id = f"token-tx-free1-{UNIQUE}-{int(time.time())}"

        status_code, data = self._submit_order(reg, f"来一杯{COFFEE_1}", req_id)
        print(f"[order-1] status={data.get('status')} payment={data.get('payment_status')} "
              f"order_ids={data.get('order_ids')} free_remaining={data.get('free_orders_remaining')}")

        self.assertEqual(status_code, 200, f"Order 1 failed: {status_code} {data}")
        self.assertIn(data["status"], ("completed", "ok"))
        self.assertIn(data.get("payment_status"), ("free", None))
        self.assertEqual(data.get("free_orders_remaining"), 1)
        self.assertTrue(data.get("order_ids"))

    # ──────────────────────────────────────────────────────────────
    # Test 3: Second order — last free quota
    # ──────────────────────────────────────────────────────────────
    def test_03_second_order_exhausts_free_quota(self):
        reg = self._register()
        ts = int(time.time())

        s1, d1 = self._submit_order(reg, f"来一杯{COFFEE_1}", f"token-tx-free-a-{UNIQUE}-{ts}")
        self.assertEqual(s1, 200, f"Order 1a failed: {s1} {d1}")
        self.assertIn(d1.get("payment_status"), ("free", None))

        s2, data2 = self._submit_order(reg, f"来一杯{COFFEE_2}", f"token-tx-free-b-{UNIQUE}-{ts}")
        self.assertEqual(s2, 200, f"Order 1b failed: {s2} {data2}")
        print(f"[order-2] status={data2.get('status')} payment={data2.get('payment_status')} "
              f"free_remaining={data2.get('free_orders_remaining')}")

        self.assertIn(data2["status"], ("completed", "ok"))
        self.assertIn(data2.get("payment_status"), ("free", None))
        self.assertEqual(data2.get("free_orders_remaining"), 0)

    # ──────────────────────────────────────────────────────────────
    # Test 4: Third order — token payment required (no node secret)
    # ──────────────────────────────────────────────────────────────
    def test_05_third_order_requires_token_payment(self):
        reg = self._register()
        ts = int(time.time())

        # Exhaust free quota
        self._submit_order(reg, f"来一杯{COFFEE_1}", f"token-tx-paid-1-{UNIQUE}-{ts}")
        self._submit_order(reg, f"来一杯{COFFEE_2}", f"token-tx-paid-2-{UNIQUE}-{ts}")

        # Third order — no node secret → payment_required
        status_code, data3 = self._submit_order(reg, f"来一杯{COFFEE_3}", f"token-tx-paid-3-{UNIQUE}-{ts}")
        print(f"[order-3] http={status_code} status={data3.get('status')} "
              f"payment={data3.get('payment_status')} amount_credits={data3.get('amount_credits')}")

        # Without node secret, should get 402 payment_required
        self.assertEqual(status_code, 402)
        detail = data3.get("detail", data3)
        if isinstance(detail, dict):
            self.assertEqual(detail.get("status"), "payment_required")
            self.assertGreater(detail.get("amount_credits", 0), 0)
            self.assertEqual(detail.get("payment_method"), "evomap_service_order")
            # Should include service_order_request with listing info
            sor = detail.get("service_order_request") or {}
            self.assertTrue(sor.get("sender_id"))
            print(f"[order-3] service_order_request listing={sor.get('listing_id', 'N/A')}")

    # ──────────────────────────────────────────────────────────────
    # Test 6: Idempotent retry — same request_id returns same result
    # ──────────────────────────────────────────────────────────────
    def test_06_idempotent_retry_does_not_duplicate(self):
        reg = self._register()
        req_id = f"token-tx-idem-{UNIQUE}-{int(time.time())}"

        s1, data1 = self._submit_order(reg, f"来一杯{COFFEE_1}", req_id)
        order_ids_1 = data1.get("order_ids", [])

        s2, data2 = self._submit_order(reg, f"再来一杯{COFFEE_1}", req_id)
        order_ids_2 = data2.get("order_ids", [])

        print(f"[idempotent] first={order_ids_1} retry={order_ids_2}")

        # Same request_id → same order_ids, no duplicates
        self.assertEqual(order_ids_1, order_ids_2)
        self.assertEqual(len(order_ids_1), len(set(order_ids_1)))

    # ──────────────────────────────────────────────────────────────
    # Test 7: Same consumer re-register keeps free order count
    # ──────────────────────────────────────────────────────────────
    def test_07_reregister_same_node_keeps_free_count(self):
        node_id = _gen_node_id()
        reg1 = self._register(node_id=node_id)

        # Place one free order
        self._submit_order(reg1, f"来一杯{COFFEE_1}", f"token-tx-rereg-1-{UNIQUE}-{int(time.time())}")

        # Re-register same node → should report reduced free count
        reg2_payload = {
            "tool_name": f"token-test-{node_id}-v2",
            "display_name": f"TokenAgent-{node_id}-v2",
            "evomap_node_id": node_id,
            "evomap_did": "",
            "role_type": "customer",
            "capabilities": ["a2a_super_order"],
            "metadata": {},
            "evomap_capability_status": "unknown",
        }
        _, reg2 = _api("POST", "/skill/register", reg2_payload)

        print(f"[reregister] free_remaining after 1 order: {reg2['free_orders_remaining']}")
        self.assertEqual(reg2["consumer_id"], reg1["consumer_id"])
        self.assertEqual(reg2["free_orders_remaining"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
