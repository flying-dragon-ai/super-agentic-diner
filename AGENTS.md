<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- When reading local code, prefer CodeGraph whenever practical to reduce token usage.
- **MCP tools** (when available): `codegraph_explore` answers most code questions in one call - the relevant symbols' verbatim source plus the call paths between them. `codegraph_node` returns one symbol's source + callers, or reads a whole file with line numbers. If the tools are listed but deferred, load them by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` and `codegraph node <symbol-or-file>` print the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely - indexing is the user's decision.
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

Coffee AI Boss is a FastAPI application with static HTML/CSS/JS frontends, SQLAlchemy ORM, MySQL 8 persistence, Redis 7 short-term memory, A2A Skill/EvoMap ordering integration, and a WebSocket visualization event stream.

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

- MySQL is the only supported relational database. Do not add SQLite modes, SQLite examples, SQLite branches, or SQLite-specific schema variants.
- Redis is the only supported memory/middleware backend. Do not add fakeredis, in-memory Redis fallbacks, or fake memory modes.
- MySQL and Redis connection details must come from `.env` through the `MYSQL_*` and `REDIS_*` settings. Do not hard-code connection strings, passwords, tokens, or secrets in code, docs, logs, or pages.
- `Base.metadata.create_all()` may initialize new MySQL databases, but existing MySQL schema changes must use explicit idempotent migration scripts.
- The web dialog ordering path and A2A Skill/EvoMap ordering path share persisted orders/events, but their payment logic remains separate unless explicitly requested.
- `order` is the canonical order fact table for both `web_dialog` and `skill` sources. Keep `source_type`, `payment_status`, `consumer_url`, `consumer_id`, `agent_id`, `ledger_id`, `correlation_id`, and timestamps aligned between SQLAlchemy models and MySQL DDL.
- `order.consumer_id`, `order.agent_id`, and `order.ledger_id` are strict MySQL foreign keys. Do not weaken them into loose references without an explicit architecture decision.
- Domain state values such as order source, order status, identity status, and payment status live in `app/domain_constants.py`; do not introduce ad hoc string values in service code or migrations.
- Existing MySQL schema upgrades must go through `scripts/migrate_order_sources.py`, which is expected to be idempotent and safe to run more than once.
<!-- PROJECT_ARCHITECTURE_END -->
