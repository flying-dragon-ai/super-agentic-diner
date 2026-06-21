[根目录](../CLAUDE.md) > **app** (后端)

# app/ — FastAPI 后端

## 变更记录 (Changelog)

| 时间 | 动作 | 说明 |
|------|------|------|
| 2026-06-21 | 3D 交互增强（第三步） | **/chat 广播 show_message 打通 3D 店长气泡**（`docs/3D交互增强-执行计划.md` 第三步）。① `chat()` 新增 `_broadcast_reply_speech(text)` 闭包 helper：在 customer_agent 块后预取 `staff:manager` agent（只读 `db.query`，不触发创建），best-effort 调 `staff_service.publish_agent_action(db, mgr, "show_message", text=text[:200], correlation_id=req.request_id)`，失败 swallow 不阻断回复。② **7 个 return 点**（查看订单/下单失败/下单成功/咖啡未解析/待确认订单/编排器 orch.reply/降级 handle_message）前各加一行 `_broadcast_reply_speech(...)`，统一覆盖所有回复路径含 LLM 无 key 降级。③ **前端链路已就绪无需改动**：`sim/agentStore.applyEvent` 的 `show_message` 分支（`payload.text → speech Map`）早已存在，`office3d/objects/agents.tsx` 读 `speechText` 渲染气泡（`flattenSpeechBubbleMarkdown`+`clampSpeechBubbleText` 180 字截断）。④ 验证：`POST /chat`（user_id=99998）reply 正常（"你好呀！☕ 欢迎来到 EvoMap..."），**⚠️ 需后端重启加载新代码后 `show_message` 事件才广播**（当前 uvicorn 进程未带 `--reload` 或 Windows reload 卡死，改动未自动生效；重启后 `/visualization/events` 可见 `agent.action/show_message`）。语法检查通过（`ast.parse` OK）。`publish_agent_action` 是 best-effort，绝不阻断点单/支付 |
| 2026-06-21 09:55 | 增量校验（第九次 init） | **一致性校验 + 补漏**（仅文档，不改源码；对照 HEAD `031608f`）。① **表数校正 16→17**：`models.py` 实测 17 个 `class X(Base)`，新增**第 17 张表 `office_layout`**（3D 编辑器布局持久化，全局单例 by `namespace`）+ 新 service `office_layout_service.py`（`get_layout`/`save_layout` upsert，JSON 损坏降级 None 不阻塞渲染）。② **新增路由补录**：`GET /menu`（菜单图片卡片数据源，前端 `.menu-card` 消费，`get_all_products` 60s 缓存）、`GET|PUT /api/office/layout`（3D 编辑器布局读写，匿名可读写遵循无登录门槛原则）。③ **测试段校正**：app/CLAUDE.md 原"34 passed"已过时，实测 12 个 pytest 文件（根 CLAUDE.md 计数），详见测试段。④ **FAQ 根路由校正**：原第一条 Q 仍写"`/` 匿名直出不校验登录"——与 `d408c58` 恢复的登录门槛矛盾，已改为"根路由 `/` 需登录（未登录 302 `/3d/login`），但点单 API `/chat` 匿名"。⑤ 文件清单补 `office_layout_service.py` + 修 `main.py`/`models.py` 描述。⑥ 校验通过项（保持不动）：startup `_ensure_staff_seeded` 不广播、`/3d/sounds` mount 已恢复、reviewer timeout_seconds 遗留 bug 标注、多 Agent 协作架构、LLM 超时系统重构均准确 |
| 2026-06-21 08:10 | 增量刷新（第八次 init） | **多 Agent 协作架构 + LLM 超时系统完整重构 + /chat 加速 + 16 表**。① **多 Agent 协作**（详见新增「多 Agent 协作架构」小节）：`services/agents/`（manager/recommender/reviewer/experience）+ `agent_orchestrator.orchestrate`（/chat 的 recommend/chat 入口）+ `evomap_evolution_service`（UA 伪装绕 Cloudflare + REST 风格记忆 API）+ 第 16 表 `AgentExperience` + 新端点 `/admin/agent-collaboration`·`/admin/evomap/status`；复盘走后台线程（`_run_review_background`），经验三写（MySQL+Redis+EvoMap）。② **LLM 超时系统完整重构**（`6ba57cc`）：config 加 `redis_socket_connect/timeout=3/5s` + `llm_connect/intent/generation/review_timeout=3/4/12/6s`（保留 `llm_timeout=15s`）；client `_timeout()` 分阶段 httpx.Timeout + `_run_with_wall_clock_timeout()` **ThreadPoolExecutor 挂钟超时** + `reset_client`；parse_intent 用 intent 超时 + temp=0.0 + 只传最近 2 轮。③ **暖身店长 persona** + INTENT_PROMPT 精简（省 ~470 tokens/次）。④ **/chat 加速**：`_detect_exact_product`（精确+部分匹配，歧义不返回）+ `_is_clearly_non_order` 启发式跳过 parse_intent；`ChatResponse` 新增 `products` 卡片字段；`get_all_products` 60s TTL 缓存。⑤ **同义词地图 70+ 条**（9 大类）+ 未知咖啡品类友好兜底。⑥ **EvoMap 进化服务** UA 伪装绕 Cloudflare + record_lesson/recall 改 REST 风格。⑦ **⚠️ 根路由 `/` 恢复登录门槛**（`d408c58`，反转第七次匿名直出）：未登录→302 `/3d/login`，已登录→2D 聊天页；`/3d/*` + `POST /chat` 仍匿名。⑧ startup `_ensure_staff_seeded()` **不广播**。⑨ **遗留 bug**：`reviewer_agent.py:67,81` 调 `chat_with_role(timeout_seconds=)` 签名不匹配→TypeError，被后台线程兜住→复盘静默失效（不伤业务）。测试 71 passed（11 文件，第九次 init 校正为 12 文件）。覆盖率 99% |
| 2026-06-21 01:47 | 增量刷新 | **在线用户显示模型 + WS presence + Skill 心跳 + 服务员并发去重 + `/3d/sounds` 挂载**。① **`visualization_service.VisualizationHub`**：加 `_ws_agent` 在线映射（websocket→顾客 agent_id）+ `register_ws_presence`/`online_ws_agent_ids`；拆出 `broadcast_others`（排除自己、不持久化）与 `broadcast_transient`（不持久化，用于上线/离线/sweep 通知，避免污染 `_recent_events` 回放缓冲）；原 `broadcast` 仍持久化业务事件。② **WS 端点 `/ws/visualization` 重写**：连接时读 `websocket.cookies` → `auth_service.read_session_token` → `account.user_id` → `ensure_web_customer_agent` → `register_ws_presence`（未登录跳过、不显示）；DB 操作用 `anyio.to_thread.run_sync` 避免阻塞事件循环；snapshot 由 `_build_snapshot_agents(db)` 构造传入 `connect(ws, agents=...)`（修原先恒空）；上线 `broadcast_others`、离线 `broadcast_transient` 实时增删人偶。③ **`_build_snapshot_agents`**：4 服务员常驻 + 在线顾客（`agent_id in online_ws_agent_ids` OR `last_seen_at >= now - ONLINE_WINDOW_SECONDS(120)`）。④ **`_register_web_customer_presence`**：Cookie→account→建/复用顾客 agent→刷新 `last_seen_at` + display_name 用真实账号名。⑤ **startup `_ensure_staff_seeded`**（幂等创建 4 服务员；删掉原先无效的 `broadcast_from_sync` 广播——async 上下文失效且无接收者）+ **`_skill_presence_sweep_loop`**（后台每 30s 清扫过期 Skill 顾客，广播 `leave_scene`，修"Skill 用户离线后人偶不消失"；web 用户由 disconnect handler 即时处理，sweep 只管非 WS 的 Skill 用户）。⑥ **`staff_service` 重构**：`ensure_staff_agents`/`ensure_web_customer_agent` 改 ensure→`_collapse_duplicate_agents`→重查 survivor 返回（修并发 race：`tool_name` 无唯一约束 + query-then-create 重复创建；不能加全局唯一约束，因 skill 路径 `codex` 合法重复）；`ensure_staff_agents` 用 `in_` 批量查询。⑦ **`skill_order_service._complete_order`** 更新 `agent.last_seen_at`（Skill 心跳，原先只更新 consumer）。⑧ **静态挂载补 `/3d/sounds`**（修背景音乐 mp3 被 `/3d/{path}` SPA fallback 返回 HTML 的 bug）。新增 `tests/test_web_presence_snapshot.py`（5 用例）。覆盖率 99% |
| 2026-06-20 21:30 | 增量刷新 | **匿名点单门槛确立**（仅文档刷新，不改源码）。核心对齐 `app/main.py:1696` `index()`：根路由 `/` **直接返回 3D 咖啡厅 SPA，匿名可访问、不校验登录**（3D 未构建时才 fallback 到 2D `index.html`）。确认点单全程无登录门槛：① `POST /chat`（`main.py:588`）无 auth 依赖、匿名 `req.user_id`；② `/skill/orders` 走 Agent token（非账户登录）。`/auth/*` 与 `/3d/login` `/3d/register` **改为可选增值**（个性化昵称 + WS 在线顾客 presence），不是点单前置。**唯一例外**：`/ws/visualization` 的 `_register_web_customer_presence`（`main.py:1428`）读签名 Cookie，**匿名访客被跳过、不显示为在线顾客人偶**，但**不阻断匿名点单**（事件流照常推、服务员编排照常跑）。uvicorn 启动建议 `--reload-dir app`（规避 `_mock_hub.py`）或不带 `--reload`（Windows 卡死兜底）。覆盖率维持 ~99% |
| 2026-06-20 19:07 | 增量刷新 | **服务员团队编排落地**（外部 commit "服务员团队编排/staff 智能模型"）：① 新增 `services/staff_service.py`——4 个固有服务员 agent 幂等创建（`staff:barista/cashier/waiter/manager`，sprite_seed 100001-100004）+ `ensure_web_customer_agent`（web 匿名用户也建顾客 agent，修 B4 `agent_anon`）+ `orchestrate_staff_node`（业务节点→服务员动作编排）+ `publish_staff_action/publish_agent_action`（best-effort 广播，失败 swallow+rollback）。② 编排挂载点：`main.py` lifespan startup `_seed_and_broadcast_staff`（广播 4 条 `agent.registered`）+ `_publish_web_completion_flow`/`_publish_skill_completion_flow` 各业务节点（payment_completed/preparation_progress×3/order_ready/order_delivered/customer_left）+ intent_detected 节点。③ `visualization_service` 的 `scene.snapshot` 追加 `agents` 字段（4 staff + 活跃顾客），后连接页面也能看到服务员。④ 编排容错铁律：可视化编排绝不阻断订单/支付。详见新增「服务员团队编排」小节。覆盖率维持 ~99% |
| 2026-06-20 10:05 | 增量对齐 | 第三次 init：① 2D 对话页归档——根 `/` 改直出 3D SPA（旧 2D 页面已移出活跃仓库，外部归档见 `docs/archive-manifest.md`），`/static/index.html` 已不存在；`/chat` 仍作 JSON API 供 3D 场景内嵌聊天消费。② Colyseus 子进程拉起为 no-op（`colyseus_bridge.py` 检测 `colyseus-server/` 目录缺失 → 仅 warning 跳过）。③ 数据模型实际 15 表（新增 Product/ProductOptionGroup/ProductOption/OrderItem/OrderItemOption/UserWallet/BalanceTransaction）。④ 新增 services：wallet_service（credits 钱包流水）、catalog_service（库存递减）。⑤ 补扫 evomap_payment_service / skill_order_service 幂等恢复细节 |
| 2026-06-20 | 创建 | 初始化架构师首次生成 |

---

## 模块职责

Coffee AI Boss 的 Python 后端，提供：
1. **对话式点单**（`/chat`）：LLM 意图分类 + RAG 推荐 + 两段式确认 + 余额扣款。匿名 `user_id`（`/chat` 本身无 auth 依赖；根路由 `/` 有登录门槛但点单 API 不依赖）。
2. **A2A Skill 点单**（`/skill/register`、`/skill/orders`）：EvoMap 消费者身份 + 积分支付 + 免费额度（走 Agent token，非账户登录）。
3. **Agent 可视化 API**（`/agents/*`、`/agents/{id}/actions`）：外部 Agent 工具注册并上报动作，生成可视化事件。
4. **实时可视化**（`/ws/visualization`、`/visualization/events`、`/admin/restaurant-state`）：事件流持久化 + WebSocket 广播。
5. **服务员团队编排**（`services/staff_service.py`）：4 个固有服务员 + 业务节点→服务员动作编排（2026-06-20 新增）。
6. **多 Agent 协作**（`services/agents/` + `agent_orchestrator.py`，2026-06-21 落地）：店长(意图+纠正/生气/重复检测)→推荐(RAG+硬过滤+经验)→[后台]复盘(失误分析)→经验继承(MySQL+Redis+EvoMap 三写)；`/chat` 的 recommend/chat 走编排器，配合 EvoMap 群体进化共享经验。
7. **账户认证**（`/auth/*`）：3D 前端的注册/登录/登出/会话。根路由 `/` 的登录门槛依赖它；点单 API 不依赖。
8. **3D 编辑器布局持久化**（`/api/office/layout` GET/PUT + `office_layout_service.py`，2026-06-20 新增）：全局单例（`namespace='default'`）家具布局存储，员工编辑一次所有访客共享，JSON 损坏降级 None 不阻塞渲染。

## 入口与启动

- **入口**：`app/main.py`（`app = FastAPI(title="智能咖啡馆 AI 店长")`）
- **启动**（推荐二选一）：
  - `uvicorn app.main:app --reload --reload-dir app`（`--reload-dir app` 规避根目录 `_mock_hub.py` 触发的热重载干扰）
  - `uvicorn app.main:app`（不带 `--reload`，Windows + merge 频繁文件变化时 `--reload` 易卡死的兜底）
  - 端口 8000，**根路由 `/` 有登录门槛**（未登录→302 `/3d/login`，已登录→2D 聊天页）；`/3d/*` 与 `POST /chat` 匿名可用。
- **生命周期**：
  - `startup` → `_startup_colyseus()`：① `start_colyseus_server()`（**目标目录已归档**，`colyseus_bridge.py` 检测目录缺失 → 记 warning 并 return None，**不拉子进程、不占端口**）；② `_ensure_staff_seeded()`（幂等创建 4 个服务员，**不广播** `agent.registered`——冷启动无接收者，靠 `_build_snapshot_agents` 稳定返回）；③ `_skill_presence_sweep_loop`（asyncio，30s 扫过期 Skill 顾客）；④ EvoMap 心跳线程（5min，配 `evomap_node_id`+`evomap_node_secret` 才启，心跳 + 拉社区经验）。全包 try/except，可视化 seeding 绝不 crash app boot。
  - `shutdown` → `stop_colyseus_server()`：`_proc=None` 时直接返回，no-op。
  - `bridge_event_to_colyseus(event)`：Stage 0 stub，仅 `logger.debug`，未被移除（保留集成点，便于未来恢复）。
- **静态托管**：
  - `/static` → `app/static/`（构建产物区，含回归活跃的 2D 聊天页 `index.html`，由根路由 `/` 在已登录时返回）
  - `/3d/assets`、`/3d/office-assets` → `app/static/3d/`（Vite 构建产物）
  - **`/3d/sounds` → `app/static/3d/sounds/`**（`m1.mp3`/`m2.mp3` 背景音乐；独立 mount 修此前被 `/3d/{path}` SPA fallback 返回 HTML 致 audio 静默的 bug）
  - **`/` → 有登录门槛**：`index()`（`main.py:1855`）读会话 Cookie → 未登录 302 `/3d/login`；已登录返回 2D 聊天页 `app/static/index.html`（含 `.menu-card` 卡片，fetch `/menu`）。**点单 API `/chat` 与 `/3d/*` 仍匿名**。
  - `/3d`、`/3d/{path}` → 3D SPA（fallback 到 index.html，支持 `/3d/scene`、`/3d/login`、`/3d/dashboard`、`/3d/machines` 客户端路由；均匿名可访问）

## 对外接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/` | **有（Cookie）** | 根路由：未登录→302 `/3d/login`，已登录→2D 聊天页 `app/static/index.html`（`d408c58`，反转第七次的匿名直出）。**点单 API `/chat` 仍匿名** |
| POST | `/chat` | **无（匿名 user_id）** | 对话点单主入口；返回回复 + 可选 order_id + products 卡片。**无 auth 依赖**，匿名 `req.user_id`。**当前由 3D 场景内嵌聊天 + 已登录的 2D 聊天页消费**。下单成功会触发服务员编排（`_publish_web_completion_flow`） |
| GET | `/menu` | 无 | 菜单图片卡片数据源（名称/价格/标签/类别/图片路径/库存），前端 `.menu-card` 消费；走 `get_all_products` 60s TTL 缓存 |
| GET | `/api/office/layout` | 无（匿名可读） | 3D 编辑器布局读取；未保存返回空列表，前端用默认/localStorage 兜底 |
| PUT | `/api/office/layout` | 无（匿名可写） | 3D 编辑器布局保存（单例 upsert by `namespace`） |
| POST | `/agents/register` | 无 | 注册 Agent，返回 api_token（明文一次性）+ sprite_seed |
| POST | `/agents/{id}/heartbeat` | Agent token | 心跳，更新 last_seen_at |
| POST | `/agents/{id}/actions` | Agent token | 上报动作（enter_scene/take_order/...） |
| GET | `/agents` | 无 | 列出活跃 Agent（启动后含 4 个 `staff:*` 服务员） |
| POST | `/skill/register` | 无 | 注册 EvoMap 消费者 + Agent，返回免费额度 |
| POST | `/skill/orders` | Agent token + 可选 X-Evomap-Node-Secret | A2A 点单；返回 402 表示需积分支付。下单成功触发服务员编排（`_publish_skill_completion_flow`）。**走 Agent token，非账户登录** |
| GET | `/visualization/events` | 无 | 拉取最近事件（limit ≤ 200） |
| GET | `/admin/restaurant-state` | 无 | 大屏聚合状态（今日订单/金额/来源/最近订单/事件/Agent） |
| GET | `/admin/agent-collaboration` | 无 | 多 Agent 协作状态（最近经验记录，供大屏展示） |
| GET | `/admin/evomap/status` | 无 | EvoMap 节点状态（心跳/进化圈/credits/novelty，`evomap_evolution_service.get_node_status`） |
| WS | `/ws/visualization` | 无（连接匿名） | 实时事件流；连接即推 `scene.snapshot`（payload 含 `agents` 字段：4 staff + 活跃顾客，2026-06-20 新增）；支持 presence.move/leave + ping/pong。**注**：连接本身匿名，但"在线顾客人偶 presence"需签名 Cookie（`_register_web_customer_presence` 匿名访客被跳过），不阻断匿名点单 |
| POST | `/auth/register` `/login` `/logout` | Cookie | 账户会话（httpOnly 签名 Cookie）。根路由 `/` 登录门槛依赖它；点单 API 不依赖 |
| GET | `/auth/me` | Cookie | 当前登录账户（根路由门槛 + 2D 聊天页用） |
| GET | `/user/{id}` `/orders/{id}` `/history/{id}` | 无 | 用户/订单/对话历史查询 |
| DELETE | `/history/{id}` | 无 | 清空对话历史 |
| GET | `/status` | 无 | 数据库/LLM 配置状态 |

**Agent token 鉴权**：`_require_agent()` 校验 `Authorization: Bearer <token>` 或 `X-Agent-Token`，对比 `api_token_hash`（SHA-256）。**服务员 agent 无 token**（`staff:{role}:internal` 仅是满足 NOT NULL 的占位 hash，不做鉴权）。

> **登录门槛说明**（2026-06-21 `d408c58` 恢复）：**根路由 `/` 需登录**（未登录→302 `/3d/login`，已登录→2D 聊天页）。但**点单链路 `/chat`、`/skill/orders`、`/3d/*` 全程匿名**，无账号密码门槛——登录只是 `/` 根页面的访问控制，点单 API 与 3D 场景仍匿名可用。`/auth/*` 同时承载 WS 在线顾客人偶 presence（读签名 Cookie）。

## 关键依赖与配置

- **Web 框架**：FastAPI + Uvicorn（`requirements.txt`）
- **ORM**：SQLAlchemy 2.0（`declarative_base`，`pool_pre_ping` + `pool_recycle=3600`）
- **数据库**：MySQL 8.0（`mysql+pymysql`，唯一支持的持久化后端）
- **缓存/记忆**：Redis（短期对话历史 List + 待确认订单 String）
- **LLM**：OpenAI 兼容协议，用 `httpx` 直连（**非** openai SDK，避免版本冲突）；429 自动重试 1 次
- **EvoMap 支付**：用标准库 `urllib.request` 直连（`evomap_payment_service.py`，非 httpx），`x-correlation-id=request_id`
- **分词**：jieba（中文关键词 RAG）
- **认证**：bcrypt + itsdangerous（签名 Cookie）——根路由 `/` 门槛 + `/auth/*` + WS presence 用；点单 API（`/chat`、`/skill/orders`）不依赖
- **配置**：`app/config.py` 用 `pydantic-settings` 从 `.env` 读取；`effective_llm_api_key` 按优先级选 `LLM_API_KEY > DEEPSEEK_API_KEY > OPENAI_API_KEY`，过滤 placeholder。 

## 数据模型（`app/db/models.py`，17 张表）

| 表 | 说明 | 关键字段 |
|----|------|---------|
| `user` | 匿名/登录顾客（带本地余额） | user_id, balance, taste_preference |
| `user_account` | 3D 前端登录账户（与 user 1:1） | username(unique), password_hash, user_id(FK) |
| `order` | 已支付订单 | user_id, coffee_name, amount, source_type(web_dialog/skill), payment_status, request_id(unique), consumer_id/agent_id/ledger_id/correlation_id |
| `order_item` | 订单明细行（与 product 快照） | order_id, product_id, product_name_snapshot, unit_price, quantity, line_total |
| `order_item_option` | 订单行加料/规格选项 | order_item_id, ... |
| `product` | 商品目录（含 base_price、库存） | name, base_price, ...（替代/补充老 coffee_kb 的价格源） |
| `product_option_group` | 商品选项组（规格/加料） | ... |
| `product_option` | 具体选项项 | ... |
| `coffee_kb` | 咖啡知识库（RAG 数据源 + 价格） | coffee_name, content, price, tags |
| `agent_profile` | 外部 Agent 身份（**也承载固有服务员 `staff:*` 与 web 顾客 `web:customer:*`**） | tool_name, role_type, api_token_hash, sprite_seed, status, metadata_json(source=staff/web) |
| `evomap_consumer` | EvoMap 消费者（A2A 点单主体） | evomap_node_id(unique), free_orders_used, local_user_id |
| `skill_order_ledger` | A2A 点单账本（幂等 + 支付凭证） | request_id(unique), amount_credits, payment_status, order_ids_json, evomap_order_id, payment_proof_json, coffee_items_json |
| `user_wallet` | 用户钱包（credits 等多币种） | user_id, currency, ... |
| `balance_transaction` | 钱包流水（consume/free_order 等） | user_id, currency, type_, amount, order_id, ledger_id, correlation_id, note |
| `visualization_event` | 可视化事件流（持久化） | event_type, payload_json, correlation_id, agent_id |
| `agent_experience` | 多 Agent 经验（复盘教训持久化，2026-06-21 新增，第 16 张表） | experience_id, user_id, agent_role, coffee_name, context_tags, insight, rating, order_id, correlation_id（Index: user_id+context_tags） |
| `office_layout` | 3D 编辑器布局（全局单例 by namespace，2026-06-20 新增，**第 17 张表**） | layout_id, namespace(unique), layout_json（FurnitureItem[] JSON blob）, updated_at |

**CHECK 约束**：order.source_type / status / payment_status、agent/consumer.status、ledger.payment_status 都用域常量（`app/domain_constants.py`）做数据库级校验。`WALLET_CURRENCY_CREDITS = "credits"`（`domain_constants.py:88`）。

> 说明：本次扫描（第九次 init）在 `models.py` 实测 **17 个 `class X(Base)`**。`order_item`/`product`/`user_wallet`/`balance_transaction` 是 Skill 点单落库与新目录体系引入；`agent_experience` 是多 Agent 协作引入；`office_layout` 是 3D 编辑器持久化引入（JSON blob，不做关系分解，~100 项家具）。服务员团队**不新增表**，复用 `agent_profile`（`tool_name` 用 `staff:{role}` 约定，`metadata_json={"source":"staff","staff_role":role}`）。

## 核心流程

### `/chat` 对话点单决策树（`app/main.py`）
```
1. 查看订单意图？(_is_order_view_query) → 返回订单列表
2. 读 Redis 历史 + 待确认订单(pending)
   ├─ 有 pending 且 _is_confirming → place_orders 扣款 + 发布完成流事件(_publish_web_completion_flow)
   └─ 否则清 pending，继续
3. LLM 意图分类(parse_intent): order / recommend / chat
   ├─ order → 四路解析咖啡名:
   │   3.1 价格匹配(extract_price + match_by_price)
   │   3.2 LLM 显式 coffee_name
   │   3.3 RAG 关键词(extract_keywords + retrieve)
   │   3.4 历史提取(_resolve_coffees_from_history, 兜底)
   │   → set_pending_order 存 Redis，回"确认下单请回复确认"
   └─ recommend/chat → chat_service.handle_message(RAG + LLM)
```

### Skill 点单（`app/services/skill_order_service.py`）
```
process_skill_order:
  发 restaurant.customer_entered + message.received 事件
  幂等检查(按 request_id 查 SkillOrderLedger)
    ├─ 已存在且 consumer_id 不符 → 409 request_id_conflict
    └─ 已存在 → _resume_existing_order
  _resolve_items(直接名/价格/LLM/RAG/后缀匹配；从 Product 表取 base_price)
  免费额度判断(free_sequence = free_orders_used+1 <= SKILL_FREE_ORDER_LIMIT)
    ├─ 免费 → _complete_order(PAYMENT_STATUS_FREE) + free_order_sequence 记账
    └─ 需付费:
        ├─ 传了 payment_proof → _reject_unverified_payment_proof(402, 拒绝客户端伪造)
        ├─ 无 node_secret → ledger=PAYMENT_STATUS_PAYMENT_REQUIRED → 抛 SkillPaymentRequired(402, 含 service_order_request)
        └─ 有 node_secret → _charge_evomap_and_complete:
             place_service_order(EvoMap Hub) → _complete_order(PAYMENT_STATUS_PAID)
             支付成功但本地落库失败 → ledger=NEEDS_RECONCILE + 事件 order.failed(code=local_order_reconcile_required)
  intent_detected 节点 → orchestrate_staff_node("intent_detected") (waiter walk_to_counter)

_resume_existing_order(幂等恢复，三态):
  FREE/PAID                       → _success_response("幂等重试：订单已完成")（不改库）
  PAYMENT_REQUIRED/FAILED/PENDING → 客户端 payment_proof 仍拒；无 node_secret 抛 402；有则重新 _charge_evomap_and_complete
  其余                            → SkillOrderError("订单账本状态不可恢复", code=ledger_not_resumable)

_complete_order(落库 + 钱包镜像):
  按 request_id[:index] 幂等建/复用 Order 行；fresh 订单写 OrderItem + decrement_stock（catalog_service）
  免费：consumer.free_orders_used = max(old, seq)（防回退）；wallet_service.apply_transaction(type=free_order, amount=0)
  付费：wallet_service.apply_transaction(type=consume, amount=-amount_credits)（EvoMap 扣款镜像）
  发 restaurant.* 完整流程链(payment_completed→grinding→brewing→plating→order_ready→order_delivered→customer_reviewed→customer_left)
  每个节点后调 orchestrate_staff_node (见下「服务员团队编排」)
```

### 服务员团队编排（`app/services/staff_service.py`，2026-06-20 新增）

> 对应 `docs/smart-search-evidence/20260619-coffee-pixel-style/SKILL-VISUALIZATION-ROADMAP.md` 的 Phase 2/3/4。决策：**后端编排**（前端只读渲染），服务员 agent_id 用固定约定（`staff:barista` 等），无"谁空闲"调度（YAGNI）。

**4 个固有服务员**（`STAFF_ROLES`，启动幂等创建）：

| role | tool_name | display_name | sprite_seed | 工位坐标（前端 roleMap.ts） |
|------|-----------|-------------|-------------|---------------------------|
| barista | `staff:barista` | 咖啡师 | 100001 | (360, 540) |
| cashier | `staff:cashier` | 收银员 | 100002 | (620, 320) |
| waiter | `staff:waiter` | 服务员 | 100003 | (880, 660) |
| manager | `staff:manager` | 主管 | 100004 | (1180, 320) |

**核心函数**：
- `ensure_staff_agents(db)`：按 `tool_name=staff:{role}` 幂等查询/创建 4 个 agent（`metadata_json={"source":"staff"}`，`api_token_hash` 用 `staff:{role}:internal` 占位满足 NOT NULL 但不做鉴权）。
- `ensure_web_customer_agent(db, user_id)`：为 web 匿名用户幂等建 `web:customer:{user_id}` 顾客 agent（修 B4——web 路径事件原本不带 agent_id 落 `agent_anon`，现携带真实 agent_id 与 skill 路径对齐）。**注**：仅当 WS 连接携带有效签名 Cookie（`_register_web_customer_presence`）时才触发——纯匿名访客的 WS 连接不会建顾客 agent（但点单链路照常）。
- `customer_enter_scene(db, customer_agent_id, ...)`：统一进场函数（2026-06-21 08:40 新增），刷 `last_seen_at` + 广播 `enter_scene`；web `/chat` 与 skill `/skill/orders` 两处去重内联 try/except 改调它，消除"在线显示模型/点单链路"架构断层。
- `publish_staff_action(db, staff, role, action_type, ...)` / `publish_agent_action(db, agent, action_type, ...)`：广播 `agent.action` 事件（payload 含 `agent_id/tool_name/display_name/role_type/sprite_seed/action_type`）；**best-effort**——失败 swallow + rollback，可视化绝不阻断业务。
- `orchestrate_staff_node(db, staff, node, correlation_id)`：业务节点→服务员动作分派：

| node（业务节点） | 追加的服务员 agent.action | 视觉效果 |
|------------------|--------------------------|---------|
| `intent_detected` | waiter → `walk_to_counter` | 服务员走向收银台接单（在 payment 之前） |
| `payment_completed` | cashier → `take_order`(work) | 收银员绿圈收银 |
| `preparation_progress` | barista → `prepare_coffee`(work) | 咖啡师绿圈做咖啡（grinding/brewing/plating 各一次） |
| `order_ready` | barista → `enter_scene` | 咖啡师完成制作返回工位 |
| `order_delivered` | waiter → `deliver_order` | 服务员走到顾客桌位送餐 |
| `customer_left` | waiter → `enter_scene` + cashier → `enter_scene` | 服务员复位 |

**挂载点**（编排挂在已有完成流节点，零业务侵入）：
- `main.py` lifespan startup `_seed_and_broadcast_staff`：广播 4 条 `agent.registered`。
- `main.py` `_publish_web_completion_flow`：web 下单（`/chat` 确认后）各节点追加 `orchestrate_staff_node`；同时修 B4（web 事件补顾客 agent_id）。
- `skill_order_service.py` `_publish_skill_completion_flow`：Skill 下单各节点追加 `orchestrate_staff_node`；`process_skill_order` 在 intent_detected 节点也调。
- `visualization_service` snapshot：`scene.snapshot` payload 含 `agents` 字段，由 `_build_snapshot_agents` 构造 = 4 staff 常驻 + 在线顾客（WS presence ∪ `last_seen_at` 心跳窗口）；后连接页面刷新即见服务员团队 + 当前在线顾客（详见下「在线用户显示模型」）。

**验证证据**（Roadmap 第 10 节）：真实 Skill 免费单 22 事件含 9 条 staff action（waiter walk_to_counter / cashier take_order / barista×3 prepare_coffee / barista enter_scene / waiter deliver_order / waiter+cashier 复位）；mock Hub 跑通付费单 28 事件含同样 9 条 staff action。编排接线由"函数级验证"升级为"真实订单链验证"。

### 多 Agent 协作架构（`services/agents/` + `agent_orchestrator.py`，2026-06-21 新增）

> `/chat` 的 recommend/chat 路径从「直接 parse_intent + chat_service」升级为「多 Agent 编排」。编排器串起店长→推荐→[后台]复盘→经验继承，配合 EvoMap 群体进化让经验跨用户/跨节点共享。`AgentExperience` 表是经验持久化权威源。

**编排流程**（`agent_orchestrator.orchestrate`）：
```
用户消息 → _detect_exact_product(精确/部分匹配) ──命中→ 直接 order(跳过所有 LLM)
         → 店长 manager_agent.parse_intent(order/recommend/chat)
         → detect_review_trigger(纠正/生气/重复) ──命中→ 复盘后台线程(不阻塞)
         → recommend: recommender_agent.recommend(RAG + 硬过滤 + 经验软引导)
         → chat: 复用 recommender_agent(闲聊也能给建议)
         → 返回 OrchestratorResult{intent, reply, events, products}
```

**四 Agent 职责**：
| Agent | 文件 | 职责 |
|-------|------|------|
| 店长 manager | `manager_agent.py` | `parse_intent`(委托 llm) + `detect_correction/anger/repeat`(bigram Jaccard ≥0.7) + `detect_review_trigger`(优先级 correction>anger>repeat) |
| 推荐 recommender | `recommender_agent.py` | RAG 检索 + **硬过滤**(`_apply_hard_filters`: banned_names/banned_tags) + 经验软引导(注入《推荐前必读》) + `RECOMMENDER_PROMPT` |
| 复盘 reviewer | `reviewer_agent.py` | `review_mistake`：LLM 分析失误(`REVIEWER_PROMPT`→mistake_type/insight/rating) + 经验继承压缩 + 三写 |
| 经验继承 experience | `experience_agent.py` | `save_experience`(MySQL+Redis+EvoMap 三写) + `get_hard_filters`(低评分拉黑+否定口味 tag) + `sync_community_experience` |

**关键设计**：
- **复盘后台异步**：`threading.Thread(target=_run_review_background, daemon=True)`，独立 db session，失败 swallow——省 2-6s，不阻塞推荐。
- **硬过滤 vs 软引导**：硬过滤(规则剔除已知错项) + 软引导(经验注入 prompt)。
- **EvoMap 群体进化**：`evomap_evolution_service` 心跳(5min) + 进化圈共享经验池；`record_lesson`(sender_id+status+signals) / `recall_community_lessons`；UA 伪装绕 Cloudflare。
- **可视化事件**：编排产生 `agent.manager.intent`/`agent.recommender.suggesting`/`agent.recommender.suggested`/`agent.reviewer.reviewing`/`agent.experience.applied`，大屏 `/admin/agent-collaboration` 展示。

**⚠️ 遗留 bug**：`reviewer_agent.py:67,81` 调 `chat_with_role(timeout_seconds=...)` 签名不匹配 → TypeError；无 key 时提前 return 不触发，有 key 时被 `_run_review_background` 兜住→复盘静默失效（不伤业务）。修法：给 `chat_with_role` 加 `timeout_seconds: float | None = None` 透传。

---

### 在线用户显示模型（2026-06-21 新增）

> 诉求：3D 场景显示的用户必须来自数据库 `agent_profile` 且当前真实在线（修原先 snapshot.agents 恒空、无在线概念、WS 匿名三大根因）。采用双接入在线判定，因为 Skill/CLI 是一次性脚本无法维持 WS 长连接。

**双接入在线模型**：

| 接入方式 | 登录 | 身份名 | 在线探测 |
|---|---|---|---|
| **网页** | UserAccount 账号密码 → Cookie | `account.nickname/username` | **WS 连接保持**（presence） |
| **SQL/Skill** | `/skill/register`（CLI） | `detect_username()` 系统账号名 | **`agent.last_seen_at` 心跳窗口 120s**（register/orders 时更新） |

snapshot 显示规则：4 固有服务员常驻 + 在线顾客（`agent_id in hub.online_ws_agent_ids()` OR `last_seen_at >= now - ONLINE_WINDOW_SECONDS`）；未登录匿名访客不显示。

**关键组件**：
- `VisualizationHub._ws_agent`（`visualization_service.py`）：`{websocket → 顾客 agent_id}` 在线映射；`register_ws_presence`/`online_ws_agent_ids`。
- `VisualizationHub.broadcast` / `broadcast_others` / `broadcast_transient`：分别用于持久化业务事件 / 排除自己的瞬时通知 / 全员瞬时通知（上线·离线·sweep）；后两者**不入 `_recent_events` 回放缓冲**（避免回放陈旧 `leave_scene` 错误移除仍在场的人偶）。
- `_build_snapshot_agents(db)`（`main.py`）：snapshot agents = 4 服务员 + 在线顾客；字段对齐前端 `SnapshotAgent`。
- `_register_web_customer_presence(websocket)`：WS 连接时读 `websocket.cookies` → `auth_service.read_session_token` → `account.user_id` → `ensure_web_customer_agent` → `register_ws_presence` + 刷新 `last_seen_at` + display_name 用真实账号名；未登录返回 None（跳过）。DB 操作经 `anyio.to_thread.run_sync` 跑在线程池，不阻塞事件循环。
- WS 端点 `/ws/visualization`：连接→登记 presence→构造 snapshot→`connect(ws, agents)`；上线 `broadcast_others`（`agent.registered`）、断开 `broadcast_transient`（`leave_scene`）实时增删人偶。
- `_skill_presence_sweep_loop`（startup 起，每 30s）：diff `_prev_skill_online` 与当前心跳窗口内**非 WS** 的 Skill 顾客，对刚过期的广播 `leave_scene`，让已连接客户端实时移除人偶（web 用户由 disconnect handler 即时处理，sweep 只补 Skill）。

**并发与容错铁律**：
- `staff_service.ensure_staff_agents`/`ensure_web_customer_agent` 改 ensure→`_collapse_duplicate_agents`→重查 survivor 返回。因 `agent_profile.tool_name` **无唯一约束**（skill 路径 `codex` 合法重复），不能加全局唯一约束，改 per-tool_name 定向收敛（保留 `agent_id` 最小），消除并发 WS 连接的重复创建 race。
- `skill_order_service._complete_order` 同步更新 `agent.last_seen_at`（Skill 心跳，原先只更新 `consumer.last_seen_at`，导致用 agent 心跳判在线失效）。
- 静态挂载补 `/3d/sounds`（`app/static/3d/sounds`）——背景音乐 mp3 原先被 `/3d/{path}` SPA fallback 返回 HTML，audio 拿到 HTML 静默；挂载后返回 `audio/mpeg`。
- 在线探测 best-effort：presence/sweep 全包 try/except，绝不阻断 WS 握手或订单/支付业务。
- 测试：`tests/test_web_presence_snapshot.py`（5 用例：登录在线显示 / 匿名不显示 / 重复行收敛 / 过期 sweep / 在线不误清）。

### EvoMap 支付客户端（`app/services/evomap_payment_service.py`）
```
place_service_order:
  校验 evomap_payment_mode==service_order + listing_id 非空 + node_secret 非空（否则 402）
  POST {hub}/a2a/service/order，Header: Authorization: Bearer <node_secret>, x-correlation-id: request_id
  _extract_order_id: 依次试 evomap_order_id/order_id/orderId/task_id/taskId/id，再递归 order/task/payload
  无 order_id → 502 evomap_order_id_missing
  返回 {evomap_order_id, credits, request_id, consumer_node_id, listing_id, status, question, raw_response(脱敏)}
HTTP 错误映射: 401/402/429 原样透传；404/≥500 → 502；其余 → 400
脱敏: _redact_response 递归把 key 含 secret/token/key/authorization 的值替换为 [REDACTED]
```

## 测试与质量

- 测试目录：仓库根 `tests/`（不在 app/ 内）
- 后端相关测试（12 个 pytest 文件，详见根 CLAUDE.md「测试策略」）：`test_llm_configuration.py`(LLM key + 超时配置)、`test_chat_confirm.py`(两段式确认)、`test_chat_fast_path.py`(`_detect_exact_product`)、`test_chat_heuristic.py`(`_is_clearly_non_order`)、`test_chat_history_fallback.py`(Redis 降级)、`test_chat_order_view.py`(查看订单)、`test_catalog_disambiguation.py`(商品歧义)、`test_product_wallet_unit.py`+`test_product_wallet_integration.py`(商品目录+钱包)、`test_skill_evomap_payment.py`(Skill 支付)、`test_web_presence_snapshot.py`(WS presence)、`test_customer_enter_scene.py`(顾客进场统一入口，2026-06-21 08:40 新增)；另有 `verify_quick_menu.py`(快捷菜单验证脚本，非 pytest)。
- 种子数据：`app/db/seed.py`（5 款咖啡 + user_id=1 测试顾客，余额 100）；服务员团队由 `ensure_staff_agents` 在启动时幂等创建（非 seed.py）。
- 迁移脚本（`scripts/`，均幂等不删数据）：`init_db.py`(建表+种子)、`migrate_order_sources.py`、`migrate_user_accounts.py`、`migrate_product_catalog.py`(从 coffee_kb 回填 product)、`migrate_wallet_ledger.py`、`migrate_order_lineitem.py`(order 列扩展+CHECK 重建)、`migrate_agent_experience.py`(第 16 表)；另 `start.sh` Linux 生产启动脚本（绑 0.0.0.0、单 worker 保 WS presence、含连通性检查）。
- **覆盖缺口**：`staff_service` 编排无独立单元测试（靠真实订单链 + mock Hub 验证）；付费 Skill 单端到端未跑通（依赖 Owner 真实 EvoMap Hub 凭证，非代码缺陷）；`parse_intent`/`orchestrate_staff_node`/`_register_web_customer_presence` 无直接单测；`reviewer_agent` 的 `chat_with_role(timeout_seconds=)` TypeError 无测试暴露（无 LLM key 时 `review_mistake` 提前 return）。

## 常见问题 (FAQ)

- **Q: 访问 `/` 需要登录吗？** A: **根路由 `/` 需登录**（`index()`，`main.py:1855`，`d408c58` 恢复门槛）：未登录→302 `/3d/login`，已登录→2D 聊天页 `app/static/index.html`。但**点单不受影响**——`POST /chat` 无 auth 依赖、`/3d/*` 与 `/skill/orders` 全程匿名（详见下条）。3D 未构建时根路由仍 404 提示 `cd frontend && npm run build`。
- **Q: 点单（`/chat` / `/skill/orders`）需要登录账户吗？** A: **不需要**。`/chat` 无 auth 依赖、用匿名 `req.user_id`；`/skill/orders` 走 Agent token（非账户登录）。`/3d/scene` 等 3D 路由也匿名可访问。仅根页面 `/` 有访问门槛，点单 API 不依赖登录。
- **Q: 那 `/auth/*` 和 `/3d/login` 还有什么用？** A: ① 根路由 `/` 登录门槛（登录后才能进 2D 聊天页）；② 个性化昵称（登录后用真实昵称而非占位名）；③ WS 在线顾客人偶 presence——`_register_web_customer_presence` 读签名 Cookie，登录用户的顾客人偶会出现在 snapshot/presence 广播里，匿名访客则被跳过。均非点单前置。
- **Q: 匿名访客的 `/chat` 下单会触发服务员编排吗？** A: 会。`_publish_web_completion_flow` 各节点照常追加 `orchestrate_staff_node`，服务员接单/收银/做咖啡/送餐动画不受登录状态影响。唯一差别：匿名访客自身不会有"顾客人偶"在 snapshot 里（因为 `ensure_web_customer_agent` 仅在 WS presence 成功时触发），但订单业务流和事件广播完全正常。
- **Q: LLM 没配 key 会怎样？** A: `llm.has_real_key()=False`，`chat()` 走 `_mock_chat`（直接用 RAG 结果拼推荐），`parse_intent()` 走硬编码兜底词。`/status` 会显示 `llm_status_reason`。
- **Q: 为什么 LLM 不用 openai SDK？** A: 见 `app/llm/client.py` 顶部注释——避免 SDK 与 httpx 版本冲突，改用 httpx 直连 `/chat/completions`。
- **Q: 为什么 EvoMap 支付用 urllib 而非 httpx？** A: `evomap_payment_service.py` 用标准库 `urllib.request`，避免给支付链路引入额外异步/依赖耦合，错误映射集中在 `_message_for_status/_code_for_status/_http_status_for_upstream`。
- **Q: 待确认订单怎么避免误下单？** A: `_is_confirming()` 三层判定：否定/疑问词优先否决 → 强确认词（确认/下单/扣钱）长句也算 → 弱确认词（好/对/行）仅纯短句 startswith。
- **Q: Skill 点单的支付凭证能客户端传吗？** A: 不能。`_reject_unverified_payment_proof` 会拒绝客户端 payment_proof，要求传 `X-Evomap-Node-Secret` 由后端发起官方 service order。
- **Q: Colyseus 启动会失败吗？** A: 不会报错。`colyseus-server/` 已移出活跃仓库，`colyseus_bridge.py` 检测目录缺失后仅记 warning 并跳过，FastAPI 正常启动。如需恢复像素方案，按 `docs/archive-manifest.md` 中记录的外部归档路径恢复。
- **Q: uvicorn 启动卡死 / 频繁重载？** A: 根目录 `_mock_hub.py`（临时 mock，NOT part of repo）会被 `--reload` 监听，用 `uvicorn app.main:app --reload --reload-dir app` 限定 watch 范围规避；Windows 上若 `--reload` 仍卡死可去掉 `--reload` 跑固定进程。
- **Q: 服务员编排失败了会阻断下单吗？** A: 不会。`publish_staff_action`/`publish_agent_action`/`ensure_staff_agents`/`ensure_web_customer_agent`/startup seeding/ws snapshot 全包 try/except + rollback，编排是 best-effort，**可视化绝不阻断订单/支付业务**（Roadmap 铁律 #5/#7）。
- **Q: 服务员 agent 需要鉴权吗？** A: 不需要。服务员是后端固有 agent，`api_token_hash` 用 `staff:{role}:internal` 占位仅满足 NOT NULL 列约束，不走 `_require_agent()` 鉴权；编排由后端直接引用固定 agent_id 触发。
- **Q: 3D 编辑器布局存哪？** A: `office_layout` 表（全局单例 `namespace='default'`），JSON blob 对齐前端 `FurnitureItem[]`；`/api/office/layout` GET/PUT 匿名可读写（遵循项目无登录门槛原则，编辑器不强制登录）。JSON 损坏时 `get_layout` 降级返回 None，前端用默认/localStorage 兜底，绝不阻塞渲染。

## 相关文件清单

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI 入口，所有路由 + `/chat` 决策树 + 静态/3D 托管（**`index()` 根路由有登录门槛：未登录 302 `/3d/login`，已登录 2D 聊天页**）+ `/menu` + `/api/office/layout` GET/PUT + Colyseus 生命周期挂载 + lifespan `_ensure_staff_seeded`（不广播）+ `_publish_web_completion_flow` 服务员编排挂载 |
| `config.py` | pydantic-settings 配置 |
| `domain_constants.py` | 订单/支付/身份/钱包状态枚举（数据库 CHECK 约束来源） |
| `colyseus_bridge.py` | Colyseus 子进程生命周期管理（**目标已归档，启动为 no-op**） |
| `db/database.py` | engine + SessionLocal + Base |
| `db/models.py` | 17 张 SQLAlchemy 表 |
| `db/seed.py` | 种子数据 |
| `services/chat_service.py` | RAG 聊天主流程 + 价格匹配 |
| `services/order_service.py` | 事务安全扣款下单（with_for_update） |
| `services/skill_order_service.py` | A2A Skill 点单全流程（幂等恢复 + 钱包镜像 + 完成流事件链 + **`_publish_skill_completion_flow` 服务员编排挂载**） |
| `services/staff_service.py` | **服务员团队编排（2026-06-20 新增）**：4 固有服务员幂等创建 + web 顾客 agent + `customer_enter_scene`（统一进场，2026-06-21 新增）+ `orchestrate_staff_node` 业务节点→动作分派 + best-effort 广播 |
| `services/agent_orchestrator.py` | **多 Agent 编排器（2026-06-21 新增）**：`/chat` 的 recommend/chat 入口 + `_detect_exact_product` 快速 order + 复盘后台线程 + products 卡片 |
| `services/agents/` | **四 Agent 协作（2026-06-21 新增）**：manager(意图+纠正/生气/重复) / recommender(RAG+硬过滤) / reviewer(复盘，⚠️含 timeout_seconds 遗留 bug) / experience(三写经验) |
| `services/evomap_evolution_service.py` | **EvoMap 群体进化（2026-06-21 新增）**：心跳/记忆读写/社区经验（UA 伪装绕 Cloudflare） |
| `services/evomap_payment_service.py` | EvoMap 积分 service-order 支付客户端（urllib + 脱敏 + 多键 order_id 抽取） |
| `services/visualization_service.py` | Agent token 工具 + VisualizationHub（WebSocket 广播）+ **`scene.snapshot` 追加 `agents` 字段（4 staff + 活跃顾客）** |
| `services/wallet_service.py` | credits 钱包流水（apply_transaction：consume/free_order 等） |
| `services/catalog_service.py` | 商品目录 + 库存递减（decrement_stock） |
| `services/office_layout_service.py` | **3D 编辑器布局持久化（2026-06-20 新增）**：`get_layout`（JSON 损坏降级 None）/`save_layout`（upsert by namespace） |
| `llm/client.py` | OpenAI 兼容 LLM 客户端（chat + parse_intent + 分阶段超时 + 挂钟超时） |
| `rag/keywords.py` | jieba 关键词提取（正向 + 负向 + 同义词） |
| `rag/retrieval.py` | LIKE 召回 + NOT LIKE 过滤 |
| `memory/chat_history.py` | Redis 对话历史 + 待确认订单 |
| `auth/router.py` | /auth/* 路由（根路由门槛 + 2D 聊天页 + WS presence 用） |
| `auth/service.py` | bcrypt + itsdangerous 会话（根路由门槛 + /auth/* + WS presence 用） |
