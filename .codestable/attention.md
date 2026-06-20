# Attention

本文件是 CodeStable 技能启动必读的项目注意事项入口。所有 CodeStable 子技能开始工作前必须读取它。

## 项目碎片知识

<!-- cs-note managed: 用 cs-note 维护，新条目按下面分节追加 -->

### 编译与构建

### 运行与本地起服务

### 测试

### 命令与脚本陷阱

### 路径与目录约定

- 仓库根目录存在 `.codegraph/` 时，理解或定位本地代码优先使用 CodeGraph；MCP 工具不可用时使用 `codegraph explore "<question>"` 或 `codegraph node <symbol-or-file>`。
- 本项目核心运行边界：`app/main.py`、`app/db/models.py`、`app/db/database.py`、`app/memory/chat_history.py`、`app/services/order_service.py`、`app/services/skill_order_service.py`、`app/services/visualization_service.py`、`app/static/`、`.agents/skills/a2a-super-order/`。
- MySQL 是唯一关系型数据库；Redis 是唯一短期记忆/中间件后端。不要新增 SQLite、fakeredis、内存 fallback 或对应示例。
- `order` 是 web dialog 与 A2A Skill 两条路径共享的订单事实表；`source_type`、`payment_status`、`consumer_url`、`consumer_id`、`agent_id`、`ledger_id`、`correlation_id` 与时间戳需要在 SQLAlchemy 模型和 MySQL DDL 之间保持一致。
- 既有 MySQL schema 升级必须走 `scripts/migrate_order_sources.py`，并保持幂等、可重复运行。

### 环境变量与凭证

- MySQL、Redis、API key、token、完整连接串等凭证不得写入代码、文档、日志、页面或最终回复。
- MySQL 和 Redis 连接信息必须来自 `.env` 的 `MYSQL_*` 与 `REDIS_*` 配置；不要在 `.mcp.json` 或 wrapper 脚本中硬编码凭证。
- 使用 `coffee-mysql`、`coffee-redis` 检查连接时，只报告 host/database/type/status 等非敏感信息。

### 其他
