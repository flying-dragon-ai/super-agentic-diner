[根目录](../CLAUDE.md) > **app** (后端)

# app/ — FastAPI 后端

## 变更记录 (Changelog)

| 时间 | 动作 | 说明 |
|------|------|------|
| 2026-06-20 10:05 | 增量对齐 | 第三次 init：① 2D 对话页归档——根 `/` 改直出 3D SPA（`index()` 注释 "2D archived to _archive/2d-legacy/"），`/static/index.html` 已不存在；`/chat` 仍作 JSON API 供 3D 场景内嵌聊天消费。② Colyseus 子进程拉起为 no-op（`colyseus_bridge.py` 检测 `colyseus-server/` 目录缺失 → 仅 warning 跳过）。③ 数据模型实际 15 表（新增 Product/ProductOptionGroup/ProductOption/OrderItem/OrderItemOption/UserWallet/BalanceTransaction）。④ 新增 services：wallet_service（credits 钱包流水）、catalog_service（库存递减）。⑤ 补扫 evomap_payment_service / skill_order_service 幂等恢复细节 |
| 2026-06-20 | 创建 | 初始化架构师首次生成 |

---

## 模块职责

Coffee AI Boss 的 Python 后端，提供：
1. **对话式点单**（`/chat`）：LLM 意图分类 + RAG 推荐 + 两段式确认 + 余额扣款。
2. **A2A Skill 点单**（`/skill/register`、`/skill/orders`）：EvoMap 消费者身份 + 积分支付 + 免费额度。
3. **Agent 可视化 API**（`/agents/*`、`/agents/{id}/actions`）：外部 Agent 工具注册并上报动作，生成可视化事件。
4. **实时可视化**（`/ws/visualization`、`/visualization/events`、`/admin/restaurant-state`）：事件流持久化 + WebSocket 广播。
5. **账户认证**（`/auth/*`）：3D 前端的注册/登录/登出/会话。

## 入口与启动

- **入口**：`app/main.py`（`app = FastAPI(title="智能咖啡馆 AI 店长")`）
- **启动**：`uvicorn app.main:app --reload`（端口 8000）
- **生命周期**：
  - `startup` → `start_colyseus_server()`：**目标目录已归档**。`colyseus_bridge.py` 检查 `_COLYSEUS_DIR = repo_root/"colyseus-server"`，目录不存在（已移至 `_archive/colyseus-server/`）→ `_COLYSEUS_DIR.is_dir()=False` → 记 warning 并 return None，**不拉子进程、不占端口**。`COLYSEUS_PORT` 仍被读取但无消费者。
  - `shutdown` → `stop_colyseus_server()`：`_proc=None` 时直接返回，no-op。
  - `bridge_event_to_colyseus(event)`：Stage 0 stub，仅 `logger.debug`，未被移除（保留集成点，便于未来恢复）。
- **静态托管**：
  - `/static` → `app/static/`（构建产物区，2D 原生 `index.html` 已删除）
  - `/3d/assets`、`/3d/office-assets` → `app/static/3d/`（Vite 构建产物）
  - **`/` → 3D SPA**：`index()` 返回 `app/static/3d/index.html`（原 2D 对话页已归档到 `_archive/2d-legacy/`）；若 3D 未构建则 404 提示 `cd frontend && npm run build`
  - `/3d`、`/3d/{path}` → 3D SPA（fallback 到 index.html，支持 `/3d/scene`、`/3d/login`、`/3d/dashboard` 客户端路由）

## 对外接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/chat` | 无（匿名 user_id） | 对话点单主入口；返回回复 + 可选 order_id。**当前由 3D 场景内嵌聊天消费**（独立 2D 页已归档） |
| POST | `/agents/register` | 无 | 注册 Agent，返回 api_token（明文一次性）+ sprite_seed |
| POST | `/agents/{id}/heartbeat` | Agent token | 心跳，更新 last_seen_at |
| POST | `/agents/{id}/actions` | Agent token | 上报动作（enter_scene/take_order/...） |
| GET | `/agents` | 无 | 列出活跃 Agent |
| POST | `/skill/register` | 无 | 注册 EvoMap 消费者 + Agent，返回免费额度 |
| POST | `/skill/orders` | Agent token + 可选 X-Evomap-Node-Secret | A2A 点单；返回 402 表示需积分支付 |
| GET | `/visualization/events` | 无 | 拉取最近事件（limit ≤ 200） |
| GET | `/admin/restaurant-state` | 无 | 大屏聚合状态（今日订单/金额/来源/最近订单/事件/Agent） |
| WS | `/ws/visualization` | 无 | 实时事件流；连接即推 `scene.snapshot`；支持 presence.move/leave + ping/pong |
| POST | `/auth/register` `/login` `/logout` | Cookie | 账户会话（httpOnly 签名 Cookie） |
| GET | `/auth/me` | Cookie | 当前登录账户 |
| GET | `/user/{id}` `/orders/{id}` `/history/{id}` | 无 | 用户/订单/对话历史查询 |
| DELETE | `/history/{id}` | 无 | 清空对话历史 |
| GET | `/status` | 无 | 数据库/LLM 配置状态 |

**Agent token 鉴权**：`_require_agent()` 校验 `Authorization: Bearer <token>` 或 `X-Agent-Token`，对比 `api_token_hash`（SHA-256）。

## 关键依赖与配置

- **Web 框架**：FastAPI + Uvicorn（`requirements.txt`）
- **ORM**：SQLAlchemy 2.0（`declarative_base`，`pool_pre_ping` + `pool_recycle=3600`）
- **数据库**：MySQL 8.0（`mysql+pymysql`，唯一支持的持久化后端）
- **缓存/记忆**：Redis（短期对话历史 List + 待确认订单 String）
- **LLM**：OpenAI 兼容协议，用 `httpx` 直连（**非** openai SDK，避免版本冲突）；429 自动重试 1 次
- **EvoMap 支付**：用标准库 `urllib.request` 直连（`evomap_payment_service.py`，非 httpx），`x-correlation-id=request_id`
- **分词**：jieba（中文关键词 RAG）
- **认证**：passlib[bcrypt] + itsdangerous（签名 Cookie）
- **配置**：`app/config.py` 用 `pydantic-settings` 从 `.env` 读取；`effective_llm_api_key` 按优先级选 `LLM_API_KEY > DEEPSEEK_API_KEY > OPENAI_API_KEY`，过滤 placeholder。

## 数据模型（`app/db/models.py`，15 张表）

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
| `agent_profile` | 外部 Agent 身份 | tool_name, role_type, api_token_hash, sprite_seed, status |
| `evomap_consumer` | EvoMap 消费者（A2A 点单主体） | evomap_node_id(unique), free_orders_used, local_user_id |
| `skill_order_ledger` | A2A 点单账本（幂等 + 支付凭证） | request_id(unique), amount_credits, payment_status, order_ids_json, evomap_order_id, payment_proof_json, coffee_items_json |
| `user_wallet` | 用户钱包（credits 等多币种） | user_id, currency, ... |
| `balance_transaction` | 钱包流水（consume/free_order 等） | user_id, currency, type_, amount, order_id, ledger_id, correlation_id, note |
| `visualization_event` | 可视化事件流（持久化） | event_type, payload_json, correlation_id, agent_id |

**CHECK 约束**：order.source_type / status / payment_status、agent/consumer.status、ledger.payment_status 都用域常量（`app/domain_constants.py`）做数据库级校验。`WALLET_CURRENCY_CREDITS = "credits"`（`domain_constants.py:88`）。

> 说明：本次扫描在 `models.py` 实测 15 个 `class X(Base)`。`order_item`/`product`/`user_wallet`/`balance_transaction` 是 Skill 点单落库（`_complete_order` 写 order_item + decrement_stock + wallet_service.apply_transaction）与新目录体系引入的，老文档仅记 8 表，已校正。

## 核心流程

### `/chat` 对话点单决策树（`app/main.py`）
```
1. 查看订单意图？(_is_order_view_query) → 返回订单列表
2. 读 Redis 历史 + 待确认订单(pending)
   ├─ 有 pending 且 _is_confirming → place_orders 扣款 + 发布完成流事件
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

_resume_existing_order(幂等恢复，三态):
  FREE/PAID                       → _success_response("幂等重试：订单已完成")（不改库）
  PAYMENT_REQUIRED/FAILED/PENDING → 客户端 payment_proof 仍拒；无 node_secret 抛 402；有则重新 _charge_evomap_and_complete
  其余                            → SkillOrderError("订单账本状态不可恢复", code=ledger_not_resumable)

_complete_order(落库 + 钱包镜像):
  按 request_id[:index] 幂等建/复用 Order 行；fresh 订单写 OrderItem + decrement_stock（catalog_service）
  免费：consumer.free_orders_used = max(old, seq)（防回退）；wallet_service.apply_transaction(type=free_order, amount=0)
  付费：wallet_service.apply_transaction(type=consume, amount=-amount_credits)（EvoMap 扣款镜像）
  发 restaurant.* 完整流程链(payment_completed→grinding→brewing→plating→order_ready→order_delivered→customer_reviewed→customer_left)
```

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
- 后端相关测试：`test_chat_confirm.py`、`test_chat_order_view.py`、`test_skill_evomap_payment.py`、`test_llm_configuration.py`
- 种子数据：`app/db/seed.py`（5 款咖啡 + user_id=1 测试顾客，余额 100）
- 迁移脚本：`scripts/migrate_order_sources.py`、`scripts/migrate_user_accounts.py`（幂等，不删数据）

## 常见问题 (FAQ)

- **Q: LLM 没配 key 会怎样？** A: `llm.has_real_key()=False`，`chat()` 走 `_mock_chat`（直接用 RAG 结果拼推荐），`parse_intent()` 走硬编码兜底词。`/status` 会显示 `llm_status_reason`。
- **Q: 为什么 LLM 不用 openai SDK？** A: 见 `app/llm/client.py` 顶部注释——避免 SDK 与 httpx 版本冲突，改用 httpx 直连 `/chat/completions`。
- **Q: 为什么 EvoMap 支付用 urllib 而非 httpx？** A: `evomap_payment_service.py` 用标准库 `urllib.request`，避免给支付链路引入额外异步/依赖耦合，错误映射集中在 `_message_for_status/_code_for_status/_http_status_for_upstream`。
- **Q: 待确认订单怎么避免误下单？** A: `_is_confirming()` 三层判定：否定/疑问词优先否决 → 强确认词（确认/下单/扣钱）长句也算 → 弱确认词（好/对/行）仅纯短句 startswith。
- **Q: Skill 点单的支付凭证能客户端传吗？** A: 不能。`_reject_unverified_payment_proof` 会拒绝客户端 payment_proof，要求传 `X-Evomap-Node-Secret` 由后端发起官方 service order。
- **Q: Colyseus 启动会失败吗？** A: 不会报错。`colyseus-server/` 已归档到 `_archive/`，`colyseus_bridge.py` 检测目录缺失后仅记 warning 并跳过，FastAPI 正常启动。如需恢复像素方案，把 `_archive/colyseus-server/` 移回根目录即可。
- **Q: 访问 `/` 看到 3D 还是 2D？** A: 3D SPA。原 2D 对话页（`app/static/index.html`）已归档到 `_archive/2d-legacy/index.html`，根路由 `index()` 现直出 `app/static/3d/index.html`。

## 相关文件清单

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI 入口，所有路由 + `/chat` 决策树 + 静态/3D 托管 + Colyseus 生命周期挂载 |
| `config.py` | pydantic-settings 配置 |
| `domain_constants.py` | 订单/支付/身份/钱包状态枚举（数据库 CHECK 约束来源） |
| `colyseus_bridge.py` | Colyseus 子进程生命周期管理（**目标已归档，启动为 no-op**） |
| `db/database.py` | engine + SessionLocal + Base |
| `db/models.py` | 15 张 SQLAlchemy 表 |
| `db/seed.py` | 种子数据 |
| `services/chat_service.py` | RAG 聊天主流程 + 价格匹配 |
| `services/order_service.py` | 事务安全扣款下单（with_for_update） |
| `services/skill_order_service.py` | A2A Skill 点单全流程（幂等恢复 + 钱包镜像 + 完成流事件链） |
| `services/evomap_payment_service.py` | EvoMap 积分 service-order 支付客户端（urllib + 脱敏 + 多键 order_id 抽取） |
| `services/visualization_service.py` | Agent token 工具 + VisualizationHub（WebSocket 广播） |
| `services/wallet_service.py` | credits 钱包流水（apply_transaction：consume/free_order 等） |
| `services/catalog_service.py` | 商品目录 + 库存递减（decrement_stock） |
| `llm/client.py` | OpenAI 兼容 LLM 客户端（chat + parse_intent） |
| `rag/keywords.py` | jieba 关键词提取（正向 + 负向 + 同义词） |
| `rag/retrieval.py` | LIKE 召回 + NOT LIKE 过滤 |
| `memory/chat_history.py` | Redis 对话历史 + 待确认订单 |
| `auth/router.py` | /auth/* 路由 |
| `auth/service.py` | bcrypt + itsdangerous 会话 |
