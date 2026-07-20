"""用户画像功能测试：对话持久化 + 增量总结 + 登录过滤 + LLM 降级 + 锁防重入 + 推荐注入。

覆盖：
  - chat_history.add_message 双写（Redis + SQL）
  - summarize_user_session 增量游标推进
  - 仅登录用户总结（匿名跳过）
  - LLM 无 key 时保留旧画像
  - summarize_async Redis 锁防重入
  - recommender_agent 注入画像
"""
from __future__ import annotations

import _test_env  # noqa: F401 - activate hermetic defaults before app imports
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.memory import chat_history


# ---------------- 共用 fake ----------------


class _FakeRedis:
    def __init__(self):
        self._lists: dict[str, list] = {}
        self._strings: dict[str, object] = {}
        self._setnx_results: dict[str, bool] = {}

    def lpush(self, key, value):
        self._lists.setdefault(key, []).insert(0, value)

    def lrange(self, key, start, end):
        data = self._lists.get(key, [])
        if end == -1:
            return list(data[start:])
        return list(data[start : end + 1])

    def ltrim(self, key, start, end):
        data = self._lists.get(key, [])
        self._lists[key] = list(data[start : end + 1])

    def set(self, key, value, ex=None, nx=None):
        if nx:
            if key in self._strings:
                return None
            self._strings[key] = value
            return True
        self._strings[key] = value
        return True

    def get(self, key):
        return self._strings.get(key)

    def delete(self, key):
        self._strings.pop(key, None)
        self._lists.pop(key, None)
        return 1

    def expire(self, key, ttl):
        return True


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    """简单 fake session：支持 add/commit/query(...).filter/first/all 链式调用。"""

    def __init__(self):
        self.added: list = []
        self._committed = False
        # 由测试按需设置 _rows_map: {ModelClass: [rows]}

    def query(self, model):
        self._current_model = model
        rows = getattr(self, "_rows_map", {}).get(model, [])
        return _FakeQuery(rows)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self._committed = True

    def close(self):
        pass

    def refresh(self, _obj):
        pass


# ---------------- 测试 1：add_message 双写 ----------------


class AddMessageDoubleWriteTests(unittest.TestCase):
    def test_message_persisted_to_sql_when_redis_ok(self):
        """add_message 同时写 Redis 和 SQL（ChatMessage 落库）。"""
        from app.db import models as M

        captured: list[M.ChatMessage] = []

        class _CapturingSession(_FakeSession):
            def add(self, obj):
                captured.append(obj)

        fake_redis = _FakeRedis()

        with (
            patch.object(chat_history, "_client", lambda: fake_redis),
            patch("app.db.database.SessionLocal", lambda: _CapturingSession()),
        ):
            chat_history.add_message(777777, "user", "测试双写")

        # Redis 侧
        self.assertEqual(len(fake_redis._lists["chat:history:777777"]), 1)
        # SQL 侧
        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], M.ChatMessage)
        self.assertEqual(captured[0].user_id, 777777)
        self.assertEqual(captured[0].role, "user")
        self.assertEqual(captured[0].content, "测试双写")

    def test_sql_failure_does_not_raise(self):
        """SQL 写入失败时 swallow，不抛异常（不阻断聊天）。"""
        fake_redis = _FakeRedis()

        class _BoomSession:
            def add(self, _o):
                raise RuntimeError("db down")

            def commit(self):
                pass

            def close(self):
                pass

        with (
            patch.object(chat_history, "_client", lambda: fake_redis),
            patch("app.db.database.SessionLocal", lambda: _BoomSession()),
        ):
            # 不应抛异常
            chat_history.add_message(777778, "assistant", "降级测试")

        # Redis 侧仍成功
        self.assertEqual(len(fake_redis._lists["chat:history:777778"]), 1)


# ---------------- 测试 2：summarize_user_session 行为 ----------------


class SummarizeSessionTests(unittest.TestCase):
    def _msg(self, mid, role, content):
        return SimpleNamespace(message_id=mid, role=role, content=content, user_id=100)

    def test_anonymous_user_skipped(self):
        """匿名用户（无 UserAccount）跳过总结。"""
        from app.db import models as M
        from app.services import user_profile_service as ups

        # UserAccount 查询返回 None
        sess = _FakeSession()
        with patch.object(ups, "_is_logged_in_user", return_value=False):
            result = ups.summarize_user_session(sess, user_id=99999)
        self.assertIsNone(result)

    def test_no_new_messages_skipped(self):
        """无新对话（last_msg_id 之后无新消息）跳过总结。"""
        from app.services import user_profile_service as ups

        sess = _FakeSession()
        with (
            patch.object(ups, "_is_logged_in_user", return_value=True),
            patch.object(ups, "_fetch_new_messages", return_value=[]),
        ):
            result = ups.summarize_user_session(sess, user_id=100)
        self.assertIsNone(result)

    def test_llm_no_key_preserves_old_profile(self):
        """无 LLM key 时返回 None，调用方应保留旧画像。"""
        from app.services import user_profile_service as ups

        sess = _FakeSession()
        new_msgs = [self._msg(5, "user", "我想要苦的")]
        with (
            patch.object(ups, "_is_logged_in_user", return_value=True),
            patch.object(ups, "_fetch_new_messages", return_value=new_msgs),
            patch.object(ups.llm, "has_real_key", return_value=False),
        ):
            result = ups.summarize_user_session(sess, user_id=100)
        self.assertIsNone(result)

    def test_successful_summary_advances_cursor_and_returns_dict(self):
        """成功总结：返回 dict，last_msg_id 游标推进到最后一条新消息 id。"""
        from app.db import models as M
        from app.services import user_profile_service as ups

        new_msgs = [
            self._msg(5, "user", "我喜欢苦的"),
            self._msg(6, "assistant", "推荐美式"),
        ]
        llm_output_dict = {
            "summary": "偏爱纯粹苦味，预算敏感",
            "favorite_tags": ["苦", "纯粹"],
            "avoid_tags": ["甜"],
            "price_tier": "budget",
            "persona": "纯粹苦味党",
        }

        class _UpdatableSession(_FakeSession):
            def __init__(self):
                super().__init__()
                self._rows_map = {}
                self.committed_profile_row = None

            def add(self, obj):
                self.added.append(obj)
                if isinstance(obj, M.UserProfile):
                    self.committed_profile_row = obj

        sess = _UpdatableSession()
        # User 查询返回一个可更新对象
        fake_user = SimpleNamespace(user_id=100, taste_preference=None, updated_at=None)
        sess._rows_map[M.User] = [fake_user]

        with (
            patch.object(ups, "_is_logged_in_user", return_value=True),
            patch.object(ups, "_fetch_new_messages", return_value=new_msgs),
            patch.object(ups, "_fetch_recent_orders", return_value=[]),
            patch.object(ups.llm, "has_real_key", return_value=True),
            patch.object(ups.llm, "chat_with_role", return_value='{"summary":"偏爱纯粹苦味"}'),
            patch.object(
                ups.llm, "parse_json_response", return_value=llm_output_dict
            ),
            patch.object(ups, "_persist_profile") as mock_persist,
        ):
            result = ups.summarize_user_session(sess, user_id=100)

        self.assertEqual(result, llm_output_dict)
        # _persist_profile 被调用，且 last_msg_id = 最后一条消息 id (6)
        args = mock_persist.call_args.args
        self.assertEqual(args[3], llm_output_dict)  # result
        self.assertEqual(args[4], 6)  # new_last_msg_id


# ---------------- 测试 3：summarize_async 锁防重入 ----------------


class SummarizeAsyncLockTests(unittest.TestCase):
    def test_second_trigger_within_lock_window_skipped(self):
        """Redis 锁存在时，第二次触发直接跳过（不重复总结）。"""
        from app.services import user_profile_service as ups

        fake_redis = _FakeRedis()
        # 预置锁：第一次 set(nx) 会返回 None
        fake_redis._strings["profile:lock:200"] = "1"

        triggered: list = []
        with (
            patch.object(ups, "_redis", lambda: fake_redis),
            patch.object(
                ups, "summarize_user_session", side_effect=lambda *a, **k: triggered.append(1)
            ),
        ):
            ups.summarize_async(user_id=200)

        import time

        time.sleep(0.1)  # 等后台线程（不应被启动）
        self.assertEqual(triggered, [])  # 锁存在，未真正调用总结

    def test_lock_acquired_triggers_summary(self):
        """无锁时获取锁并触发后台总结。"""
        from app.services import user_profile_service as ups

        fake_redis = _FakeRedis()
        triggered: list = []

        with (
            patch.object(ups, "_redis", lambda: fake_redis),
            patch.object(
                ups, "summarize_user_session", side_effect=lambda *a, **k: triggered.append(1)
            ),
        ):
            ups.summarize_async(user_id=201)

        import time

        time.sleep(0.2)  # 等后台线程执行
        self.assertEqual(triggered, [1])
        # 锁已设置
        self.assertIn("profile:lock:201", fake_redis._strings)


# ---------------- 测试 4：推荐 Agent 注入画像 ----------------


class RecommenderProfileInjectionTests(unittest.TestCase):
    def test_profile_hint_merged_into_context(self):
        """推荐 Agent 把画像摘要拼到软引导前缀。"""
        from app.services.agents import recommender_agent as ra

        fake_product = SimpleNamespace(
            name="美式咖啡", base_price=22, tags="苦,纯粹", description="纯苦"
        )

        with (
            patch.object(ra, "extract_keywords", return_value=(["苦"], [])),
            patch.object(ra, "retrieve", return_value=[fake_product]),
            patch.object(ra, "get_hard_filters", return_value={"banned_names": [], "banned_tags": []}),
            patch.object(ra, "get_experience_for_user", return_value=""),
            patch.object(ra, "get_profile_hint", return_value="偏爱纯粹苦味"),
            patch.object(ra.llm, "chat_with_role", return_value="推荐美式"),
        ):
            result = ra.recommend(db=_FakeSession(), user_id=100, user_msg="苦的", history=[])

        # 画像摘要应出现在传给 LLM 的 context 里
        self.assertIn("偏爱纯粹苦味", result["context"])
        self.assertTrue(result["applied_experience"])


if __name__ == "__main__":
    unittest.main()
