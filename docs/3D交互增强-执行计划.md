# 3D 交互增强执行计划

> 本文档供其他 AI 按步执行。每步含：目标 / 现状 / 实施 / 验证 / 风险。
> 创建于 2026-06-21，基于 HEAD 代码 + 运行时事件验证。

## 背景

3D 咖啡厅场景（`frontend/`）有三处交互体验待增强：
1. Skill 点单的顾客能否进 3D 场景渲染（验证现有链路）
2. 角色人偶缺乏有效碰撞/避障，观感"死板"（穿模、重叠）
3. 2D 聊天（`app/static/index.html` 或 `ChatPanel`）的对话回复能否显示在 3D 人偶头上的气泡

运行环境（执行前确认）：
- 后端 `uvicorn app.main:app --reload --reload-dir app`（8000）
- 前端 `cd frontend && pnpm run dev`（5174）— **项目用 pnpm，不要用 npm**
- MySQL + Redis（docker compose 或本地）
- 构建：`cd frontend && pnpm run build`（产物 → `app/static/3d/`）

---

## 第一步：验证 skill → 3D 顾客渲染 ✅（事件层已完成）

### 现状（已验证）

代码链路完整且工作过：
- `app/services/staff_service.py:231` `customer_enter_scene(db, agent, ...)` — 统一进场函数（刷 `last_seen_at` + 广播 `enter_scene`）
- `app/services/skill_order_service.py:395` — skill 点单流程调用 `customer_enter_scene`
- `app/main.py` WS 端点 `_build_snapshot_agents` + `register_ws_presence` — snapshot 含在线顾客

运行时证据（2026-06-21 验证）：
- `/visualization/events?limit=30` 含 `agent.action` + `action_type:enter_scene` × 3、`restaurant.customer_entered` × 4
- `/agents` 含 39 个 `role_type:customer` + 17 个 `tool_name:codex`（skill 用户）

### 待补充验证（3D 渲染层）

事件层已证明链路 work，但**3D 渲染层面**（顾客人偶实际出现在 Canvas）需 Playwright 截图确认：

```bash
# 1. 跑一次 skill 点单（需 ~/.evomap 凭证 或 A2A_NODE_SECRET env）
python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁"

# 2. Playwright 打开 3D 场景，截图看顾客人偶
#    用 mcp__Playwright__browser_navigate → http://localhost:5174/3d/scene
#    首次点击页面（触发 WS + 音乐），等待 2s，browser_take_screenshot
#    验证：截图里除 4 个服务员（barista/cashier/waiter/manager）外，有顾客人偶
```

### 验证标准
- ✅ 事件层：`enter_scene` 广播（已确认）
- ⬜ 渲染层：3D Canvas 出现顾客人偶（非 4 staff）— Playwright 截图确认

### 如果渲染层失败（排查）
- 前端 `OfficeScene.tsx` `onEvent` 是否处理 `enter_scene` → `enter` behavior（`sim/roleMap.ts` ACTION_BEHAVIOR）
- `sim/agentStore.ts` `ensureAgent` 是否创建顾客 agent（`meta.id` 复用/新建）
- `roleMap.ts` `resolveRole` 顾客工位坐标（`customer` {880,580}）是否在画布内

---

## 第二步：角色碰撞系统调优（角色不再死板）

### 现状

碰撞系统**代码已有**，但效果不足：
- `frontend/src/sim/tick.ts:134-151` — `applyAgentCollisionBumps` + `bumpedUntil` + `collisionCooldownUntil` + `BUMP_RECOVERY_MS`
- `frontend/src/office3d/core/constants.ts` — `SEPARATION_STRENGTH=3`、`BUMP_FREEZE_MS=1500`、`AGENT_RADIUS=20`

CLAUDE.md 记载："去掉了 Claw3D 的 bump/separation 完整逻辑，相关字段保留但未在 tick 中使用"——即字段在但逻辑可能不完整。

### 问题假设（需实施时确认）

1. `applyAgentCollisionBumps` 力度不够（`SEPARATION_STRENGTH=3` 太小）
2. 寻路（A*）只算单 agent 路径，不考虑其他 agent 占位 → 终点重叠
3. `bumpedUntil` 冷却期间 agent 完全静止（"死板"），无平滑避让

### 实施步骤

**Step 2.1 调查现状**（读代码确认问题）：
- Read `frontend/src/sim/tick.ts` 全文（特别 `applyAgentCollisionBumps` 实现）
- Read `frontend/src/office3d/core/constants.ts`（碰撞相关常量）
- 确认 `applyAgentCollisionBumps` 是否被 tick 每帧调用（tick.ts:150 已调用）

**Step 2.2 调优参数**（`constants.ts`）：
- `SEPARATION_STRENGTH` 3 → 6~8（增大排斥力）
- `AGENT_RADIUS` 20 → 24~28（增大碰撞半径，提前避让）
- `BUMP_FREEZE_MS` 1500 → 800（缩短冻结，减少"死板"感）

**Step 2.3 增强避让逻辑**（`tick.ts`，可选）：
- 在 `moveAlongPath` 推进前，检测前方是否有其他 agent，若有则减速或微调方向
- 或在寻路目标点被占时，找附近空闲点（`navigation.ts` `findFree`）

**Step 2.4 多 agent 终点去重**（`agentStore.ts`）：
- 多个 agent 目标同一桌位时，分散到桌位周围不同点（避免终点堆叠）

### 验证

```bash
# Playwright 截图：3D 场景多 agent（4 staff + 顾客），观察是否穿模/重叠
# 触发：skill 点单让顾客进场景 + 服务员走动（walk_to_counter / deliver_order）
# 验证：截图里 agent 之间有间隙，不重叠
```

### 风险
- 中（改 sim 移动逻辑，可能影响寻路到达）
- 回滚：参数改动可逆（恢复 constants 原值）

### 文件
- `frontend/src/office3d/core/constants.ts`（参数）
- `frontend/src/sim/tick.ts`（避让逻辑）
- `frontend/src/sim/agentStore.ts`（终点去重，可选）

---

## 第三步：聊天 → 3D 人偶气泡打通

### 目标

用户在 2D 页面（`app/static/index.html` 首页 或 3D 内嵌 `ChatPanel`）聊天，AI 店长的回复**显示在 3D 店长人偶头上的对话气泡**（`agents.tsx` speechText）。

### 现状

- `frontend/src/ui/ChatPanel.tsx` — 3D 内嵌聊天面板，`sendChat(userId, text)` → POST `/chat`
- `frontend/src/office3d/objects/agents.tsx` — 人偶对话气泡（`speechText` + `speechBubbleRef`），由 `sim/agentStore.ts` 的 `speech` Map 驱动
- `app/services/staff_service.py` — `publish_agent_action(action_type="show_message")` 能广播气泡事件
- **待确认**：`/chat` 回复后，后端是否调用 `publish_agent_action(show_message, 店长, 回复文本)` 推到 WS

### 实施步骤

**Step 3.1 确认链路**：
- Read `app/main.py` 的 `/chat` 端点（约 `main.py:588`，`chat()` 函数）
- 确认回复生成后是否触发 `staff_service.publish_agent_action(db, manager_agent, "show_message", text=reply)` 或类似
- 如果**没触发** → 这是核心缺口

**Step 3.2 后端打通**（`app/main.py` `/chat`）：
```python
# 在 /chat 返回回复前，广播 show_message 让 3D 店长气泡显示
try:
    manager = staff_service.ensure_staff_agents(db)  # 或取 manager agent
    staff_service.publish_agent_action(
        db, manager, "show_message",
        text=reply,  # LLM 回复内容
        correlation_id=correlation_id,
    )
except Exception:
    pass  # best-effort，不阻断 /chat
```
- 注意：`publish_agent_action` 是 best-effort（失败 swallow），不阻断点单
- `manager` agent 的 `agent_id`（`staff:manager`）要和前端 `roleMap.ts` 的 manager 对应

**Step 3.3 前端接收**（确认已有）：
- `OfficeScene.tsx` `onEvent` 处理 `agent.action` + `action_type:show_message` → 写入 `sim/agentStore.ts` 的 `speech` Map
- `agents.tsx` 读 `speechText` 显示气泡（已有逻辑，:92-96 `speechState`）
- 确认 `show_message` 事件 payload 的 `text` 字段被前端正确取用（`agentStore.applyEvent` 的 `show_message` 分支）

**Step 3.4 2D 页面（`app/static/index.html`）也触发**：
- 2D 页面的聊天也走 `/chat`（fetch POST），所以 Step 3.2 的后端改动自动覆盖 2D 页面
- 无需额外改 2D 页面（只要 /chat 统一广播 show_message）

### 验证

```bash
# 1. Playwright 打开 3D 场景 http://localhost:5174/3d/scene
# 2. 在 ChatPanel 输入 "推荐一杯咖啡" 发送
# 3. 等 LLM 回复（~2-5s）
# 4. 截图：验证 3D 店长（manager）人偶头上气泡显示回复内容
# 5. 或看 /visualization/events 是否有 action_type:show_message 事件
```

### 风险
- 中（改 /chat 后端，但 best-effort 不阻断点单）
- LLM 无 key 时走 `_mock_chat`，回复也要触发 show_message（统一处理）

### 文件
- `app/main.py`（`/chat` 加 show_message 广播）
- `app/services/staff_service.py`（确认 publish_agent_action 支持 show_message + text payload）
- `frontend/src/sim/agentStore.ts`（确认 show_message → speech Map，已有）
- `frontend/src/office3d/objects/agents.tsx`（气泡渲染，已有）

---

## 第四步：整合验证 + 文档同步

### 目标

端到端验证三步联动 + 更新 CLAUDE.md。

### 实施

**Step 4.1 端到端验证**：
```bash
# 1. skill 点单 → 顾客进 3D（第一步）
# 2. 3D 场景观察多 agent 不穿模（第二步）
# 3. ChatPanel 聊天 → 店长气泡显示回复（第三步）
# 4. Playwright 截图记录三步联动效果
```

**Step 4.2 更新文档**：
- `frontend/CLAUDE.md` 变更记录：补"碰撞调优 + 聊天气泡打通"
- `app/CLAUDE.md` 变更记录：补"/chat 广播 show_message"
- 如有新常量/事件，同步「事件 → 渲染管线」「sim 层」小节

**Step 4.3 回归测试**：
- `python -m pytest tests/`（后端无回归）
- `cd frontend && pnpm run build`（前端编译通过）

### 验证标准
- 三步联动：顾客进场景 + 不穿模 + 聊天气泡显示
- 测试无回归
- CLAUDE.md 同步

---

## 附录

### A. 执行顺序与依赖

```
第一步（验证）→ 第二步（碰撞）→ 第三步（气泡）→ 第四步（整合）
   ↓ 已 done       ↓ 独立           ↓ 独立          ↓ 依赖 1-3
```

第二步和第三步**相互独立**，可并行或换序。

### B. 关键文件速查

| 模块 | 文件 | 职责 |
|------|------|------|
| skill 进场 | `app/services/staff_service.py:231` | customer_enter_scene |
| skill 点单 | `app/services/skill_order_service.py:395` | 调用进场 |
| /chat | `app/main.py`（chat 函数） | 聊天回复（第三步加 show_message） |
| 碰撞 | `frontend/src/sim/tick.ts:134-151` | applyAgentCollisionBumps |
| 碰撞常量 | `frontend/src/office3d/core/constants.ts` | SEPARATION_STRENGTH 等 |
| 气泡渲染 | `frontend/src/office3d/objects/agents.tsx:92` | speechText |
| 气泡状态 | `frontend/src/sim/agentStore.ts` | speech Map（show_message 事件） |
| 内嵌聊天 | `frontend/src/ui/ChatPanel.tsx` | sendChat → /chat |

### C. 风险与回滚

- 所有改动 best-effort（不阻断点单/支付）
- 碰撞参数可逆（恢复 constants 原值）
- /chat 的 show_message 广播失败 swallow（不阻断回复）
- 每步前 `git stash` 或分支保护，便于回滚

### D. 注意事项

- **包管理器用 pnpm**（项目原生 pnpm-lock.yaml，不要用 npm）
- **vite.config.ts 当前 `emptyOutDir: false`**（绕过 sounds 目录锁，构建配置）
- **Windows 上停 dev server 用 `powershell Stop-Process -Id <pid> -Force`**（TaskStop 杀不干净）
- **3D 场景 logo 用 drei `<Html>` overlay**（SVG 纹理会白屏，已用 Html 代替）
