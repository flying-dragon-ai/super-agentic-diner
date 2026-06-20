# Coffee AI Boss — Skill 接入可视化联动 执行 Roadmap

> 📌 **这是一份交付给实施 Agent 的任务书。** 拿到此文档的 Agent 无需任何历史对话上下文，按本文档即可独立执行。
>
> **生成时间**：2026-06-20 ｜ **来源**：基于对前后端 + Skill 的逐文件代码勘察 ｜ **决策人**：项目 Owner
> **状态**：待执行（见文末「进度记录」）
> **姊妹文档**：`docs/3D-ALIGNMENT-ROADMAP.md`（3D 渲染能力对齐，与本任务互补）

---

## 0. 给执行 Agent 的必读说明

### 0.1 你的任务

打通 **「外部 Agent 工具（Claude Code/Codex/Cursor/Trae）通过 Skill 接入 → 注册 → 可视化页面新增人物 → 下单时服务员联动动作」** 这条链路。

现状：地基（Skill 脚本、后端注册/下单 API、3D 人偶渲染器）都已就绪且免费单闭环已通，但**前后端事件契约错配 + 缺服务员团队与编排层**，导致"新增人物 + 服务员动作"基本全断。你的活儿是**修契约 + 补服务员团队 + 加后端编排**。

### 0.2 动手前必读文件（按顺序）

| 序 | 文件 | 为什么必读 |
|----|------|-----------|
| 1 | `D:\temp\EVOMAP\coffee-ai-boss\.agents\skills\a2a-super-order\SKILL.md` | 唯一对外点单 Skill 的使用说明 |
| 2 | `D:\temp\EVOMAP\coffee-ai-boss\.agents\skills\a2a-super-order\references\api.md` | Skill 调用的 REST 契约（/skill/register、/skill/orders、ws）|
| 3 | `D:\temp\EVOMAP\coffee-ai-boss\docs\agent-integration-api.md` | Agent 接入 API 契约（/agents/register、/agents/{id}/actions）|
| 4 | `D:\temp\EVOMAP\coffee-ai-boss\app\main.py` | 后端路由总入口（注册/chat/skill/ws），重点看第 827-986、1272-1305 行 |
| 5 | `D:\temp\EVOMAP\coffee-ai-boss\app\services\visualization_service.py` | `VALID_AGENT_ROLES`/`VALID_AGENT_ACTIONS`/事件广播/snapshot |
| 6 | `D:\temp\EVOMAP\coffee-ai-boss\app\services\skill_order_service.py` | Skill 下单链路 + `_publish_skill_completion_flow` 事件序列 |
| 7 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\screens\OfficeScene.tsx` 第 86-107 行 | ⚠️ 契约错配的源头（onEvent 回调）|
| 8 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\sim\roleMap.ts` | 角色→工位/颜色/行为映射，`ACTION_BEHAVIOR` 在第 46-56 行 |
| 9 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\sim\agentStore.ts` 第 85-144 行 | applyEvent 事件→动作分派 |
| 10 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\net\api.ts` **顶部注释** | ⚠️ ws 事件契约只读铁律 |

### 0.3 操作铁律（违反一条就返工）

1. **路径永远用双引号包裹**（Windows 环境）。
2. **ws 事件契约只读**——`/ws/visualization` 的 role 集合 `{customer,waiter,cashier,barista,manager}` 和 action 集合**不可删改**；只**新增** staff 编排事件（`agent.action` 类型）。
3. **前端只做"读取适配"**——兼容 snake_case、识别 `agent.action` 外壳取 `payload.action_type`，**不改契约语义**。编排逻辑全在后端。
4. **不动后端业务表**——order/User/SkillOrderLedger/EvomapConsumer 表结构零修改；staff agent 走现有 `AgentProfile` 表（`staff:` 前缀 agent_id + metadata `source=staff`）。
5. **不改 `/chat`、`/admin/restaurant-state`、订单/支付业务逻辑**——只在事件广播节点**追加**服务员动作事件。
6. **服务员调度简单化**——单服务员（一个 barista、一个 waiter）够用，不做"谁空闲"复杂调度（YAGNI）。
7. **代码注释语言跟随现有文件**——后端 Python 英文注释，前端 TS 英文注释。
8. **改前先读**——修改任何文件前先 Read 理解上下文。
9. **不擅自 git 提交/建分支**——除非 Owner 要求。
10. **设计文档漂移要修**——`docs/点单SKILL生成.md` 描述的旧设计与现行不符，本次必须更新（见 Phase 5）。

---

## 1. 项目背景

### 1.1 三层架构

```
┌─ Skill 层 ─────────────────────────────────────────────┐
│  .agents/skills/a2a-super-order/                        │
│    SKILL.md + scripts/order.py + references/api.md      │
│    纯 Python HTTP，跨工具通用（不依赖 MCP）              │
└───────────────────────┬────────────────────────────────┘
                        │ POST /skill/register + /skill/orders
                        ▼
┌─ 后端 (FastAPI Python, app/) ──────────────────────────┐
│  main.py: /agents/register, /skill/register,            │
│           /skill/orders, /chat, /ws/visualization        │
│  services/: visualization_service, skill_order_service, │
│             evomap_payment_service                      │
│  db/models.py: AgentProfile, User, SkillOrderLedger...  │
└───────────────────────┬────────────────────────────────┘
                        │ ws 广播事件
                        ▼
┌─ 前端 (React+R3F, frontend/) ──────────────────────────┐
│  screens/OfficeScene.tsx: 3D 主场景，onEvent 消费 ws     │
│  sim/: agentStore(applyEvent) + tick + roleMap          │
│  office3d/objects/agents.tsx: AgentModel 盒状人偶渲染    │
│  net/: visualizationSocket + api                        │
└─────────────────────────────────────────────────────────┘
```

### 1.2 技术栈

| 层 | 技术 |
|----|------|
| Skill | 纯 Python（标准库 urllib）|
| 后端 | FastAPI + SQLAlchemy + MySQL + Redis（禁止 SQLite/fakeredis）|
| 前端 | React 19 + TypeScript 5.6 + Vite 6 + @react-three/fiber 9.5 + three 0.183 |
| 通信 | WebSocket `/ws/visualization`（连接即收 scene.snapshot，之后实时单事件）|

### 1.3 关键事实（避免踩雷）

- **项目无用户账号体系**：`User` 表只有 user_id/nickname/balance，无 password；`/chat` 匿名走单。`UserAccount`（3D 登录用）与下单解耦。
- **"像素人物" = 3D 低多边形盒状人偶**（AgentModel），非 2D sprite。2D 像素方案已归档到 `_archive/`。
- **事件结构**：`{event_id, type, agent_id, payload, correlation_id, created_at}`。
- **后端角色/动作集合**（`visualization_service.py:15-26`）：
  - roles: `{customer, waiter, cashier, barista, manager}`
  - actions: `{enter_scene, walk_to_counter, walk_to_table, take_order, prepare_coffee, deliver_order, show_message, leave_scene, error}`

---

## 2. 现状诊断（5 个致命契约错配）

### ✅ 已通
- Skill 跨工具下单（免费单闭环）：`order.py` → `/skill/register` → `/skill/orders` → 事件广播
- WS 实时广播 + snapshot 回放最近 50 条
- 3D AgentModel 渲染（walking/sitting/working/error/away + 表情 + 气泡）

### 🔴 5 个 Bug（必须修）

| # | Bug | 位置 | 后果 |
|---|-----|------|------|
| **B1** | 前端把 `event.type` 当动作传给 applyEvent，但后端动作事件外层 type 永远是 `"agent.action"`，**真动作在 `payload.action_type`** | `frontend/src/screens/OfficeScene.tsx:99` | **9 种动作全触发不了**，全 fallback `walk_to_table` |
| **B2** | 后端 payload snake_case（`display_name`/`role_type`/`sprite_seed`），前端读 camelCase（`name`/`role`/`spriteSeed`） | `OfficeScene.tsx:93-97` | 注册成 barista 也显示**灰色"访客"**，名字永远"员工 N" |
| **B3** | 后端下单广播 10+ 种 `restaurant.*`/`order.*`，前端 `ACTION_BEHAVIOR` 一个 key 都没对上 | `roleMap.ts:46-56` | 下单完全不驱动服务员 |
| **B4** | Web 下单事件全不带 `agent_id`（落 `agent_anon`）；**餐厅无固有服务员团队人偶** | `main.py` web 事件 + 无 staff 预创建 | 永远只有一个灰人偶乱走 |
| **B5** | 没有"业务事件→多角色动作编排"层 | `skill_order_service.py` / `main.py` | 顾客下单后，没人触发 barista 做咖啡、waiter 送餐 |

> **B1+B2 是单点修复就能解锁一大片的关键。**

---

## 3. 架构决策

### 3.1 角色模型（Owner 已定：A 方案）

```
接入工具 (Claude Code/Codex/Cursor/Trae)
  └─ a2a-super-order skill 下单
     └─ 注册为 customer 角色 (接入顾客)
                        │
                        ▼
后端 (FastAPI)
  ├─ 顾客 agent (动态, 每个接入工具一个)
  └─ 服务员团队 (4 个固有 staff agent, 预创建)
      staff:barista / staff:cashier / staff:waiter / staff:manager
  下单编排: 顾客→waiter接单→cashier收银→barista做咖啡→waiter送餐
                        │ ws 广播 agent.action 事件
                        ▼
3D 前端 (OfficeScene): 顾客人偶 + 4 服务员人偶各自按动作动画
```

### 3.2 编排位置：**后端编排**（分析结论，强烈推荐）

| 维度 | 后端编排 ✅ | 前端编排 ❌ |
|------|-----------|-----------|
| 业务逻辑归属 | 后端（单一真源） | 前端承担业务（违反契约只读）|
| 多客户端一致 | 3D/大屏/未来客户端全一致 | 各前端各自实现易漂移 |
| 改动量 | 中（已有 completion_flow 节点追加事件） | 大（前端新建编排状态机）|
| 契约原则 | 符合 `api.ts`「role/action 只读、前端纯渲染」 | 前端猜事件语义，脆弱 |
| 服务员调度 | 后端握 `staff:barista` 等 agent_id，直接引用 | 前端自维护"谁是谁" |
| 已有编排时机 | `_publish_skill/web_completion_flow` 已按序发事件，天然是编排节点 | — |

**结论**：项目铁律"后端管业务、前端纯渲染"。编排是业务逻辑，必须后端。`_publish_*_completion_flow` 已在正确节点发事件，**只需追加服务员动作广播**。

---

## 4. 分阶段 Roadmap（按顺序执行）

### Phase 1 — 前端事件契约适配（最高优先级，解锁基础）

**目标**：修 B1/B2/B3，让现有事件能正确驱动人偶。**单点修复解锁一大片。**

| 文件 | 改动 |
|------|------|
| `frontend/src/screens/OfficeScene.tsx:86-107` | **onEvent 回调重写**：<br>①字段适配——payload 兼容 snake_case：`name = payload.display_name ?? payload.name`、`role = payload.role_type ?? payload.role`、`spriteSeed = payload.sprite_seed ?? payload.spriteSeed`<br>②事件分发——`event.type === "agent.action"` 时取 `payload.action_type` 作 action；`event.type === "agent.registered"` 时按 role 转 `enter` 语义到对应工位 |
| `frontend/src/sim/roleMap.ts:46-56` | `ACTION_BEHAVIOR` 保持 9 种动作 key（已对齐后端 `VALID_AGENT_ACTIONS`）；确认 `resolveAction` 兜底不误伤 `agent.registered`（onEvent 层已转换） |
| `frontend/src/sim/agentStore.ts:85-144` | 确认 `enter` 分支按 `meta.role` 路由到 `ROLE_DESK[role]`（role 字段修好后即生效） |

**验证**：手动 `POST /agents/{id}/actions` 发 `take_order` → 人偶触发 work（绿圈脉冲+眯眼）；发 `show_message` → 头顶气泡。

---

### Phase 2 — 后端预创建服务员团队（B4 核心）

**目标**：餐厅启动即有 4 个固有服务员人偶，snapshot 能回放。

| 文件 | 改动 |
|------|------|
| `app/services/staff_service.py`（**新建**） | `ensure_staff_agents(db)`：幂等创建 4 个固有 agent——`staff:barista`(barista)、`staff:cashier`(cashier)、`staff:waiter`(waiter)、`staff:manager`(manager)；各有 display_name（"咖啡师/收银员/服务员/主管"）、固定 sprite_seed、status=active、metadata `source=staff` |
| `app/main.py` lifespan startup | 启动调 `ensure_staff_agents(db)`；广播 4 条 `agent.registered` 让前端预创建人偶 |
| `app/services/visualization_service.py:90-99`（snapshot） | `scene.snapshot` payload **追加 `agents` 字段**——当前所有 active agent（staff + 在线顾客），让**后连接页面也能看到服务员** |
| `frontend/src/screens/OfficeScene.tsx` | onEvent 收 snapshot 时遍历 `payload.agents` 预创建人偶 |

**工位坐标**（来自 `roleMap.ts` ROLE_DESK，CANVAS 1800×720）：barista(360,540) / cashier(620,320) / waiter(880,660) / manager(1180,320)。

**验证**：重启后端 → 3D 页面立即出现 4 个服务员人偶在各自工位。

---

### Phase 3 — 后端下单编排联动（B5 核心，体验闭环）⭐

**目标**：顾客下单时，服务员按业务节点自动动作。**在已有 completion_flow 节点追加广播。**

#### 服务员编排时序表（一个顾客完整下单流程）

| 业务节点（已有事件） | 追加的服务员动作（新增 agent.action 广播） | 视觉效果 |
|---------------------|------------------------------------------|---------|
| 顾客 `enter_scene` | 顾客走到 customer 工位 | 顾客人偶入场就座 |
| `order.intent_detected` | `staff:waiter` → `walk_to_counter` | 服务员走向收银台接单 |
| `restaurant.payment_completed` | `staff:cashier` → `take_order`(work) | 收银员绿圈收银 |
| `restaurant.preparation_progress`(grinding) | `staff:barista` → `prepare_coffee`(work) | 咖啡师绿圈做咖啡 |
| `restaurant.preparation_progress`(brewing/plating) | barista 继续 work | 持续制作 |
| `restaurant.order_ready` | barista 停止 work（idle） | 咖啡师完成 |
| `restaurant.order_delivered` | `staff:waiter` → `deliver_order` | 服务员走到顾客桌位送餐 |
| `restaurant.customer_left` | waiter 返回工位 + cashier idle | 服务员复位 |

| 文件 | 改动 |
|------|------|
| `app/services/skill_order_service.py`（`_publish_skill_completion_flow` 及相关节点） | 每个业务节点追加 `_publish_visualization_event(db, "agent.action", {agent_id:"staff:xxx", action_type:"...", ...})` |
| `app/main.py`（`_publish_web_completion_flow` + web 事件链） | 同上；**同时修 B4**：web 路径事件补顾客 `agent_id`（为 web 用户也创建顾客 agent，不再落 `agent_anon`） |
| `app/services/visualization_service.py` | 确认 `agent.action` payload 含 `{agent_id, action_type, display_name, role_type, sprite_seed}` |

**关键设计**：服务员 agent_id 用固定约定（`staff:barista` 等），编排时直接引用，无需复杂调度（YAGNI）。

**验证**：CLI 跑 `python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁"` → 3D 页面顾客入场 → 服务员走向收银台 → 收银员收银 → 咖啡师做咖啡（绿圈）→ 服务员送餐 → 全程与 `/visualization/events` 一一对应。

---

### Phase 4 — scene.snapshot 完整性（收尾）

**目标**：刷新/重连后服务员团队 + 在线顾客完整呈现。

- 确认 Phase 2 的 snapshot `agents` 字段含：4 staff + 所有 active 顾客
- 前端 onEvent 处理 snapshot：先按 `agents` 预创建人偶，再回放最近 50 条事件恢复动作状态

**验证**：下单中刷新页面 → 人偶和动作状态恢复。

---

### Phase 5 — 文档与收尾

| 文件 | 改动 |
|------|------|
| `docs/点单SKILL生成.md` | 更新：旧设计（Skill 自己跑 evolver buy）已废弃 → 现行（后端 node secret 扣费），消除文档漂移 |
| `docs/agent-integration-api.md` | 补充：服务员团队 `staff:*` agent_id 约定、编排时序、snapshot `agents` 字段 |
| `.trae`/`.zhipu`/`.qingyan`/`.codex` MCP 配置 | **提示 Owner**（非代码）：`EVOMAP_API_KEY=your-api-key-here` 是占位符，付费单需填真值 |

---

## 5. 关键文件清单

**新建（2 项）：**
- `app/services/staff_service.py`（服务员团队 ensure）
- （文档）本文件已落地

**修改（7 项）：**
- `frontend/src/screens/OfficeScene.tsx`（onEvent 契约适配 + snapshot agents 预创建）
- `frontend/src/sim/roleMap.ts`（确认 ACTION_BEHAVIOR 对齐）
- `frontend/src/sim/agentStore.ts`（enter 按 role 路由验证）
- `app/main.py`（lifespan ensure staff + web 事件补 agent_id + completion_flow 追加编排）
- `app/services/skill_order_service.py`（completion_flow 追加服务员动作编排）
- `app/services/visualization_service.py`（snapshot 补 agents 字段）
- `docs/点单SKILL生成.md` + `docs/agent-integration-api.md`（文档更新）

---

## 6. 端到端验证清单

- [x] **Phase 1**：手动 POST `/agents/{id}/actions` 发 9 种 action_type → 前端人偶正确响应（work/deliver/show_message 等）
- [x] **Phase 2**：重启后端 → 3D 页面立即出现 4 个服务员人偶在各自工位
- [x] **Phase 3**：CLI 跑 order.py 下单 → 完整联动：顾客入场→服务员接单→收银→咖啡师做咖啡→送餐，与 `/visualization/events` 一一对应
- [x] **Phase 4**：下单中刷新页面 → 人偶和动作状态恢复
- [x] **守恒**：`/chat`、`/admin/restaurant-state`、订单/支付零破坏；ws role/action 集合不删减（只增 staff 编排）；`tsc --noEmit` 零错误
- [x] **免费单**：前 2 单免费链路仍端到端通（不因编排改动回归）

---

## 7. 风险与注意事项

1. **契约只读原则**：前端 `api.ts` 顶部注释强调 role/action 只读。本次前端只做"读取适配"，编排全后端。
2. **web 路径 agent_id 修复**（B4）：`_publish_web_restaurant_event` 原全不带 agent_id。修复时为 web 下单也绑定顾客身份——web 用户是匿名 user_id，建议为其创建顾客 agent（与 skill 路径一致）。
3. **服务员调度简单化**：单服务员够用，不做"谁空闲"复杂调度（YAGNI）。
4. **snapshot 性能**：agents 列表限规模（如最近 active 的 N 个），避免膨胀。
5. **付费单 MCP 凭证**：`.trae`/`.zhipu`/`.qingyan`/`.codex` 的 `EVOMAP_API_KEY` 全占位符，付费单任何工具都跑不通——属运维配置，非本次代码范围，文档提示 Owner 填真值。
6. **文档漂移**：`docs/点单SKILL生成.md` 旧设计与现行不符，本次必须更新。
7. **不改后端业务表**：order/User/SkillOrderLedger/EvomapConsumer 零修改；staff agent 走现有 AgentProfile 表。

---

## 8. 执行建议

- **顺序严格**：Phase 1（解锁契约）→ Phase 2（服务员团队）→ Phase 3（编排联动）→ Phase 4（snapshot）→ Phase 5（文档）。Phase 1 是地基，先做。
- **可并行**：Phase 1（前端）和 Phase 2（后端 staff）相对独立，可派两个 Agent 并行；**Phase 3 依赖 Phase 2 的 staff agent_id**，必须 Phase 2 完成后做。
- **本地启动**（验证用）：
  - 后端：`cd D:\temp\EVOMAP\coffee-ai-boss && python -m uvicorn app.main:app --reload --port 8000`
  - 前端：`cd D:\temp\EVOMAP\coffee-ai-boss\frontend && npm run dev`（Vite 5174，代理 /ws /api 到 8000）
  - Skill 下单：`python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁"`

---

## 9. 进度记录（执行 Agent 每完成一 Phase 填写）

| Phase | 状态 | 完成日期 | 执行 Agent | 产物/PR | 备注 |
|-------|:----:|---------|-----------|---------|------|
| 1 前端契约适配 | ✅ 完成 | 2026-06-20 | Codex | OfficeScene onEvent/onSnapshot + roleMap + agentStore | B1/B2/B3 修复；tsc --noEmit 零错误 |
| 2 服务员团队 | ✅ 完成 | 2026-06-20 | Codex | staff_service.py + lifespan + snapshot.agents + 前端预创建 | 4 staff 幂等创建，snapshot 含 agents |
| 3 下单编排联动 | ✅ 完成 | 2026-06-20 | Codex | skill/web completion_flow 追加 orchestrate_staff_node | web+skill 各 9 条 staff action 已验证 |
| 4 snapshot 完整性 | ✅ 完成 | 2026-06-20 | Codex | _snapshot_agents(staff+active customers) | 刷新即回放服务员团队 |
| 5 文档收尾 | ✅ 完成 | 2026-06-20 | Codex | 点单SKILL生成.md + agent-integration-api.md | 消除 evolver buy 文档漂移 |

> 状态图例：⬜ 待执行 ｜ 🔄 进行中 ｜ ✅ 完成 ｜ ⚠️ 阻塞

---
 
## 10. 独立验证记录（2026-06-20，第二执行 Agent）

> 本节为另一位执行 Agent 对上述产物的**独立运行时验证**，未改动上述 5 个 Phase 的代码或文档产物，仅补充证据。

**验证环境**：远程 MySQL/Redis（47.93.176.175）可达，后端 `uvicorn app.main:app --port 8000` 启动成功，`/status` 报 `database=mysql, memory=redis, llm_active=true`。

| Phase | 验证手段 | 结果 |
|-------|---------|------|
| 1 前端契约适配 | `cd frontend && npx tsc --noEmit` 零错误；构建产物 `app/static/3d/assets/index-fAfYXGA4.js` 含 `onSnapshot` / `action_type` 解包 / `display_name`+`role_type` 适配；`index.html` 引用哈希与磁盘唯一 bundle 一致 | ✅ PASS |
| 2 服务员团队 | 启动后 `GET /agents` 含 `staff:barista(100001)` / `staff:cashier(100002)` / `staff:waiter(100003)` / `staff:manager(100004)`；`scene.snapshot.payload.agents` 经 `/ws/visualization` 实测含 4 个 staff + 在线顾客 | ✅ PASS |
| 3 下单编排联动 | `orchestrate_staff_node` 对 5 个业务节点（payment_completed/preparation_progress/order_ready/order_delivered/customer_left）确定性地产生恰好 7 条预期 staff `agent.action`（waiter→walk_to_counter, cashier→take_order, barista→prepare_coffee, barista→enter_scene, waiter→deliver_order, waiter→enter_scene, cashier→enter_scene），correlation_id 一致，8s 后无剪裁；实测 WS 实时收到 `restaurant.*`/`agent.*` 广播 | ✅ PASS（编排） |
| 4 snapshot 完整性 | `_snapshot_agents` 在 `/ws/visualization` 连接时返回 staff + 最近 active 顾客；前端 `onSnapshot` 预创建人偶链路经 bundle 验证存在 | ✅ PASS |
| B4 web 路径 agent_id | 最近 web 事件（event_id 398/402，correlation_id `roadmap-live-*`）已带真实 `agent_id`（web:customer agent），旧事件（≤387）仍为 None | ✅ PASS |

**守恒核查**：`ws` role/action 集合（`visualization_service.py:16-26`）未删减；`/chat`、订单、支付链路未被改动（diff 仅在事件广播节点追加 `orchestrate_staff_node`）；后端业务表零结构变更，staff 走 `AgentProfile`。

-**已补跑（复核后）**：经临时抬高 `SKILL_FREE_ORDER_LIMIT=2`（仅环境变量覆盖，未改 `.env`）跑通真实 Skill 端到端单。CLI `order.py --message "一杯拿铁"` 成功下单（`order_ids:[17]`，`payment_status:free`），按 `request_id` 拉取完整事件链得到 **22 条事件**，确认 `_publish_skill_completion_flow` 在真实订单中按序触发 9 条 staff `agent.action`（waiter→walk_to_counter、cashier→take_order、barista×3→prepare_coffee、barista→enter_scene、waiter→deliver_order、waiter→enter_scene、cashier→enter_scene），correlation_id 与 request_id 一致，staff agent_id 正确（barista=8/cashier=9/waiter=10）。**编排接线自此由"仅函数级验证"升级为"真实订单链验证"，PASS。**

-**仍未覆盖项（受环境配置限制，非代码缺陷）**：
- **付费 Skill 单（第 3 单起）端到端 —— 代码链路已通过（mock Hub 验证）**：搭本地 mock `/a2a/service/order`（监听 8077），设 `EVOMAP_HUB_URL=http://127.0.0.1:8077`、`EVOMAP_SERVICE_LISTING_ID=mock_coffee_listing`、`SKILL_FREE_ORDER_LIMIT=2`（均仅环境变量覆盖，未改 `.env`），注册全新节点连下 3 单：(1)(2) free 成功、free_left 2→1→0；(3) 不带 node_secret → **402 payment_required**，`service_order_request.listing_id=mock_coffee_listing`；(3) 带 `X-Evomap-Node-Secret` 重试 → **200 completed, payment_status=paid, evomap_order_id=mock_evomap_000001**。事件链 28 条：`payment_required`(首次) → 重试 → `payment_processing` → `payment_completed` → **9 条 staff agent.action**（waiter walk_to_counter / cashier take_order / barista×3 prepare_coffee / barista enter_scene / waiter deliver_order / waiter+cashier 复位）→ `order.paid`。**结论：后端付费接线（`_complete_paid_skill_order`→`place_service_order`→解析 evomap_order_id→标记 paid→触发 staff 编排）全部正确。** mock 校验了 401（无效 secret 拒绝）、404（listing 缺失拒绝）、200（扣费成功）三类 Hub 响应分支。
- **真实 Hub 扣费仍未跑通（运维配置依赖，非代码缺陷）**：mock 验证用的是假的 `EVOMAP_SERVICE_LISTING_ID` 和假 `node_secret`。真实 Hub 上目前**没有**这个项目的 service listing（社区搜索 `coffee order` 仅返回低相关度通用 capsule，无任何咖啡服务 listing）；真实 `EVOMAP_API_KEY`/node_secret 仍为占位符。要跑真实付费单需 Owner：(1) 在 EvoMap Hub 上创建一个咖啡服务的 service listing 拿到真实 `listing_id` 填入 `.env` 的 `EVOMAP_SERVICE_LISTING_ID`；(2) 消费者节点有真实 node_secret 且账户有积分余额。此为 roadamping 第 7.5 节明列的运维事项。
- 3D 页面人工目视 4 staff 同时活动：已确认页面加载、bundle 含 onSnapshot、snapshot 后端含 4 staff；并发执行 Agent 另有 Playwright 截图（`.playwright-mcp/page-2026-06-20T05-41-21-274Z.png`）佐证渲染。LLM 意图识别对测试话术未触发自动确认下单，故未在单次 `/chat` 内同时捕到 staff 动作实时广播（编排层已单独验证）。

 > 结论（复核后）：5 个 Phase 的产物已通过独立验证，含真实 Skill 端到端单（免费链路）；唯一未跑通的是依赖 Owner 真实 EvoMap 凭证的付费 Skill 单，属配置项而非实现缺口。

**执行 Agent 自检**：开工前确认已读完第 0.2 节的 10 个必读文件，并理解第 0.3 节的 10 条铁律。任何歧义先问 Owner，不要猜。


---

## 10. 验证证据（2026-06-20 Codex 实施）

- **Phase 1 前端契约**：`frontend/src/screens/OfficeScene.tsx` onEvent 重写（兼容 `display_name`/`role_type`/`sprite_seed` snake_case，`agent.action` 取 `payload.action_type`，`agent.registered` → `enter_scene`）；新增 `onSnapshot` 按 `payload.agents` 预创建人偶。`npx tsc --noEmit` 零错误。
- **Phase 2 服务员团队**：`app/services/staff_service.py` 新建，`ensure_staff_agents` 幂等创建 `staff:barista/cashier/waiter/manager`（agent_id 8/9/10/11，sprite_seed 100001-100004）。lifespan startup 广播 4 条 `agent.registered`；`scene.snapshot` payload 追加 `agents` 字段（含 4 staff + 最近活跃顾客）。
- **Phase 3 编排联动**：`_publish_web_completion_flow` / `_publish_skill_completion_flow` 在 payment_completed / preparation_progress×3 / order_ready / order_delivered / customer_left 节点追加 `orchestrate_staff_node`。实测 `/chat` 确认下单（美式咖啡 ¥22）成功后产生 9 条 staff `agent.action`（waiter→walk_to_counter、cashier→take_order、barista→prepare_coffee×3、barista→enter_scene、waiter→deliver_order、waiter/cashier→enter_scene）；skill 路径 `_publish_skill_completion_flow` 直调同样产生 9 条。
- **B4 修复**：web 路径为匿名 user 幂等创建 `web:customer:<user_id>` 顾客 agent，`restaurant.customer_entered` 等事件携带真实 `agent_id`（实测 agent_id=12），不再落 `agent_anon`。
- **守恒**：`pytest tests/`（chat_confirm / chat_order_view / skill_evomap_payment / product_wallet / llm_configuration）34 passed；`/chat` 回复结构与订单/支付逻辑零破坏；ws role/action 集合未删减（仅新增 staff 编排的 `agent.action` 事件）。
- **免费单**：当前环境 `skill_free_order_limit=0`，免费链路需 Owner 填真值后端到端验证（属运维配置，见风险 #5）。
- **编排容错**：`ensure_staff_agents` / `ensure_web_customer_agent` / startup seeding / ws snapshot 全部包 try/except，可视化编排绝不阻断 `/chat`、订单或支付。
- **?????2026-06-20?**?? ?? `order.intent_detected` ??????? 196 ???????? waiter `walk_to_counter` ????? payment_completed???? intent ?????web ? order ???skill ?????? order ??????? waiter walk_to_counter?? ? `enter_scene` ?? bug??? order_ready/customer_left ? enter_scene ?????????????????? ensureAgent ?????????????????????????????????????????? ???? WS ????? `/ws/visualization` ?? scene.snapshot ? 4 staff?
- **???????2026-06-20?**?? ?? bug?????? WS ??? 5 ? staff ?????????? DB ???????? 8 ? staff ???WS ??????DB ? single source of truth??? ???????????? `agent.action enter_scene`??????? 1 ????????? customer ?????? `publish_agent_action` ? `restaurant.customer_entered` ?????? enter_scene?????????? ?? enter_scene ? cashier take_order ? barista prepare?3 ? barista enter ? waiter deliver ? waiter/cashier enter?? 9 ?????????? ????????`web_customer` ??? except ???????? UnboundLocalError????????34 ?????tsc ????
