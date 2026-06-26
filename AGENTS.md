<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tools** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them. `codegraph_node` returns one symbol's source + callers, or reads a whole file with line numbers. If the tools are listed but deferred, load them by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` and `codegraph node <symbol-or-file>` print the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

<!-- MCP_TOOLING_START -->
## MCP Tooling

The project MCP configuration lives in `.mcp.json` and currently exposes three local servers: `codegraph`, `coffee-mysql`, and `coffee-redis`.

General rules:

- Do not write database passwords, Redis passwords, API keys, tokens, or full connection strings into code, docs, logs, pages, or final responses.
- `coffee-mysql` and `coffee-redis` are configured with `permission-mode full`, but default to read-only inspection unless the user explicitly asks for a write, cleanup, migration, or destructive operation.
- Connection details must come from `.env`; never replace the wrapper scripts with hard-coded credentials in `.mcp.json`.
- When testing connectivity, report only host/database/type/status details. Redact or omit secrets.

### codegraph

Use `codegraph` first when you need to understand or locate local code and `.codegraph/` exists at the repository root.

- MCP server name: `codegraph`
- `.mcp.json` command: `codegraph serve --mcp`
- Preferred use: symbol lookup, caller/callee exploration, call-path tracing, and reading indexed source with line numbers.
- If MCP CodeGraph tools are unavailable, use the shell fallback:
  - `codegraph explore "<symbol names or question>"`
  - `codegraph node <symbol-or-file>`
- Use filesystem tools such as `rg` after CodeGraph when you need exhaustive text matches, static assets, config files, SQL/XML/resource files, or files outside the symbol index.

### coffee-mysql

Use `coffee-mysql` for the real Coffee AI Boss MySQL database.

- MCP server name: `coffee-mysql`
- Database type: MySQL
- Expected database: `coffee_ai`
- Startup wrapper: `.agents/scripts/start-coffee-mysql-mcp.ps1`
- Required `.env` keys: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
- Typical read tools: `get_connection_status`, `get_schema`, `get_table_info`, `get_sample_data`, `get_enum_values`, `execute_query`
- Connectivity probe: call `get_connection_status`, then run a minimal read such as `SELECT DATABASE(), 1`.

Use this server when verifying SQLAlchemy model/schema alignment, inspecting orders/events persisted by the web dialog path or A2A Skill path, checking migration effects, or validating user-visible behavior against persisted MySQL data.

### coffee-redis

Use `coffee-redis` for the real Coffee AI Boss Redis memory backend.

- MCP server name: `coffee-redis`
- Database type: Redis
- Expected database: `0` unless `.env` sets `REDIS_DB`
- Startup wrapper: `.agents/scripts/start-coffee-redis-mcp.ps1`
- Required `.env` keys: `REDIS_HOST`, `REDIS_PORT`
- Optional `.env` key: `REDIS_PASSWORD`
- Typical read tools: `get_connection_status` and `execute_query` for Redis commands supported by `universal-db-mcp`
- Connectivity probe: call `get_connection_status`, then run a minimal Redis read command such as `PING`.

Use this server when inspecting chat history, pending-order memory, short-term workflow state, or Redis-backed runtime behavior. Avoid broad key scans in large datasets; prefer narrow key patterns derived from the application code.
<!-- MCP_TOOLING_END -->

<!-- PROJECT_ARCHITECTURE_START -->
## Project Architecture

Coffee AI Boss is a FastAPI application with static HTML/CSS/JS frontends, SQLAlchemy ORM, SQLite/MySQL persistence, fakeredis/Redis short-term memory, A2A Skill/EvoMap ordering integration, and a WebSocket visualization event stream.

Core runtime boundaries:

- Backend API: `app/main.py`
- SQLAlchemy models: `app/db/models.py`
- Database engine/session: `app/db/database.py`
- Redis chat and pending-order memory: `app/memory/chat_history.py`
- Web dialog order service: `app/services/order_service.py`
- A2A Skill order service: `app/services/skill_order_service.py`
- Visualization event service: `app/services/visualization_service.py`
- Static UI assets: `app/static/`
- A2A Skill entrypoint: `.agents/skills/a2a-super-order/`

Architecture constraints:

- **DB_MODE(数据库模式) 双后端支持**：默认 `sqlite`(本地文件数据库) 零配置运行，设 `DB_MODE=mysql` 切回 MySQL(关系型数据库)。两种模式共用同一套 SQLAlchemy ORM(对象关系映射)，models.py 不含 dialect(方言) 专属分支。
- **USE_FAKEREDIS(启用模拟Redis) 双后端支持**：默认 `true` 使用 fakeredis(进程内模拟Redis) 零配置运行，设 `USE_FAKEREDIS=false` 切回真实 Redis(缓存中间件)。两种模式通过 `app/memory/_redis_client.py` 统一分发，chat_history(对话历史) 和 experience_agent(经验继承) 共享同一 FakeServer(模拟服务端)。
- MySQL 和 Redis 连接详情必须来自 `.env` 通过 `MYSQL_*` 和 `REDIS_*` 设置。不要在代码、文档、日志、页面中硬编码连接串、密码、token(令牌)、密钥。
- `Base.metadata.create_all()` 可初始化新数据库（SQLite 或 MySQL）；现有 MySQL schema(数据结构) 变更必须使用显式的幂等迁移脚本。
- web(网页) 对话下单路径和 A2A Skill/EvoMap 下单路径共享持久化的订单/事件，但支付逻辑保持独立，除非明确要求合并。
- `order`(订单表) 是 `web_dialog`(网页对话) 和 `skill`(技能) 两种来源的规范订单事实表。保持 `source_type`、`payment_status`、`consumer_id`、`agent_id`、`ledger_id`、`correlation_id` 和时间戳在 SQLAlchemy models(数据模型) 和 DDL(数据定义语言) 之间对齐。
- `order.consumer_id`、`order.agent_id`、`order.ledger_id` 是严格的外键。不要在没有明确架构决策的情况下将它们弱化为松散引用。
- 领域状态值（如订单来源、订单状态、身份状态、支付状态）定义在 `app/domain_constants.py`；不要在 service(服务) 代码或迁移中引入临时字符串值。
- 现有 MySQL schema(数据结构) 升级必须通过 `scripts/migrate_order_sources.py`，该脚本预期幂等且可安全多次运行。
<!-- PROJECT_ARCHITECTURE_END -->
