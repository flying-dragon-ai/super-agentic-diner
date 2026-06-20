---
doc_type: roadmap
slug: free-layout-agent-migration
status: active
created: 2026-06-19
last_reviewed: 2026-06-19
tags: [pixel-visualization, free-layout, movement, agent-integration]
related_requirements: []
related_architecture: [ARCHITECTURE]
---

# 自由布局、移动机制与 Agent 接入迁移

## 1. 背景

Coffee AI Boss 当前已有 FastAPI + 静态 HTML/JS/CSS 的餐厅可视化：后端通过 `VisualizationEvent` 持久化事件，经 `/ws/visualization` 广播；前端 `order-visualization.js` 用固定 `points`、固定家具绘制和直线插值移动来表现订单流程。

`D:\temp\EVOMAP\pixel-agents-main` 提供了更完整的像素空间机制：`OfficeLayout` 网格布局、tile/furniture/seat 数据结构、BFS 路径移动、RAF 渲染循环、z-sort、sprite asset catalog、编辑器拖拽/绘制，以及 Agent 生命周期事件接入。本 roadmap 目标是迁移这些核心能力到 Coffee AI Boss，但保留当前 FastAPI、MySQL、Redis、A2A Skill、订单/支付逻辑边界。

## 2. 范围与明确不做

### 本 roadmap 覆盖

- 餐厅自由布局 schema：地板、墙、空洞、家具、station、seat、spawn 点。
- 布局持久化与 snapshot：MySQL 中保存 active layout 和 actor state，WebSocket snapshot 带布局与当前角色。
- 移动机制：从固定像素点改为 tile grid + walkable/blocked tiles + BFS path + RAF 插值。
- 像素资产迁移：抽取 pixel-agents 的 floors/walls/furniture/characters catalog 方式，迁移到静态 Web 可用资产。
- Agent 接入升级：保留现有 `/skill/register`、`/skill/orders`、`/agents/*`，把事件转换为 layout-aware scene command。
- 可视化编辑入口：提供最小 admin/editor 能力绘制 tile、摆放/移动家具、保存布局。
- 验证与文档：API 单测、迁移脚本幂等测试、浏览器 canvas 像素/交互验证、Skill 回归。

### 明确不做

- 不迁移 VS Code 扩展、Claude hook installer、terminal/session scanner、Fastify server。
- 不引入 SQLite、fakeredis、内存 fallback，也不改 MySQL/Redis 架构边界。
- 不合并 web dialog 与 A2A Skill 的支付逻辑。
- 不让外部 Agent 直接改余额、订单或数据库；Agent 仍通过现有 Skill/API 入口。
- 不在本 roadmap 内重做完整 React/Vite 应用。第一阶段优先保持静态 JS；是否引入前端构建链另行决策。

## 3. 模块拆分（概设）

```text
free-layout-agent-migration
├── Layout Model：定义并持久化餐厅布局、station、seat、blocked tile
├── Scene Engine：前端渲染 tile/furniture/character，计算路径和动画
├── Scene Protocol：把后端事件翻译成前端 scene command / snapshot
├── Asset Catalog：迁移像素资产 manifest、sprite 加载、z-sort 元数据
├── Layout Editor：提供自由布局编辑和保存入口
└── Agent Adapter：把 Skill/Agent/Presence 映射为 actor state 与 scene command
```

### Layout Model

- **职责**：定义 `RestaurantLayout`、`RestaurantActorState`，提供 active layout 读写和 actor snapshot。
- **承载的子 feature**：`layout-persistence-api`, `layout-editor-admin`
- **触碰的现有代码 / 模块**：`app/db/models.py`, `scripts/migrate_order_sources.py`, `app/main.py` 或新 service/router。

### Scene Engine

- **职责**：替换当前固定 `points` + 直线移动，使用 tile grid、blocked tiles、BFS path、RAF loop、depth sort。
- **承载的子 feature**：`layout-engine-minimal-loop`, `pixel-asset-catalog`
- **触碰的现有代码 / 模块**：`app/static/order-visualization.js`, `app/static/order-visualization.css`, `app/static/screen.html`, `app/static/index.html`。

### Scene Protocol

- **职责**：统一 WebSocket snapshot 与增量事件，保证旧 `restaurant.*`、`agent.*`、`presence.*` 可转换为 scene command。
- **承载的子 feature**：`scene-command-protocol`
- **触碰的现有代码 / 模块**：`app/services/visualization_service.py`, `app/services/skill_order_service.py`, `app/main.py`。

### Asset Catalog

- **职责**：从 pixel-agents 迁移可用 PNG 与 manifest，定义 footprint、category、orientation、surface/wall placement。
- **承载的子 feature**：`pixel-asset-catalog`
- **触碰的现有代码 / 模块**：`app/static/assets/restaurant/*`, `app/static/order-visualization.js`。

### Layout Editor

- **职责**：提供 tile paint、wall paint、furniture place/select/move/delete、undo/redo、save。
- **承载的子 feature**：`layout-editor-admin`
- **触碰的现有代码 / 模块**：`app/static/screen.html`, `app/static/order-visualization.js`, layout API。

### Agent Adapter

- **职责**：把 `AgentProfile`、Skill order、manual action、presence visitor 映射成 actor；保留 token 鉴权和 Skill 单入口。
- **承载的子 feature**：`agent-entrypoint-upgrade`
- **触碰的现有代码 / 模块**：`app/main.py`, `.agents/skills/a2a-super-order/`, `app/services/skill_order_service.py`。

## 4. 模块间接口契约 / 共享协议（架构层详设）

### 4.1 RestaurantLayout

**方向**：Layout Model -> Scene Engine / Scene Protocol

**形式**：JSON schema + MySQL `restaurant_layout.layout_json`

**契约**：

```json
{
  "version": 1,
  "layout_id": "default-restaurant",
  "revision": 1,
  "tile_size": 16,
  "cols": 40,
  "rows": 24,
  "tiles": [255, 0, 1],
  "tile_colors": [{"h": 35, "s": 30, "b": 15, "c": 0, "colorize": false}],
  "furniture": [
    {"uid": "counter-1", "type": "SERVICE_COUNTER", "col": 22, "row": 8, "color": null}
  ],
  "stations": {
    "entrance": {"col": 2, "row": 20},
    "counter": {"col": 23, "row": 13},
    "cashier": {"col": 32, "row": 13},
    "kitchen": {"col": 8, "row": 8},
    "pickup": {"col": 29, "row": 16},
    "exit": {"col": 38, "row": 21}
  },
  "seats": [{"uid": "seat-1", "col": 10, "row": 18, "facing": "up"}]
}
```

**约束**：

- `tiles.length == cols * rows`；`0=wall`、`1..9=floor variants`、`255=void`。
- 普通家具不能放在 `wall/void`，墙饰类只能锚定 wall。
- station 必须落在 walkable tile 或有可寻路的邻接 walkable tile。
- active layout 只能有一份；历史 layout 保留 revision。

### 4.2 Layout API

**方向**：Layout Editor / Scene Engine -> Backend

**形式**：HTTP API

**契约**：

```text
GET /visualization/layout
Response: RestaurantLayout

PUT /visualization/layout
Request: { layout: RestaurantLayout, expected_revision: int | null }
Response: { ok: true, revision: int }
错误：400 invalid_layout, 409 revision_conflict, 500 internal

GET /visualization/assets/catalog
Response: { floors: [], walls: [], furniture: [], characters: [] }
```

**约束**：

- 既有 MySQL 升级走 `scripts/migrate_order_sources.py`，脚本必须幂等。
- API 不返回任何 token、连接串或 `.env` 信息。
- layout validation 失败不能写库。

### 4.3 Scene Snapshot / Command

**方向**：Backend -> Scene Engine

**形式**：WebSocket server message，兼容现有 `/ws/visualization`

**契约**：

```json
{
  "type": "scene.snapshot",
  "payload": {
    "layout": "RestaurantLayout",
    "actors": [
      {
        "actor_key": "agent:1",
        "agent_id": 1,
        "role_type": "waiter",
        "display_name": "Codex Waiter",
        "sprite_seed": 123456,
        "tile": {"col": 23, "row": 13},
        "status": "idle",
        "seat_id": null
      }
    ],
    "events": []
  },
  "created_at": "ISO8601"
}
```

```json
{
  "event_id": 10,
  "type": "scene.command",
  "agent_id": 1,
  "correlation_id": "req-001",
  "payload": {
    "actor_key": "agent:1",
    "command": "spawn|walk_to|set_status|show_bubble|despawn",
    "target": {"station": "counter", "col": null, "row": null},
    "status": "walking",
    "bubble": "接到点单",
    "source_event_type": "agent.action"
  },
  "created_at": "ISO8601"
}
```

**约束**：

- 旧事件 `restaurant.*`、`agent.*`、`presence.*` 继续广播；前端可直接消费旧事件，也可消费由后端补发的 `scene.command`。
- `scene.command.target` 必须可解析为 station 或 tile；不可达时返回/广播 `scene.command_failed`，不阻断订单业务。
- snapshot 里的 `events` 保留最近事件回放，`actors` 是当前事实状态，不依赖最近 50 条事件重建。

### 4.4 前端 Scene Engine API

**方向**：页面 / Screen -> Scene Engine

**形式**：全局静态 JS API，替代/扩展 `window.OrderVisualization`

**契约**：

```javascript
const scene = window.RestaurantScene.create({
  canvas: "#orderGameCanvas",
  layoutPath: "/visualization/layout",
  assetsPath: "/visualization/assets/catalog",
  wsPath: "/ws/visualization",
  agentsPath: "/agents"
});

scene.applyServerMessage(message);
scene.enqueueCommand(command);
scene.moveActorTo("agent:1", { station: "counter" });
scene.exportState();
scene.destroy();
```

**约束**：

- `applyServerMessage` 必须兼容现有 `scene.snapshot`、`restaurant.*`、`agent.*`、`presence.*`。
- 路径计算使用 4 邻接 BFS；无 path 时不穿墙，显示失败状态。
- 渲染按 `zY` / actor y 坐标排序，保证家具遮挡关系稳定。
- WebSocket 断开时，聊天和点单仍可用；重连后通过 snapshot 修正状态。

### 4.5 Agent Action 扩展

**方向**：Agent Adapter -> Backend -> Scene Protocol

**形式**：保持现有 `POST /agents/{agent_id}/actions`

**契约**：

```json
{
  "action_type": "walk_to_counter",
  "target": "counter",
  "target_tile": {"col": 23, "row": 13},
  "message": "接到点单",
  "correlation_id": "req-001",
  "payload": {
    "bubble": "接单",
    "status": "taking_order",
    "scene_command": "walk_to"
  }
}
```

**约束**：

- `target` 保留字符串 station；`target_tile` 可选，优先级高于 `target`。
- 普通 Skill 点单仍只用 `.agents/skills/a2a-super-order/scripts/order.py`；manual action 只做视觉进度，不创建订单、不改余额。
- token 只通过 `Authorization` 或 `X-Agent-Token` 输入，不进入日志和前端。

### 4.6 MySQL 数据结构

**方向**：Layout Model / Scene Protocol -> MySQL

**形式**：共享数据库表

**契约**：

```text
restaurant_layout(
  layout_id BIGINT PK,
  slug VARCHAR(64) UNIQUE,
  revision INT NOT NULL,
  layout_json LONGTEXT NOT NULL,
  active BOOLEAN NOT NULL,
  created_at DATETIME,
  updated_at DATETIME
)

scene_actor_state(
  actor_key VARCHAR(128) PK,
  agent_id BIGINT NULL FK agent_profile.agent_id,
  role_type VARCHAR(32) NOT NULL,
  display_name VARCHAR(128) NOT NULL,
  sprite_seed INT NOT NULL,
  tile_col INT NULL,
  tile_row INT NULL,
  seat_id VARCHAR(128) NULL,
  status VARCHAR(32) NOT NULL,
  metadata_json TEXT NULL,
  last_seen_at DATETIME,
  updated_at DATETIME,
  expires_at DATETIME NULL
)
```

**约束**：

- 不弱化现有 `order.consumer_id`、`order.agent_id`、`order.ledger_id` 外键。
- `scene_actor_state.agent_id` 可空，因为 presence visitor / system actor 不一定有 `AgentProfile`。
- 清理过期 presence actor 不能删除订单、AgentProfile 或 VisualizationEvent。

## 5. 子 feature 清单

1. **layout-engine-minimal-loop** — 在静态前端引入 RestaurantLayout、tile 渲染、blocked tiles、BFS path，把现有 WebSocket 事件映射到新引擎移动。
   - 所属模块：Scene Engine / Scene Protocol
   - 依赖：无
   - 状态：planned
   - 对应 feature：未启动
   - 备注：最小闭环；先用默认内置布局和现有手绘像素角色。

2. **layout-persistence-api** — 新增 MySQL layout/actor state 表、幂等迁移、`GET/PUT /visualization/layout` 和增强 snapshot。
   - 所属模块：Layout Model / Scene Protocol
   - 依赖：layout-engine-minimal-loop
   - 状态：planned
   - 对应 feature：未启动

3. **scene-command-protocol** — 后端把 `restaurant.*`、`agent.*`、`presence.*` 转为 `scene.command`，并维护 `scene_actor_state`。
   - 所属模块：Scene Protocol / Agent Adapter
   - 依赖：layout-persistence-api
   - 状态：planned
   - 对应 feature：未启动

4. **pixel-asset-catalog** — 迁移 floors/walls/furniture/characters 的最小资产集和 catalog loader，替换固定家具绘制为 sprite + z-sort。
   - 所属模块：Asset Catalog / Scene Engine
   - 依赖：layout-engine-minimal-loop
   - 状态：planned
   - 对应 feature：未启动

5. **layout-editor-admin** — 在 `/screen` 或独立 admin 入口提供 tile/wall/furniture 编辑、拖拽移动、撤销重做、保存布局。
   - 所属模块：Layout Editor / Layout Model / Asset Catalog
   - 依赖：layout-persistence-api, pixel-asset-catalog
   - 状态：planned
   - 对应 feature：未启动

6. **agent-entrypoint-upgrade** — 扩展 Agent action payload、A2A Skill 视觉事件和 station/target_tile 映射，保持 Skill 单入口与 token 红线。
   - 所属模块：Agent Adapter / Scene Protocol
   - 依赖：scene-command-protocol
   - 状态：planned
   - 对应 feature：未启动

7. **visualization-regression-suite** — 补 API/migration/service 单测、WebSocket 回放测试、Playwright canvas 像素和交互验证、文档更新。
   - 所属模块：跨模块
   - 依赖：scene-command-protocol, pixel-asset-catalog, layout-editor-admin, agent-entrypoint-upgrade
   - 状态：planned
   - 对应 feature：未启动

**最小闭环**：第 1 条 `layout-engine-minimal-loop` 完成后，打开 `/screen`，浏览器从默认 `RestaurantLayout` 渲染餐厅格子和角色；触发一次现有 `restaurant.customer_entered` 或 `agent.action`，角色不再直线穿越固定点，而是沿 walkable tile BFS 路径移动到 station。

## 6. 排期思路

技术依赖上先做前端最小闭环，因为它能验证 pixel-agents 的核心 `layout + path + render` 是否能在现有静态 JS 架构中成立。随后做 MySQL 持久化和 snapshot，让刷新页面不再只依赖最近事件。再做 scene command 协议，把后端事件从业务阶段提升为可视化命令。资产迁移与编辑器可以并行于后端协议，但编辑器保存必须等 layout API。Agent 入口升级放在协议稳定之后，避免 Skill 和 REST 客户端追着前端私有实现改。

技术依赖之外的产品优先级待用户决定：如果更看重视觉效果，可提前做 `pixel-asset-catalog`；如果更看重可运营配置，可提前做 `layout-editor-admin`。

## 7. 观察项

- 现有 `docs/pixel-agents-integration.md` 写的是 MVP 策略：“复用思路，不直接引入 pixel-agents 代码”。本 roadmap 不与其冲突，但会把后续路径从“手绘固定场景”推进到“抽取布局/移动/资产机制”。
- `.codestable/architecture/ARCHITECTURE.md` 目前只是骨架；roadmap 落地后需要由 feature acceptance 回写真实架构，不在本次 roadmap 阶段顺手改。
- 全目录 `validate-yaml.py --dir .codestable` 会因 reference/attention 骨架没有 frontmatter 报错；roadmap 落盘时只校验 `free-layout-agent-migration-items.yaml --yaml-only`。
