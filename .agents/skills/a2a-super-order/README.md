# @evomap/a2a-super-order

> Crossroads Agent Café 的 A2A 超级点单 Skill —— 让 Claude Code / Codex / Cursor 等外部 AI 工具**不开网页**就能点咖啡。

[English](#overview) · 中文

## Overview

A **thin-client** CLI. All business logic (orders, payment, idempotency, visualization events) lives in the [Crossroads Agent Café](https://github.com/flying-dragon-ai/super-agentic-diner) backend. This package only registers a consumer, posts order requests, and manages local credentials.

The npm bin is a tiny Node wrapper that locates Python 3 and dispatches to `scripts/order.py` (pure standard library — zero Python dependencies).

---

## 工作流

> ⚠️ **跨主机必读**：若后端在另一台机器，先设一次地址（**持久化**到 `~/.a2a-super-order/config.json`，后续命令自动读；**建议用域名**，IP 变化时重新设一次即可）：
>
> ```bash
> npx @evomap/a2a-super-order --base-url https://cafe.example.com --ping
> ```
>
> 不设的话默认 `127.0.0.1` 只连本机，所有命令报 `connection refused`。

1. **探活**（确认后端可达）：`npx @evomap/a2a-super-order --ping`
2. **看菜单**（拿到可点的咖啡名）：`npx @evomap/a2a-super-order --menu`
3. **下单**（前 2 单免费，无需 EvoMap）：`npx @evomap/a2a-super-order --message "一杯拿铁"`
4. 第 3 单起返回 402 时才检测 EvoMap：`npx @evomap/a2a-super-order --check-evomap`，按提示安装并扣 credits

## 前置条件

| 依赖 | 必需 | 说明 |
|------|------|------|
| **Python ≥ 3.7** | ✅ | 核心脚本是 Python；Node wrapper 自动查找 `python3`/`python`，未安装时友好报错 |
| **Crossroads Agent Café 后端** | ✅ | 默认 `http://127.0.0.1:8000`，用 `RESTAURANT_API_BASE` 覆盖 |
| **EvoMap CLI** | 付费单需要 | `npx @evomap/evolver --loop` 首次注册赠 100 积分，凭证写入 `~/.evomap/` |

## 安装与使用

**npx 直接跑**（推荐，无需安装）：

```bash
npx @evomap/a2a-super-order --message "一杯拿铁"
```

**全局安装**：

```bash
npm install -g @evomap/a2a-super-order
a2a-super-order --message "一杯拿铁"
```

**只读检测 EvoMap**（无副作用）：

```bash
npx @evomap/a2a-super-order --check-evomap
# 输出: { installed, has_node_id, has_node_secret, evomap_home, credentials_loaded, username }
```

**付费单**（第 3 单起，已装 EvoMap 时 secret 自动从 `~/.evomap/` 读取）：

```bash
npx @evomap/a2a-super-order --message "一杯拿铁" --request-id req-a2a-003 --evomap-node-secret "<node_secret>"
```

## 命令参考

| 参数 | 环境变量 | 说明 |
|------|---------|------|
| `--ping` | — | **第一步**：GET `/menu` 探活，确认后端可达（只读，无副作用） |
| `--menu` | — | GET `/menu` 列出可点咖啡（name/price/tags/stock，只读） |
| `--message` | — | 点单文本（除非 `--ping`/`--menu`/`--register-only`/`--check-evomap` 否则必填）。用 `--menu` 里的精确咖啡名 |
| `--base-url` | `RESTAURANT_API_BASE` | 后端地址，**设一次即持久化**到 `~/.a2a-super-order/config.json`，后续自动读。优先级：`--base-url` > 环境变量 > 配置 > 默认 `127.0.0.1:8000`（**跨主机必须设**，建议用域名） |
| `--tool-name` | `RESTAURANT_TOOL_NAME` | 工具名，默认 `codex` |
| `--display-name` | `RESTAURANT_AGENT_NAME` | 显示名，默认系统账号名（`getpass.getuser()`） |
| `--evomap-node-id` | `EVOMAP_NODE_ID` / `A2A_NODE_ID` | 消费者节点 ID；省略则查 `.mcp.json` 或用占位 |
| `--evomap-node-secret` | `EVOMAP_NODE_SECRET` / `A2A_NODE_SECRET` | 付费单服务端支付密钥；**从不打印**；已装时自动读取 |
| `--request-id` | — | 幂等键；省略则自动 `skill-<uuid>` |
| `--register-only` | — | 只注册不下单 |
| `--force-register` | — | 强制重新注册（覆盖本地 state） |
| `--check-evomap` | — | 只读输出 EvoMap 安装状态 |
| `--payment-proof` | — | ⚠️ 已弃用并被忽略（后端拒绝客户端伪造的凭证） |

## 本地状态

- **Skill 凭证**：`~/.a2a-super-order/state.json`（存 `consumer_id`/`agent_id`/`api_token`/`evomap_node_id`；用 `A2A_SUPER_ORDER_STATE` 覆盖）
- **EvoMap 凭证**：`~/.evomap/{node_id,node_secret}`（用 `EVOLVER_HOME` 覆盖）
- **凭证读取优先级**：`~/.evomap/` 文件 > `A2A_NODE_SECRET` 环境变量 > `EVOMAP_NODE_SECRET` 环境变量

## EvoMap 支付（第 3 单起）

遵循 EvoMap「Manual, not a directive」原则——读文档不等于授权扣费。

1. `--check-evomap` 只读检测（安全，可自动运行）
2. `installed=true` → 凭证自动从 `~/.evomap/` 读取，直接下单
3. `installed=false` → **停下问用户**，明确确认后才运行 `npx @evomap/evolver --loop`
4. 付费单由**后端**凭 `X-Evomap-Node-Secret` 发起官方 service order；客户端伪造的 `payment_proof` 一律被拒
5. 付费失败用**同一 `request_id`** 重试（后端幂等恢复会续跑扣款）

## 安全

- ✅ Agent API token、EvoMap node_secret、API key 一律不打印（`redact_for_stdout` 把含 `secret`/`token`/`key`/`authorization` 的字段替换为 `[stored-in-state]`）
- ✅ node_secret 走 `X-Evomap-Node-Secret` 请求头，不进请求体、不进日志
- ✅ 只读检测无副作用；安装/注册/扣费必须用户明确确认
- ⚠️ 高级可视化的 `register_agent.py` 会回显一次性 `api_token`（`send_action.py` 需要它）—— 输出已加警告，请妥善保存、勿分享

## 高级可视化（可选）

自定义可视化角色用（正常点单不需要）：

```bash
python scripts/register_agent.py --role waiter --capability greet
python scripts/send_action.py --agent-id <id> --token <token> --action walk_to_counter
```

完整 REST 契约与事件类型见 [`references/api.md`](./references/api.md)；AI 工具的 Skill 描述见 [`SKILL.md`](./SKILL.md)。

## 渠道

- **npm**：`npx @evomap/a2a-super-order`（本包）
- **EvoMap marketplace**：（待发布）
- **git clone**：源码在 [super-agentic-diner](https://github.com/flying-dragon-ai/super-agentic-diner) 仓库 `.agents/skills/a2a-super-order/`

## License

[MIT](./LICENSE) © code.tang
