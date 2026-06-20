from __future__ import annotations

"""登录网页用户经 WS 连接后必须在 scene.snapshot 显示为在线顾客；匿名访客不显示。

覆盖 main.py 的 WS 在线探测链路：
读 Cookie → ensure_web_customer_agent → register_ws_presence → _build_snapshot_agents
（网页在线 = WS presence；Skill/CLI 在线 = agent.last_seen_at 心跳窗口）。
也覆盖 ensure_web_customer_agent 的重复行收敛（并发 WS 连接的 race 防护）。
"""

import unittest
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.auth import service as auth_service
from app.db.database import SessionLocal
from app.db.models import AgentProfile
from app.main import app, visualization_hub
from app.services.staff_service import ensure_web_customer_agent


class WebPresenceSnapshotTests(unittest.TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:10]
        self.username = "presence_" + uid
        self.password = "pass1234"
        self.nickname = "online_" + uid  # unique per run → isolation without full cleanup
        db = SessionLocal()
        try:
            account = auth_service.register_account(
                db, self.username, self.password, self.nickname
            )
            self.user_id = account.user_id
        finally:
            db.close()

    def tearDown(self):
        # Only the agent_profile row is visible in snapshots; removing it keeps the
        # scene clean across runs. user/user_account/wallet rows stay (unique names,
        # FK-bound) — harmless.
        db = SessionLocal()
        try:
            db.query(AgentProfile).filter(
                AgentProfile.tool_name == f"web:customer:{self.user_id}"
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def test_logged_in_web_user_appears_in_snapshot_with_presence(self):
        client = TestClient(app)
        login = client.post(
            "/auth/login", json={"username": self.username, "password": self.password}
        )
        self.assertEqual(login.status_code, 200)
        with client.websocket_connect("/ws/visualization") as ws:
            snapshot = ws.receive_json()
            self.assertEqual(snapshot["type"], "scene.snapshot")
            agents = snapshot["payload"]["agents"]
            # 4 fixed staff always on duty.
            roles = {a["role_type"] for a in agents}
            self.assertTrue({"barista", "cashier", "waiter", "manager"} <= roles)
            # The connecting user shows up under their real login name.
            me = [a for a in agents if a.get("display_name") == self.nickname]
            self.assertTrue(me, "connecting web user missing from own snapshot")
            self.assertEqual(me[0]["role_type"], "customer")
            self.assertIn(me[0]["agent_id"], visualization_hub.online_ws_agent_ids())
            my_agent_id = me[0]["agent_id"]
            ws.close()
        # Presence is cleared once the WS closes.
        self.assertNotIn(my_agent_id, visualization_hub.online_ws_agent_ids())

    def test_anonymous_visitor_not_shown_as_customer(self):
        client = TestClient(app)  # no login → no session cookie
        with client.websocket_connect("/ws/visualization") as ws:
            snapshot = ws.receive_json()
            agents = snapshot["payload"]["agents"]
            matches = [a for a in agents if a.get("display_name") == self.nickname]
            self.assertEqual(matches, [], "anonymous visitor must not appear as a customer")


class WebCustomerDedupTests(unittest.TestCase):
    """Two concurrent WS connects for the same user can race past query-then-create
    and insert duplicate web:customer:{user_id} rows. ensure_web_customer_agent must
    collapse them back to a single (oldest) row so the scene never shows twin avatars.
    """

    def setUp(self):
        self.user_id = 900000 + int(uuid.uuid4().hex[:6], 16) % 99999
        self.tool_name = f"web:customer:{self.user_id}"

    def tearDown(self):
        db = SessionLocal()
        try:
            db.query(AgentProfile).filter(AgentProfile.tool_name == self.tool_name).delete(
                synchronize_session=False
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def test_duplicate_rows_collapsed_to_oldest(self):
        db = SessionLocal()
        try:
            first = ensure_web_customer_agent(db, self.user_id)
            # Simulate a concurrent insert that won the race.
            db.add(
                AgentProfile(
                    tool_name=self.tool_name,
                    display_name="racing-duplicate",
                    role_type="customer",
                    capabilities_json="[]",
                    metadata_json="{}",
                    api_token_hash="x",
                    sprite_seed=1,
                    status="active",
                    created_at=datetime.utcnow(),
                    last_seen_at=datetime.utcnow(),
                )
            )
            db.commit()
            self.assertEqual(
                db.query(AgentProfile).filter(AgentProfile.tool_name == self.tool_name).count(),
                2,
            )
            # Next call must collapse to one, keeping the oldest (first.agent_id).
            again = ensure_web_customer_agent(db, self.user_id)
            self.assertEqual(
                db.query(AgentProfile).filter(AgentProfile.tool_name == self.tool_name).count(),
                1,
            )
            self.assertEqual(again.agent_id, first.agent_id)
        finally:
            db.close()


class SkillOfflineSweepTests(unittest.IsolatedAsyncioTestCase):
    """Skill/CLI customers can't signal departure (their script already exited); the
    background sweep must broadcast leave_scene for any whose heartbeat window just
    expired, so already-connected clients drop the avatar in real time.
    """

    def setUp(self):
        import app.main as main_mod

        self._main = main_mod
        self._saved_prev = set(main_mod._prev_skill_online)
        self.user_id = 950000 + int(uuid.uuid4().hex[:6], 16) % 49999
        self.tool_name = f"web:customer:{self.user_id}"
        db = SessionLocal()
        try:
            self.agent_id = ensure_web_customer_agent(db, self.user_id).agent_id
        finally:
            db.close()

    def tearDown(self):
        db = SessionLocal()
        try:
            db.query(AgentProfile).filter(AgentProfile.tool_name == self.tool_name).delete(
                synchronize_session=False
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        self._main._prev_skill_online = self._saved_prev

    async def test_expired_customer_emits_leave_scene(self):
        from unittest.mock import AsyncMock, patch

        main_mod = self._main
        # Expire the heartbeat (older than the online window) and pretend the agent
        # was online on the previous sweep.
        db = SessionLocal()
        try:
            db.query(AgentProfile).filter(AgentProfile.agent_id == self.agent_id).update(
                {
                    AgentProfile.last_seen_at: datetime.utcnow()
                    - timedelta(seconds=main_mod.ONLINE_WINDOW_SECONDS + 60)
                }
            )
            db.commit()
        finally:
            db.close()
        main_mod._prev_skill_online = {self.agent_id}

        mock_broadcast = AsyncMock()
        with patch.object(main_mod.visualization_hub, "broadcast_transient", mock_broadcast):
            await main_mod._sweep_offline_skill_customers()

        broadcast_ids = [
            call.args[0]["agent_id"]
            for call in mock_broadcast.call_args_list
            if call.args[0].get("type") == "agent.action"
        ]
        self.assertIn(self.agent_id, broadcast_ids, "expired customer must get a leave_scene broadcast")
        self.assertNotIn(self.agent_id, main_mod._prev_skill_online, "sweep must drop expired id from prev set")

    async def test_still_online_customer_not_swept(self):
        from unittest.mock import AsyncMock, patch

        main_mod = self._main
        # Agent is within the window → still online → must NOT be swept.
        db = SessionLocal()
        try:
            db.query(AgentProfile).filter(AgentProfile.agent_id == self.agent_id).update(
                {AgentProfile.last_seen_at: datetime.utcnow()}
            )
            db.commit()
        finally:
            db.close()
        main_mod._prev_skill_online = {self.agent_id}

        mock_broadcast = AsyncMock()
        with patch.object(main_mod.visualization_hub, "broadcast_transient", mock_broadcast):
            await main_mod._sweep_offline_skill_customers()

        broadcast_ids = [call.args[0]["agent_id"] for call in mock_broadcast.call_args_list]
        self.assertNotIn(self.agent_id, broadcast_ids, "still-online customer must not be swept")
        self.assertIn(self.agent_id, main_mod._prev_skill_online, "still-online id stays in prev set")


if __name__ == "__main__":
    unittest.main()
