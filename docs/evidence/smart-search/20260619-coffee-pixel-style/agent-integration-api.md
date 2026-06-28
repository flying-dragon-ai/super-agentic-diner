# Agent 工具接入与餐厅像素可视化 API

## 目标

让 Claude Code、Codex、Cursor、Trae、Tree 等 Agent 工具通过统一 REST API 注册为餐厅角色，并通过 WebSocket 让可视化页面实时新增像素人物和播放动作。

## 架构

- Agent 工具通过 Skill 调用 REST API。
- 后端保存 Agent 身份与可视化事件。
- 浏览器页面连接 `/ws/visualization` 接收实时事件。
- 现有 `/chat`、订单扣款和用户余额逻辑保持原接口不变。

## 角色

支持的 `role_type`：

- `customer`
- `waiter`
- `cashier`
- `barista`
- `manager`

Agent 身份独立于现有 `user` 表。`user` 仍表示餐厅顾客；`agent_profile` 表示外部工具或系统角色。

## 注册

`POST /agents/register`

```json
{
  "tool_name": "codex",
  "display_name": "Codex Waiter",
  "role_type": "waiter",
  "capabilities": ["take_order", "deliver_order"],
  "metadata": {
    "workspace": "crossroads-agent-cafe"
  }
}
```

响应：

```json
{
  "agent_id": 1,
  "api_token": "pa_...",
  "role_type": "waiter",
  "sprite_seed": 123456
}
```

`api_token` 只在注册响应中返回一次。调用动作和心跳接口时使用：

```text
Authorization: Bearer <api_token>
```

也支持：

```text
X-Agent-Token: <api_token>
```

## 动作上报

`POST /agents/{agent_id}/actions`

```json
{
  "action_type": "take_order",
  "target": "counter",
  "message": "接到点单",
  "correlation_id": "req-001",
  "payload": {
    "coffee_name": "柑橘冷萃"
  }
}
```

允许的 `action_type`：

- `enter_scene`
- `walk_to_counter`
- `walk_to_table`
- `take_order`
- `prepare_coffee`
- `deliver_order`
- `show_message`
- `leave_scene`
- `error`

常用 `target`：

- `entrance`
- `table`
- `counter`
- `cashier`
- `service`
- `kitchen`
- `pickup`
- `exit`

## 心跳

`POST /agents/{agent_id}/heartbeat`

用于刷新 `last_seen_at`，并向页面广播 `agent.heartbeat`。

## 查询

- `GET /agents`：列出当前 active Agent。
- `GET /visualization/events?limit=50`：查询最近可视化事件。
- `GET /status`：查询系统状态。

## WebSocket

页面连接：

```text
ws://127.0.0.1:8000/ws/visualization
```

连接成功后会收到：

```json
{
  "type": "scene.snapshot",
  "payload": {
    "events": []
  },
  "created_at": "2026-06-19T..."
}
```

后续事件统一格式：

```json
{
  "event_id": 1,
  "type": "agent.action",
  "agent_id": 1,
  "payload": {},
  "correlation_id": "req-001",
  "created_at": "2026-06-19T..."
}
```

## 订单事件

现有 `/chat` 会补充广播：

- `message.received`
- `order.intent_detected`
- `order.pending_confirmation`
- `order.payment_required`
- `order.paid`
- `order.failed`
- `order.reply`

这些事件只用于可视化，不改变 `/chat` 响应结构。

## Skill 使用

项目内置唯一对外 Skill：

```text
.agents/skills/a2a-super-order/
```

Skill 点单示例：

```bash
python .agents/skills/a2a-super-order/scripts/order.py --message "我要一杯拿铁"
```

高级可视化动作示例：

```bash
python .agents/skills/a2a-super-order/scripts/send_action.py --agent-id 1 --token "<api_token>" --action take_order --target counter --message "接到点单"
```

## 验收

- 注册 Agent 后，页面新增对应像素人物。
- 通过 `a2a-super-order` Skill 点单时，不打开网页也能创建可回放事件。
- 前两单免费；第三单起缺少 EvoMap 支付能力时订单被阻断并显示 `order.payment_required`。
- 发送 `take_order` 后，服务员走向点单台并显示气泡。
- 用户通过 `/chat` 下单时，顾客、服务员、收银员、咖啡师按订单事件动作。
- WebSocket 断开时，现有聊天和下单流程仍可用。

## Schema Notes

- MySQL is the only supported relational database for this project.
- `staff_service.py` 幂等预创建 4 个固有服务员 agent（`staff:barista`/`staff:cashier`/`staff:waiter`/`staff:manager`），在 lifespan 启动时注册并广播 `agent.registered`。这些 staff 的 `metadata.source=staff`，不持有可登录 token，仅供编排层引用。
- web 对话路径会为匿名 user 幂等创建一个顾客 agent（`web:customer:<user_id>`），其事件携带真实 `agent_id`（与 Skill 路径对齐），不再落 `agent_anon`。
- 服务员编排发生在后端：`/chat` 与 `/skill/orders` 的完成流程（`_publish_web_completion_flow` / `_publish_skill_completion_flow`）在每个业务节点追加 `agent.action` 广播。编排节点到服务员动作的映射见下表。

### 服务员编排时序

| 业务节点（已有 restaurant.* 事件） | 追加的服务员 `agent.action`（`payload.action_type`） |
|----------------------------------|--------------------------------------------------|
| `restaurant.payment_completed`     | waiter → `walk_to_counter`；cashier → `take_order` |
| `restaurant.preparation_progress`（grinding/brewing/plating） | barista → `prepare_coffee` |
| `restaurant.order_ready`           | barista → `enter_scene`（回到工位、停止 work） |
| `restaurant.order_delivered`       | waiter → `deliver_order` |
| `restaurant.customer_left`         | waiter、cashier → `enter_scene`（复位） |

编排是「尽力而为」：`ensure_staff_agents` / `ensure_web_customer_agent` 失败时静默降级，绝不阻断 `/chat`、订单或支付业务。

### scene.snapshot 的 agents 字段

`/ws/visualization` 连接时收到的 `scene.snapshot`，其 `payload.agents` 列出当前所有 active agent（4 个固有 staff + 最近活跃顾客），用于后连接页面立即渲染服务员人偶：

```json
{
  "type": "scene.snapshot",
  "payload": {
    "events": [],
    "agents": [
      { "agent_id": 8, "tool_name": "staff:barista", "display_name": "咖啡师", "role_type": "barista", "sprite_seed": 100001, "status": "active" }
    ]
  }
}
```

前端 `OfficeScene` 的 `onSnapshot` 据此预创建人偶；`onEvent` 做只读适配（兼容 `snake_case`、从 `agent.action` 外壳取 `payload.action_type`、把 `agent.registered` 映射为 `enter_scene`）。
- `order` is shared by web dialog orders and `a2a-super-order` Skill orders.
- `order.source_type` is constrained to `web_dialog` or `skill`.
- `order.payment_status` is the order-level display/status field. Skill details remain in `skill_order_ledger.payment_status`.
- `order.consumer_id`, `order.agent_id`, and `order.ledger_id` are physical foreign keys to `evomap_consumer`, `agent_profile`, and `skill_order_ledger`.
- State constants live in `app/domain_constants.py`.
- Existing MySQL databases must be upgraded with `python scripts/migrate_order_sources.py`; the script is idempotent and safe to run repeatedly.
