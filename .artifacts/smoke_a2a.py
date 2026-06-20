"""A2A 冒烟测试 3.1 + 3.2：Agent 注册/动作/鉴权 API + WS 实时广播交叉验证。

用法: python .artifacts/smoke_a2a.py
退出码 0 = 全部断言通过; 非 0 = 有失败项。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx
import websockets

BASE = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/visualization"

VALID_ACTIONS = [
    "enter_scene", "walk_to_counter", "walk_to_table", "take_order",
    "prepare_coffee", "deliver_order", "show_message", "leave_scene", "error",
]

received: list[dict] = []
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" :: {detail}" if detail else ""))


async def ws_reader(ws) -> None:
    """持续读 WS 消息存入 received（直到任务被取消）。"""
    try:
        async for raw in ws:
            try:
                received.append(json.loads(raw))
            except Exception:
                pass
    except websockets.ConnectionClosed:
        pass


async def main() -> int:
    # ---- 连 WS，验证 snapshot ----
    try:
        ws = await websockets.connect(WS_URL, open_timeout=10)
    except Exception as e:
        record("WS 连接", False, f"connect 失败: {e}")
        return 1

    reader_task = asyncio.create_task(ws_reader(ws))
    # 等第一条 snapshot 到达
    await asyncio.sleep(1.5)
    snapshot = next((m for m in received if m.get("type") == "scene.snapshot"), None)
    if snapshot:
        agents = snapshot.get("payload", {}).get("agents", [])
        staff = [a for a in agents if str(a.get("tool_name", "")).startswith("staff:")]
        record("L2 snapshot 推送", True, f"agents={len(agents)}, staff={len(staff)}")
        record("L2 snapshot 含 4 服务员", len(staff) >= 4, ", ".join(a.get("tool_name", "?") for a in staff))
    else:
        record("L2 snapshot 推送", False, "未收到 scene.snapshot")

    baseline = len(received)  # 后续新增广播从这之后算

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        # ---- 3.1 注册 ----
        reg_payload = {
            "tool_name": f"smoke-a2a-{int(time.time())}",
            "display_name": "冒烟测试员A2A",
            "role_type": "customer",
            "capabilities": ["a2a_super_order"],
            "metadata": {"source": "smoke_a2a"},
        }
        r = await client.post("/agents/register", json=reg_payload)
        reg_ok = r.status_code == 200
        body = r.json() if reg_ok else {}
        record("L1 注册 200", reg_ok, f"status={r.status_code}")
        if reg_ok:
            record("L1 返回 token/agent_id/sprite_seed",
                   bool(body.get("api_token") and body.get("agent_id") and body.get("sprite_seed")),
                   f"agent_id={body.get('agent_id')} sprite_seed={body.get('sprite_seed')}")
        agent_id = body.get("agent_id")
        token = body.get("api_token", "")

        # 等 agent.registered 广播
        await asyncio.sleep(0.8)
        new_msgs = received[baseline:]
        baseline = len(received)
        registered = [m for m in new_msgs if m.get("type") == "agent.registered"]
        record("L2 广播 agent.registered", len(registered) >= 1,
               f"收到 {len(registered)} 条" + (f" (display_name={registered[0]['payload'].get('display_name')})" if registered else ""))

        # ---- 3.1 逐个发 9 种 action ----
        auth_h = {"Authorization": f"Bearer {token}"}
        action_ok_count = 0
        for i, act in enumerate(VALID_ACTIONS):
            ra = await client.post(f"/agents/{agent_id}/actions",
                                   headers=auth_h,
                                   json={"action_type": act, "correlation_id": f"smoke-{i}",
                                         "message": f"动作 {act}"})
            if ra.status_code == 200 and ra.json().get("ok") is True:
                action_ok_count += 1
        record("L1 9 种 action_type 全 200", action_ok_count == 9, f"{action_ok_count}/9 通过")

        # ---- 3.1 heartbeat ----
        rh = await client.post(f"/agents/{agent_id}/heartbeat", headers=auth_h)
        record("L1 heartbeat 200", rh.status_code == 200, f"status={rh.status_code}")

        # ---- 3.1 鉴权失败：错 token → 401 ----
        rw = await client.post(f"/agents/{agent_id}/actions",
                               headers={"Authorization": "Bearer wrong_token"},
                               json={"action_type": "enter_scene"})
        record("L1 错 token → 401", rw.status_code == 401, f"status={rw.status_code}")

        # ---- 3.1 非法 action_type → 400 ----
        ri = await client.post(f"/agents/{agent_id}/actions",
                               headers=auth_h,
                               json={"action_type": "fly_to_moon"})
        record("L1 非法 action → 400", ri.status_code == 400, f"status={ri.status_code}")

        # 等 WS 广播到达
        await asyncio.sleep(1.5)
        new_msgs = received[baseline:]
        actions_broadcast = [m for m in new_msgs if m.get("type") == "agent.action"]
        action_types = [m.get("payload", {}).get("action_type") for m in actions_broadcast]
        record("L2 广播 agent.action 数量", len(actions_broadcast) >= 9,
               f"收到 {len(actions_broadcast)} 条 action 广播 (含 heartbeat 可能 +1)")
        # 验证 9 种 action_type 都被广播（去重比对）
        missing = set(VALID_ACTIONS) - set(action_types)
        record("L2 9 种 action_type 广播齐全", not missing,
               f"缺失: {missing}" if missing else "全部 9 种均广播")

        # ---- 3.1 GET /agents 确认新 agent 在列 ----
        rg = await client.get("/agents")
        agents_list = rg.json() if rg.status_code == 200 else []
        found = any(a.get("agent_id") == agent_id for a in agents_list)
        record("L1 GET /agents 含新 agent", found, f"agent_id={agent_id}")

        # ---- 3.2 GET /visualization/events 确认落库 ----
        rv = await client.get("/visualization/events", params={"limit": 200})
        events = rv.json() if rv.status_code == 200 else []
        # 找出我们刚发的 agent.action 事件（按 agent_id 过滤）
        ours = [e for e in events if e.get("agent_id") == agent_id and e.get("type") == "agent.action"]
        record("L2 事件落库 visualization_event", len(ours) >= 9,
               f"agent_id={agent_id} 的 agent.action 事件 {len(ours)} 条")

    # 收尾
    reader_task.cancel()
    try:
        await ws.close()
    except Exception:
        pass

    # ---- 汇总 ----
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n=== 冒烟 3.1+3.2 汇总: {passed}/{total} PASS ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
