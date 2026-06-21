[根目录](../CLAUDE.md) > **frontend** (3D 前端)

# frontend/ — 3D 咖啡厅 + 监控大屏

## 变更记录 (Changelog)

| 时间 | 动作 | 说明 |
|------|------|------|
| 2026-06-21 08:40 | 增量 | **顾客进场统一入口 + 3D 内嵌聊天面板 + 专项测试**（对应"全部修复"②③④⑦）。① 后端 `staff_service.customer_enter_scene`：新建统一进场函数（刷 `last_seen_at` + 广播 `enter_scene`），web `/chat` 与 skill `/skill/orders` 两处去重内联 try/except 改调它（消除"在线显示模型/点单链路"架构断层）。② web 事件全链路归属顾客：`_publish_web_restaurant_event`/`_publish_web_completion_flow` 加 `agent_id` 透传，`chat()` 内 6 处调用统一带 `customer_agent_id`。③ **前端 3D 内嵌聊天 UI**（`ui/ChatPanel.tsx`）：左下角浮动面板，`getAnonUserId`（localStorage 稳定匿名 user_id）→ `sendChat` POST `/chat`，接入 `OfficeScene.tsx`；此前"内嵌聊天消费 /chat"仅文档规划、无代码，本版补齐（`net/api.ts` 加 `sendChat`/`getAnonUserId`/`ChatResponse`）。④ 专项测试 `tests/test_customer_enter_scene.py`（2 用例）。**注**：前端本地构建需先 `npm install`（当前 node_modules 缺 typescript/vite，无法 tsc/vite 验证，代码已人工审查） |
| 2026-06-21 08:10 | 增量刷新（第八次 init） | **Dashboard 事件中文化 + 背景音乐多轨轮播 + 顾客人偶进 3D 场景修复 + three-stdlib**。① **Dashboard 事件中文化**（`Dashboard.tsx`）：新增 `EVENT_TEXT`/`SOURCE_TEXT`/`AGENT_ACTION_TEXT` 三个映射表，把英文事件 type/source/action_type 翻译成中文（如 `restaurant.payment_completed`→支付完成，`agent.action` 取 `payload.action_type` 翻译）；新增 `summary` 字段兼容（KPI 卡片优先取 `summary.today_order_count`/`active_staff_count`/`active_consumer_count`）；`formatEvent`/`sourceText` 辅助函数。② **背景音乐多轨轮播**（`sceneMusic.ts`，`031608f`）：从单 m1 升级为 m1/m2 多轨循环轮播切换；后端 `/3d/sounds` mount 恢复（`031608f`，修生产模式 mp3 被 SPA fallback 返回 HTML）。③ **顾客人偶进 3D 场景修复**（`d54f8be`/`6ce1d49`）：web/skill 点单链路正确广播 `enter_scene`，顾客人偶正常进入 3D 场景（修此前 ccg 任务「顾客人偶不进入 3D 场景」）。④ 新增依赖 `three-stdlib ^2.36.1`。⑤ `OfficeScene.tsx` 背景音乐接入调整。**注**：前端 3D 不渲染 products 卡片（卡片在 2D 聊天页 `app/static/index.html`）；`overlays/ImmersiveOverlay.tsx` 存在但 `App.tsx` 未引用 |
| 2026-06-21 01:47 | 增量刷新 | **TopBar 重合修复 + 3D 场景背景音乐**。① **TopBar（`App.tsx`）重合修复**：原 `/scene` 下 `opacity:0.45` + 整层 `pointerEvents:none` 致文字与 3D 场景（吧台/大厅）重合难读、链接/登出点不到，且 `sceneRoute` 用 `window.location` 检测不随路由更新；改统一样式——容器加半透明深色面板（`rgba(12,18,28,0.72)`）+ `blur(6px)` 毛玻璃 + `pointerEvents:none`（穿透不挡 3D 拖拽），各交互子元素（链接/按钮/用户名）`pointerEvents:auto` 恢复可点；去掉 sceneRoute 分支与 opacity:0.45。② **3D 场景背景音乐**：新建 `sounds/sceneMusic.ts`（单例 `HTMLAudioElement`，loop、volume 0.4，首次 `pointerdown`/`keydown` 后 `play()` 规避浏览器 autoplay 限制、失败自动重试；`toggleMute`+subscribe/notify；卸载暂停/重挂恢复）；`OfficeScene.tsx` `useEffect` 挂载 `initSceneMusic`/`stopSceneMusic`；TopBar 加 🔊/🔇 静音按钮（订阅 mute 状态）；音频源 `docs/m1.mp3` 复制到 `public/sounds/m1.mp3`，运行时 URL：dev `/sounds/m1.mp3`、prod `/3d/sounds/m1.mp3`（需后端挂载 `/3d/sounds`，见 app/CLAUDE.md）。③ **snapshot.agents 真正含在线用户**（依赖后端在线用户模型）：`onSnapshot` 现能收到 4 服务员 + 在线顾客，刷新页面也看得到。详见「TopBar」「背景音乐」小节 |
| 2026-06-20 21:30 | 增量刷新 | **匿名点单门槛确立（前端侧）**（仅文档刷新，不改源码）。对齐后端 `main.py:1696` `index()` 删登录校验：根路由 `/`（经 FastAPI）匿名直出 3D SPA，**前端 3D 场景无任何强制登录拦截**。确认 `App.tsx` 路由 `/` `/scene` `/machines` `/dashboard` 均**无 `<ProtectedRoute>` 守卫**，`/login` `/register` 为可选；`TopBar` 未登录时仅显示"登录"按钮（不阻断浏览/点单）。`LoginPage` 提供"匿名进入 3D"链接。内嵌聊天消费后端 `POST /chat`（匿名 user_id，无 auth）。设计动因：咖啡厅线下场景，顾客匿名消费不该有账号密码门槛。清除"账户登录访问受保护页面"过时措辞（实际无受保护页面）。详见「模块职责 #4」「账户登录」「FAQ」 |
| 2026-06-20 | 编辑器完整度对齐 | **3D 编辑器与 Claw3D 完整度对齐**（修"编辑后不生效"）：① **P0 autosave**：`OfficeScene` 加 debounced(300ms) autosave effect，删 6 处手动 `saveFurniture`（键盘移动/旋转/抬升原先漏存→刷新丢失的根因）；② **P1 操作封装**：移植 Claw3D `updateSelectedItem/moveSelectedItem/rotateSelectedItem`（键盘+面板共用），带 `snap()` 吸附+`normalizeDegrees()` 规范化+elevation `[-0.4,2.5]`；③ **P1 可视化面板**：新建 `ui/SelectedObjectPanel.tsx`（Move 3×3 方向网格+Rotate ±15°+实时 rot/lift+关闭✕+删除/恢复默认），取代原纯文字提示面板；④ **P2**：选中面板关闭按钮、恢复默认 `window.confirm` 防误触；⑤ **Machine 编辑盲区修复**：`coffee_machine/atm/vending/jukebox`（走 `resolveMachine` 分支）编辑模式下 onClick 改走 `handleFurniturePointerDown`，现可选中/跟鼠标移动/编辑/删除（原 editMode 下点选无反应）；⑥ 清理死代码：删未用 `debug` state + FurnitureModel 的 coffee_machine 死特判。构建通过(tsc+vite)。详见 `docs/3D编辑器完整度对齐.md` |
| 2026-06-20 19:07 | 增量刷新 | **服务员团队编排的前端契约适配**（外部 commit "服务员团队编排/staff 智能模型"）：① **App.tsx 导航修正**：TopBar 链接 "3D 办公室"→"3D 咖啡厅"（漏改已修）。② **新增路由 `/machines`** → `MachineShowcase`（咖啡机展示页，独立 Canvas + `CoffeeMachinePreviewCluster`，路由段补全）。③ **OfficeScene.tsx onEvent 重写**（修 B1/B2/B3 契约错配）：`agent.action` 事件取 `payload.action_type` 作 action（外层 type 永远是 `agent.action`，真动作在 payload）；兼容 snake_case（`name = payload.display_name ?? payload.name`、`role = payload.role_type ?? payload.role`、`spriteSeed = payload.sprite_seed ?? payload.spriteSeed`）；`agent.registered` 事件转 `enter` 语义让人偶入座。④ **新增 onSnapshot 回调**：收 `scene.snapshot` 时遍历 `payload.agents`（4 staff + 活跃顾客，后端 2026-06-20 新增）预创建人偶，后连接/刷新页面也能看到服务员团队。⑤ **agentStore.ts `enter` 分支增强**：返回的服务员（re-enter/reset）从当前位置 routeTo 到工位，不再 teleport 跳变（isNew 才从 ENTRY_POINT 出生）。⑥ **roleMap.ts `waiter` 工位 y700→660 微调**（与后端 staff_service 工位表对齐）。详见「事件 → 渲染管线」「角色映射」「sim 层」小节 |
| 2026-06-20 | 收尾修复+素材接入 | **移植残留清理 + cafe-extras 素材接入**：① roleMap 坐标超界真 bug 修复（`customer` y1080→580、`ENTRY/EXIT` y900→360，超出 `CANVAS_H=720`，从 Claw3D 1800×1800 抄来没适配；寻路目标曾塌缩到画布底边）+ 注释 1800x1800→1800x720；② 清理移植残留死代码（navigation `void ITEM_FOOTPRINT/snap`、agentStore `void NAV_ENTRY`、OfficeScene `roleDeskIndex`/`DESK_LOCS`/`ROLE_DESK`/`getDeskLocations` 整套 void 占位、main.py unused import `bridge_event_to_colyseus`、furnitureDefaults `void nextUid`）；③ **咖啡杯接入（曲折）**：先试 cafe-extras CC0 素材（ppCoffeeCup/ppEspresso），读 GLB bbox 发现俩模型原始尺寸差 3.5 万倍（ppCoffeeCup~3mm、ppEspresso~104m），任何单一 FURNITURE_SCALE 都调不对 → **弃用 PP 素材，改 `CupProp` 程序化画杯**（cylinder 杯身+咖啡液面：`coffee_cup` r4cm×h9cm 白陶瓷、`espresso` r2.8cm×h6cm 小杯）；elevation 按桌面高度（圆桌 0.31m、吧台 0.69m）；ppCoffeeMachine 保留二期储备（主线 kitchenCoffeeMachine 已在用） |
| 2026-06-20 11:10 | 场景改造 | **office→咖啡厅**：① 修天气系统变暗 bug（`cameraLighting` 的 `DayNightCycle` 昼夜循环→`SceneLighting` 固定明亮白天：hemisphereLight 0.6+ambient 1.1+sun 1.8，根因是原 6 关键帧含 2 暗帧 sunIntensity 0.2-0.3 + 300s 周期）；② 重写 `furnitureDefaults` 为咖啡厅布局（吧台区 executive_desk+coffee_machine+3 高脚椅 / 客座区 4 组 round_table+chair 2×2 / 休闲区 couch+2 beanbag+单人椅 / 墙面 whiteboard 菜单板+bookshelf+lamp+plant）；③ `environment` 墙色 #8d6e63→#795548 暖棕、emissive 0.4→0.5；④ `furniture` FURNITURE_TINT 转暖咖啡色；⑤ `OfficeScene` 切 SceneLighting + 文案"3D 咖啡厅"；⑥ 下载 3 个 CC0 GLB 到 `cafe-extras/` 储备 |
| 2026-06-20 10:05 | 增量对齐 | 第三次 init：精读 `screens/Dashboard.tsx` 全文，补全监控大屏布局（4 卡片 KPI + 最近订单 + 实时事件流）与 4s 轮询细节（`getRestaurantState` + `listEvents(30)` 双拉，事件流优先用本地 events 回退 `state.recent_events`）；同步根文档"唯一活跃 UI"定性 |
| 2026-06-20 | 增量补扫 | 第二次 init：逐一精读 office3d/ 子模块（navigation/geometry/constants/agents/furniture/cameraLighting/sceneRuntime/environment/avatars）、sim/tick.ts 全文、auth/AuthPages.tsx 全文，补全坐标投影/A\*寻路/昼夜循环/Agent骨骼动画/表单实现细节 |
| 2026-06-20 | 创建 | 初始化架构师首次生成 |

---

## 模块职责

Coffee AI Boss 的 3D 可视化前端（**取代** 2D 像素风，与后端 `/ws/visualization` 事件流对接）。**2026-06-20 09:40 起，本模块是项目唯一活跃 UI**（像素 Colyseus 方案与独立 2D 对话页均已移出活跃仓库，归档位置见 `docs/archive-manifest.md`），后端根路由 `/` 已改为直出本前端构建产物。四大职责：
1. **3D 咖啡厅场景**（`/3d/scene`）：用 React-Three-Fiber 渲染带真实 GLB 家具的咖啡厅（吧台/客座圆桌/沙发豆袋休闲区，2026-06-20 从办公室改造），Agent（**4 个固有服务员 barista/cashier/waiter/manager + 动态顾客**，2026-06-20 新增服务员团队）按可视化事件驱动行走、工作、说话。内嵌聊天消费后端 `POST /chat`（匿名 user_id，无登录门槛）。
2. **监控大屏**（`/3d/dashboard`）：聚合 `/admin/restaurant-state`，展示今日订单/金额/来源分布/最近订单/事件流/在线员工。
3. **咖啡机展示**（`/3d/machines`）：独立 Canvas 展示咖啡机模型簇（`CoffeeMachinePreviewCluster`，2026-06-20 新增）。
4. **账户登录（可选增值）**（`/3d/login`、`/3d/register`）：通过签名 Cookie 会话提供个性化昵称 + WS 在线顾客人偶 presence。**2026-06-20 21:30 起，3D 场景无任何强制登录拦截**——所有路由（`/` `/scene` `/machines` `/dashboard`）匿名可访问，登录是增值而非点单前置。

> 来源标注：`office3d/` 与 `avatars/` 全套从 **Claw3D retro-office** 移植（文件头均注明 "Ported/Adapted from Claw3D"），去掉了 Claw3D 特有的 janitor/gym/qa/pingpong/district 逻辑，保留监控视图所需的最小子集。

## 入口与启动

- **入口**：`src/main.tsx` → `src/App.tsx`（`<BrowserRouter basename="/3d">`）
- **TopBar 导航**（`App.tsx`）：固定右上角浮层，链接 `3D 咖啡厅`（→`/scene`）、`大屏`（→`/dashboard`）+ 登录/登出/用户名；在 `/scene` 路由下 `pointerEvents:none` + opacity 0.45 半透明，避免遮挡 3D 交互（2026-06-20 已把链接文案从"3D 办公室"修正为"3D 咖啡厅"）。**未登录时仅显示"登录"按钮，不阻断浏览/点单**。
- **路由**（react-router-dom 7，**无 `<ProtectedRoute>` 守卫，全部匿名可访问**）：
  - `/` → 重定向到 `/scene`
  - `/scene` → `OfficeScene`（匿名可访问，内嵌聊天消费 `/chat`）
  - `/machines` → `MachineShowcase`（咖啡机展示，2026-06-20 新增）
  - `/dashboard` → `Dashboard`
  - `/login`、`/register` → 登录/注册页（可选）
- **开发**：`npm run dev`（Vite，端口 5174，代理 `/ws` `/api` 到 `localhost:8000`）
- **构建**：`npm run build`（`tsc --noEmit && vite build`，产物输出到 `../app/static/3d`，由 FastAPI `/3d` 与根 `/` 托管）
- **base path**：`/3d/`（见 `vite.config.ts`）

## 对外接口（与后端的契约）

通过 `src/net/api.ts` 和 `src/net/visualizationSocket.ts` 调用后端：
- `getJson` / `postJson` — 通用 fetch 封装（带 `credentials: "include"` 传 Cookie）
- `listEvents(limit)` → GET `/visualization/events`
- `getRestaurantState()` → GET `/admin/restaurant-state`
- `connectVisualization({onEvent, onSnapshot, onStatus})` → WS `/ws/visualization`，连接即收 `scene.snapshot`（**payload 含 `agents` 字段：4 staff + 活跃顾客，2026-06-20 新增**，由 `onSnapshot` 预创建人偶），之后实时收单条事件；断线 2 秒自动重连

> **契约约束**（`api.ts` 顶部注释）：后端事件结构、role、action 是只读契约，前端不改；改后端需同步前端 `roleMap.ts`。前端只做"读取适配"——兼容 snake_case payload、识别 `agent.action` 外壳取 `payload.action_type`，**不改契约语义**，编排逻辑全在后端。

## 关键依赖与配置

- **React 19.2** + **react-router-dom 7**
- **@react-three/fiber 9** + **@react-three/drei 10**（`useGLTF`、`Billboard`、`Text`、`OrbitControls`）+ **three 0.183**（3D 渲染）
- **three-stdlib 2.36**（three.js 标准库扩展，辅助 GLB 加载/控制器等，2026-06-21 新增）
- **Vite 6** + **@vitejs/plugin-react**
- **TypeScript 5.6**（strict）
- **Playwright 1.61**（devDependency，E2E；临时截图证据不保留在活跃仓库，历史证据见 archive manifest）
- 构建产物 `app/static/3d/office-assets/` 含家具 GLB 模型与背景贴图

## 数据模型（前端运行时状态）

- **`VisEvent`**（`api.ts`）：`{event_id, type, agent_id, payload, correlation_id, created_at}`
- **`OfficeAgent`** / **`RenderAgent`** / **`FurnitureItem`**（`office3d/core/types.ts`）：
  - `OfficeAgent.status`: `"working" | "idle" | "error"`
  - `RenderAgent` 在 `OfficeAgent` 基础上扩展运行时字段：`x,y`（画布坐标）、`path`（A\* 路径点数组）、`facing`（朝向弧度）、`frame`（动画帧计数）、`walkSpeed`、`phaseOffset`（基于 spriteSeed，错峰动画）、`state`（`walking/sitting/standing/away/working_out/dancing`）、`targetX/targetY`、`awayUntil`、`bumpedUntil`、`lastSeenAt`、`danceUntil` 等
  - `FurnitureItem`：`{_uid, type, x, y, w?, h?, r?, color?, facing?, vertical?, elevation?}`
- **`AgentAvatarProfile`**（`office3d/avatars/profile.ts`）：确定性头像档案（version 1，含 skinTone/hair/clothing/accessories/glasses/headset/hat/backpack），由 seed 字符串经 FNV-1a 哈希确定性派生
- **`SimHandle`**（`sim/agentStore.ts`）：`{agents, furniture, speech, rebuildNav, setFurniture, _nav}` — 事件驱动 + tick 推进的状态机
- **`Account`**（`auth/AuthProvider.tsx`）：`{user_id, username, nickname}`（可选，未登录时为 null）
- **大屏 `State`**（`screens/Dashboard.tsx`）：`{today:{order_count,total_amount,active_agent_count,active_consumer_count}, by_source:[{source_type,count,amount}], recent_orders:[{order_id,coffee_name,amount,status,source_type,created_at}], recent_events:VisEvent[], agents:[{display_name,role_type,status}]}`

## 核心架构

### 事件 → 渲染管线（`OfficeScene.tsx`）
```
/ws/visualization 事件 → sim/agentStore.applyEvent (推入意图)
                       → sim/tick.makeTick (A* 寻路推进移动)
                       → office3d/objects/agents.AgentModel (渲染)
scene.snapshot (连接即收) → onSnapshot: 遍历 payload.agents 预创建人偶 (4 staff + 顾客)
```
`OfficeScene` 用 `materializeDefaults()` 生成咖啡厅布局（吧台+客座+休闲，2026-06-20 从 Claw3D 办公室改造），`createSimStore().setFurniture()` 同时构建 nav grid；`GameLoop`（`useFrame`）每帧调用 `tick()`；事件经 `applyEvent` 转成行为意图（enter/walk_to_counter/work/deliver/...），`SpotlightEffect` 高亮被点击的 Agent。

**onEvent 契约适配**（2026-06-20 重写，修 B1/B2/B3）：
- **字段适配**（兼容后端 snake_case）：`name = payload.display_name ?? payload.name`、`role = payload.role_type ?? payload.role`、`spriteSeed = payload.sprite_seed ?? payload.spriteSeed`。
- **事件分发**：
  - `event.type === "agent.action"` → action = `payload.action_type`（外层 type 永远是 `agent.action`，真动作在 payload——这是修 B1 的关键）。
  - `event.type === "agent.registered"` → 转 `enter` 语义让人偶入座对应工位（startup 广播的 4 条 staff `agent.registered` 由此预创建服务员）。
- **onSnapshot**（2026-06-20 新增）：收 `scene.snapshot` 时遍历 `payload.agents`，按 `{agent_id, display_name, role_type, sprite_seed}` 预创建人偶（`name: a.display_name || "?? "+a.agent_id`），保证后连接/刷新页面也能看到服务员团队。

### 角色映射（`sim/roleMap.ts`）— 后端契约镜像
- `ROLE_DESK`（画布像素坐标，`CANVAS_W=1800/CANVAS_H=720`；2026-06-20 已修复坐标超界 + waiter 微调）：
  - `barista` {360,540}、`cashier` {620,320}、`waiter` {880,**660**}（原 700，2026-06-20 微调对齐后端 staff 工位表）、`manager` {1180,320}、`customer` {880,**580**}（原 1080 超出画布，已修）
  - `ENTRY_POINT` {60,**360**}（左侧入口，原 y900 超界已修）、`EXIT_POINT` {60,**360**, facing -π/2}
  - 全部 `facing` 默认 `Math.PI`（朝向画面，customer 例外 facing 0）
- `ROLE_COLOR` / `ROLE_LABEL`：颜色与中文名（咖啡师/收银员/服务员/主管/访客）
- `ACTION_BEHAVIOR`：后端 `action_type` → 前端行为
  - `enter_scene→enter`、`walk_to_counter→walk_to_counter`、`walk_to_table→walk_to_table`
  - `take_order→work`、`prepare_coffee→work`、`deliver_order→deliver`
  - `show_message→show_message`、`leave_scene→leave`、`error→error`
  - 未知 action 兜底 → `walk_to_table`
- `resolveRole`：未知 role 兜底为 `customer`；`resolveAction`：未知 action 兜底 `walk_to_table`。

### sim 层
- **`sim/agentStore.ts`** — 事件意图状态机：
  - `ensureAgent`：按 `meta.id` 复用或创建 agent（初始坐标=ENTRY_POINT，status=idle，state=standing，phaseOffset 由 spriteSeed%100）
  - `routeTo`：用 `astar()` 计算路径写入 `agent.path`，置 `state=walking`
  - `applyEvent`：按 behavior 分派——`enter`（**2026-06-20 增强**：isNew 才从 ENTRY_POINT 出生；返回的服务员 re-enter 从当前位置 routeTo 到工位，不再 teleport 跳变）；`walk_to_counter` 走到收银桌；`work` 距桌>60 先寻路再 status=working；`show_message` 写入 `speech` Map（6 秒后由 OfficeScene 清除）；`leave` 走向 EXIT_POINT；`error` 置 status=error
  - `triggerDance`：程序化舞蹈触发（非后端 action，Phase 6 UI/社交互动用），设 `danceUntil` 窗口，tick 翻 `state=dancing`
- **`sim/tick.ts`** — 每帧推进（A\* 寻路推进逻辑）：
  - `moveAlongPath`：每帧 `frame++`，取 `path[0]` 作为下一个航点；距离 < `ARRIVAL_THRESHOLD=4` 则 shift 航点；否则按 `WALK_SPEED*60` 步长线性推进，`facing=atan2(dx,dy)`，`state=walking`
  - `makeTick`：路径走完后按"距桌位<50"判定坐下（working→sitting/standing），arrival 或 walking→standing
  - 注意：`WALK_SPEED=0.3`（constants），步长=18 像素/帧 @60fps；不做对角线提速或避障重规划（去掉了 Claw3D 的 bump/separation 完整逻辑，相关字段保留但未在 tick 中使用）

### office3d 层（详细）
- **`core/constants.ts`** — 坐标系常量：
  - 画布 `CANVAS_W=1800` × `CANVAS_H=720`，`SCALE=0.018`（画布像素→three.js 世界单位），`WORLD_W/H = CANVAS*SCALE`
  - 移动/动画：`WALK_SPEED=0.3`、`WALK_ANIM_SPEED=0.15`、`AGENT_SCALE=1.75`、`AGENT_RADIUS=20`、`SEPARATION_STRENGTH=3`、`BUMP_FREEZE_MS=1500`
  - 建模：`SNAP_GRID=10`、`WALL_THICKNESS=8`、`ELEVATION_STEP=0.08`、`DESK_STICKY_MS=10000`
  - 概览相机：`DISTRICT_CAMERA_POSITION=[14,16,18]`、`TARGET=[0,0,1]`、`ZOOM=34`（3/4 透视，非俯视）
- **`core/geometry.ts`** — 画布→世界投影与家具几何：
  - `toWorld(cx,cy) → [cx*SCALE - CANVAS_W*SCALE*0.5, 0, cy*SCALE - CANVAS_H*SCALE*0.5]`（画布中心对齐世界原点，y=0 地平面）
  - `ITEM_FOOTPRINT`：每种家具类型的 `[width,height]` 基础尺寸（desk_cubicle 100×55、round_table 120×120、couch 100×40 等）
  - `ITEM_METADATA`：每种家具是否阻塞寻路（`blocksNavigation`）+ `navPadding`（默认 `GRID_CELL*0.6`）
  - `getItemBounds`：考虑 `facing` 旋转后的轴对齐包围盒（用于 nav grid 标记）
  - `createWallItem`：由两端点生成水平/垂直墙
- **`core/navigation.ts`** — **A\* 寻路核心**（自包含，25px 网格）：
  - `GRID_CELL=25`，`GRID_COLS=ceil(CANVAS_W/25)=72`，`GRID_ROWS=ceil(CANVAS_H/25)=29`（共 2088 格）
  - `buildNavGrid`：遍历家具，对 `blocksNavigation=true` 的项按 `getItemBounds+navPadding` 标记阻塞格；四周边界格强制阻塞（防出界）
  - `astar(sx,sy,ex,ey,grid)`：8 方向 A\*（含对角线，对角 cost=1.414）；手写二叉堆优先队列（`pushOpen/popOpen`）；**拐角裁剪修正**（对角移动时检查两个正交邻格是否阻塞，避免穿墙角）；`findFree` 螺旋搜索起/终点的最近空闲格（防起终点卡在家具内）；返回画布像素坐标路径点数组，终点精确到目标像素
  - `getDeskLocations`：筛选 `desk_cubicle`，返回 `{x+40, y-5}` 桌前定位点
  - `ENTRY_POINT={x:80,y:360,facing:π/2}`（注意：agentStore 实际用的是 roleMap 的 ENTRY_POINT {60,360}，这里的 navigation.ENTRY_POINT 是另一处常量——两处入口常量曾不一致属移植残留，现已统一到画布内 y=360）
  - `ROAM_POINTS`：7 个漫游点（未在当前 tick 中使用，预留）
- **`core/furnitureDefaults.ts`** — **咖啡厅布局**（2026-06-20 从 Claw3D 办公室改造）：吧台区（executive_desk L 吧台 + coffee_machine + computer 收银 + cabinet 后柜 + fridge + 3 chair 高脚椅）/ 客座区（4 组 round_table r:55 + 每组 4 chair，2×2 错落）/ 休闲区（couch 长沙发 + table_rect 茶几 + 2 beanbag 红蓝豆袋 + couch_v 单人椅）/ 墙面装饰（3 whiteboard 菜单板 + bookshelf 展示柜 + clock + 3 lamp 落地灯 + 6 plant + 3 trash）；`materializeDefaults()` 返回 `FurnitureItem[]`
- **`scene/environment.tsx`** — `FloorAndWalls`：三层地板（深色底+中等色+米色面 `#c8a97e` 咖啡馆木地板感）+ 18 条地板纹线 + 四面墙（`wallColor=#795548` 暖棕，`emissiveIntensity=0.5`）
- **`systems/cameraLighting.tsx`**：
  - `SceneLighting`：**固定明亮白天灯光**（2026-06-20 改造；原 `DayNightCycle` 昼夜循环因 6 关键帧含 2 暗帧 sunIntensity 0.2-0.3 + 300s 周期被用户反馈"又暗又快"而整体移除）；`hemisphereLight`（天地环境光 intensity 0.6，治角落暗）+ `ambientLight`（intensity 1.1, color #f4e8d0）+ `directionalLight`（intensity 1.8, color #fff4e0，带阴影 mapSize 1024, shadow-bias -0.0002）
  - `OVERVIEW_CAMERA/TARGET/ZOOM` 复用 `DISTRICT_CAMERA_*` 常量
- **`systems/sceneRuntime.tsx`**：
  - `GameLoop`：`useFrame(() => tick())`，纯驱动器
  - `SpotlightEffect`：跟随指定 `agentId` 的聚光灯，淡入 0.4s/淡出 0.6s，强度按 `sin(progress*π)` 钟形曲线（最高 6），用 `toWorld` 把灯和 target 投到 agent 当前世界坐标
- **`objects/furniture.tsx`** — GLB 家具渲染：
  - `FURNITURE_GLB`：每种家具类型→`/3d/office-assets/models/furniture/*.glb`（desk/deskCorner/chairDesk/tableRound/loungeSofa/...）
  - `FURNITURE_SCALE` / `FURNITURE_Y_OFFSET` / `FURNITURE_TINT`：每类型专属缩放、Y 偏移（computer 抬高 0.61）、染色（lerp 0.8 到 MeshStandardMaterial，roughness 0.65/metalness 0.08）
  - `SHADOW_CASTING`：仅大件家具（桌/沙发/书架/柜/冰箱）投射阴影
  - `resolveTemplate`：按 `glbPath:type:color` 缓存克隆的模板（避免重复解析 GLB）；`FurnitureModel` 用三层 group 实现绕家具中心旋转+缩放
- **`objects/agents.tsx`** — **盒状人偶 AgentModel**（核心渲染，~690 行）：
  - 由 `RenderAgent` ref 驱动每帧姿态：`groupRef.position.lerp(toWorld(x,y), 0.15)` 平滑跟随；`rotation.y` 朝 `facing`（0.12 系数缓动，处理 ±π 回绕）
  - 走路动画：`walkPhase=sin(frame*WALK_ANIM_SPEED)`，手臂 ±0.4、腿 ±0.35 摆动，身体 bounce 0.04
  - 状态驱动表情（眼/眉/嘴/嘴角）：
    - working：眯眼（0.48-0.84）、皱眉、小嘴、绿色脉冲环、绿色状态点
    - error：红眼（0.28）、怒眉、扁嘴、红色脉冲环（更大更不透明）、红色状态点
    - standing：正常眼+微笑嘴角+呼吸起伏 0.01
    - away：半透明（opacity 0.45）+ "z z z" 气泡
  - 眨眼：基于 `agentId` 字符码哈希做 seed，按 `blinkCycle`（idle 240/error 120/working 170/away 180）随机眨眼
  - 名牌 `Billboard`：状态点（working 绿/error 红/idle 橙）+ 角色色侧条 + 名字（>8 字缩小字号）+ subtitle（角色中文名）
  - 对话气泡：Markdown 扁平化（去代码块/图片/链接/标题/列表符号）+ 截断到 180 字 + 4 行；活跃气泡带尖角和边框，空闲时偶尔显示 "• • •" 环境气泡
- **`objects/machines.tsx`** — 咖啡机渲染（`CoffeeMachinePreviewCluster` 等，供 `/machines` 展示页与场景内吧台 coffee_machine 复用）
- **`avatars/profile.ts`** — 确定性头像生成：FNV-1a 哈希 seed → 派生肤色（6 种）/发型（4 种）/发色（8 种）/上装（tee/hoodie/jacket）/下装（pants/shorts/cuffed）/鞋色/帽子/眼镜/耳机/背包

### 监控大屏（`screens/Dashboard.tsx`）— 全文细节
- **数据源**：`getRestaurantState()`（`/admin/restaurant-state`）+ `listEvents(30)`（`/visualization/events`）双拉；`useEffect` 内 `load()` 立即跑一次，再 `setInterval(load, 4000)` 每 **4 秒**轮询，卸载时 `clearInterval`。
- **事件流取值优先级**：`recentEvents = events.length ? events : (state?.recent_events ?? [])`——本地 `listEvents` 结果优先（更新），为空时回退到 `restaurant-state` 内嵌的 `recent_events`。
- **布局**（全屏 `100vw×100vh`，深色 `#080c12` 背景，monospace 数字）：
  - 顶部：标题 `Coffee AI Boss · 实时监控大屏` + 当前时间（`zh-CN` 格式）
  - 4 张 KPI 卡片（`grid 4 列`）：今日订单（`today.order_count`）、今日金额（`¥today.total_amount.toFixed(2)`）、在线员工（`today.active_agent_count`，回退 `state.agents.length`）、活跃访客（`today.active_consumer_count`）
  - 下方 2 列网格（`2fr : 1.4fr`）：
    - 左 `最近订单`：遍历 `state.recent_orders`，每行显示咖啡名（米色）/`source_type`（蓝灰）/金额（金 `¥`）/时间（`toLocaleTimeString zh-CN`），空列表显示"暂无订单"
    - 右 `实时事件流`：`maxHeight:360` 滚动区，每行事件 type（金）+ 时间；按 `event_id`（String 化）做 key
- **样式风格**：全内联 `React.CSSProperties`，卡片 `rgba(14,22,34,0.9)` + 蓝色细边框 `rgba(80,130,200,0.18)` + 圆角 10；标签大写 `letterSpacing:2` 蓝 `#7fa6d8`；数字米色 `#e8dfc0` 34px 粗体。

### 咖啡机展示（`screens/MachineShowcase.tsx`，2026-06-20 新增）
- 独立 `Canvas` + `OrbitControls` + `SceneLighting`，渲染 `CoffeeMachinePreviewCluster`（来自 `office3d/objects/machines`）。
- `ShowcaseStage`：程序化搭展示台（米色地面 + 棕色台面 + 深色背板 + 顶部招牌条），单个 `coffee_machine` 家具置于台中央（elevation 0.22）。
- 不接 ws 事件，纯静态展示页（路由 `/machines`）。

### 账户登录（`auth/`，可选增值）
- **`AuthProvider.tsx`** — React Context，封装 `login/register/logout/me`，签名 Cookie 会话。**未登录时 `account` 为 null，前端照常渲染场景/大屏/聊天**（登录非前置条件）。
- **`AuthPages.tsx`** — 登录/注册表单（全文已扫）：
  - 内联样式（无 CSS 文件），深色卡片 + 径向渐变背景，主题色 `#2a6ba8`（与收银员角色色一致）
  - `LoginPage`：用户名+密码，`login()` 成功后 `nav("/scene")`；提供"注册"和"匿名进入 3D"链接（**匿名直接进 `/scene`，无任何拦截**——2026-06-20 21:30 起为咖啡厅匿名点单的正式路径，非"向后兼容"）
  - `RegisterPage`：用户名+昵称（可选）+密码，`register()` 成功后直接登录跳 `/scene`
  - 错误处理：`busy` 禁用按钮防重复提交，错误 message 红字展示

> **登录增值点**（2026-06-20 21:30）：登录仅带来两件事——① 个性化昵称（顾客人偶显示真实昵称而非占位名）；② WS 在线顾客 presence（后端 `_register_web_customer_presence` 读签名 Cookie，登录用户的顾客人偶会出现在 `scene.snapshot`/presence 广播）。**匿名访客点单、看服务员动画、看大屏完全不受影响**。

## 测试与质量

- **Playwright** 已装但无测试文件（覆盖缺口；运行时截图证据已移出活跃仓库，历史证据见 archive manifest）。
- 类型检查：`npm run build` 会先跑 `tsc --noEmit`（2026-06-20 验证零错误）。
- 无单元测试框架。
- 移植残留（2026-06-20 已清理）：原 navigation `void ITEM_FOOTPRINT/snap`、agentStore `void NAV_ENTRY`、OfficeScene `roleDeskIndex`/`DESK_LOCS`/`ROLE_DESK`/`getDeskLocations` 整套 void 占位、main.py unused import `bridge_event_to_colyseus`、furnitureDefaults `void nextUid` 已全部清理；roleMap 坐标超界与注释不符已修。

## 常见问题 (FAQ)

- **Q: 进 3D 场景需要登录吗？** A: **不需要**。`App.tsx` 所有路由（`/` `/scene` `/machines` `/dashboard`）匿名可访问，无 `<ProtectedRoute>` 守卫；`LoginPage` 提供"匿名进入 3D"直接跳 `/scene`。2026-06-20 21:30 起这是咖啡厅匿名点单的正式路径。
- **Q: 匿名能在 3D 场景里点单吗？** A: 能。`OfficeScene` 内嵌聊天消费后端 `POST /chat`（匿名 user_id，无 auth）；后端 `/chat` 无登录依赖。服务员编排（接单/收银/做咖啡/送餐动画）照常触发。唯一差别：匿名访客自身不会有"顾客人偶"在 snapshot 里（后端 presence 需签名 Cookie），但点单业务流和事件广播完全正常。
- **Q: 那 `/login` `/register` 还有什么用？** A: 可选增值：个性化昵称 + WS 在线顾客人偶 presence（登录后顾客人偶出现在 snapshot）。不是浏览/点单前置。
- **Q: 3D 页面 404？** A: 需先 `npm run build` 把产物输出到 `app/static/3d/`，否则根 `/` 与 `/3d` 路由返回 "3D build not found"。
- **Q: 开发模式如何连后端？** A: Vite 代理 `/ws`、`/api` 到 `localhost:8000`；`api.ts` 的 `base` 在 DEV 模式返回 `http://localhost:8000`。
- **Q: 大屏数据多久刷新？** A: `Dashboard.tsx` 每 **4 秒**同时轮询 `/admin/restaurant-state`（KPI/最近订单/在线员工）和 `/visualization/events?limit=30`（事件流）。
- **Q: 为什么服务员人偶动作不触发？** A: 2026-06-20 已修 B1——后端动作事件外层 `type` 永远是 `"agent.action"`，真动作在 `payload.action_type`；`OfficeScene.onEvent` 已重写取 `payload.action_type`。若仍不触发，检查后端是否广播了 `agent.action` 类型（而非旧的 `restaurant.*`/`order.*`）。
- **Q: 刷新页面后服务员消失了？** A: 2026-06-20 已修——`scene.snapshot` 的 `payload.agents` 含 4 staff + 活跃顾客，`onSnapshot` 会预创建人偶。若消失，检查后端 `_snapshot_agents` 是否返回了 staff。
- **Q: Agent 卡在家具里不动？** A: `astar` 的 `findFree` 会螺旋搜索最近空闲格，但若起终点都在大块家具内部且 10 格内无空闲格会返回空路径；检查 `ITEM_METADATA` 的 `blocksNavigation`/`navPadding` 配置。
- **Q: GLB 加载失败？** A: 家具 GLB 必须存在于 `public/office-assets/models/furniture/`，构建后落到 `app/static/3d/office-assets/`；`FurnitureModel` 对未知类型兜底用 `table.glb`。

## 相关文件清单

| 文件 | 说明 |
|------|------|
| `src/main.tsx` | React 挂载入口 |
| `src/App.tsx` | 路由（**无 ProtectedRoute 守卫，全匿名**）+ TopBar（"3D 咖啡厅"导航）+ AuthProvider |
| `src/screens/OfficeScene.tsx` | 3D 咖啡厅主场景（装配 Canvas+灯具+家具+Agent+聚光灯+GameLoop）；**onEvent 契约适配 + onSnapshot 预创建人偶（2026-06-20）** |
| `src/screens/Dashboard.tsx` | 监控大屏（4s 双轮询 + 4 KPI 卡 + 最近订单 + 实时事件流） |
| `src/screens/MachineShowcase.tsx` | 咖啡机展示页（独立 Canvas + ShowcaseStage，2026-06-20 新增） |
| `src/auth/AuthProvider.tsx` | 账户 Context（login/register/logout/me；未登录 account=null，不阻断渲染） |
| `src/auth/AuthPages.tsx` | 登录/注册表单（内联样式，支持匿名进入） |
| `src/net/api.ts` | fetch 封装 + 事件契约类型 |
| `src/net/visualizationSocket.ts` | WebSocket 客户端（自动重连 + onSnapshot 回调） |
| `src/sim/agentStore.ts` | 事件驱动状态机（applyEvent 意图分派；**enter 分支 re-enter 不 teleport，2026-06-20**） |
| `src/sim/tick.ts` | 每帧推进（A\* 航点跟随 + 坐/站判定） |
| `src/sim/roleMap.ts` | 角色→桌位/颜色/行为映射（**后端契约镜像**；waiter y660 微调） |
| `src/office3d/core/constants.ts` | 坐标系/动画/相机常量 |
| `src/office3d/core/geometry.ts` | 画布→世界投影、家具包围盒、阻塞元数据 |
| `src/office3d/core/navigation.ts` | A\* 寻路 + nav grid 构建 + 桌位定位 |
| `src/office3d/core/furnitureDefaults.ts` | 咖啡厅布局（吧台/客座/休闲，2026-06-20 从 office 改造） |
| `src/office3d/core/types.ts` | OfficeAgent/RenderAgent/FurnitureItem 类型 |
| `src/office3d/scene/environment.tsx` | 地板与墙体 |
| `src/office3d/systems/cameraLighting.tsx` | 固定明亮灯光（SceneLighting）+ 概览相机 |
| `src/office3d/systems/sceneRuntime.tsx` | GameLoop + 聚光灯 |
| `src/office3d/objects/furniture.tsx` | GLB 家具渲染（模板缓存+染色+阴影） |
| `src/office3d/objects/agents.tsx` | 盒状人偶 AgentModel（骨骼动画+表情+气泡） |
| `src/office3d/objects/machines.tsx` | 咖啡机渲染（CoffeeMachinePreviewCluster） |
| `src/office3d/objects/types.ts` | AgentModelProps 等组件 props 类型 |
| `src/office3d/avatars/profile.ts` | 确定性头像档案生成（FNV-1a） |
| `vite.config.ts` | Vite 配置（base=/3d/，outDir=../app/static/3d） |
| `index.html` | HTML 模板 |
| `public/office-assets/` | 3D 资源（GLB 模型、背景贴图） |
