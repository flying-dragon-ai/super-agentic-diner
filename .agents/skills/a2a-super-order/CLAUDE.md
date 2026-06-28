[根目录](../../../CLAUDE.md) > [.agents](../../) > [skills](../) > **a2a-super-order**

# .agents/skills/a2a-super-order/ — A2A 超级点单 Skill

## 变更记录 (Changelog)

| 时间 | 动作 | 说明 |
|------|------|------|
| 2026-06-28 | 成功率优化（指令 + 脚本 + base_url 持久化） | 针对"另一台电脑上的 AI 工具用 Skill 下单"场景的失败点优化。① `order.py` 新增 `--ping`（GET `/menu` 探活，失败给三路排查 hint：改 `RESTAURANT_API_BASE`/起 `uvicorn`/开端口 8001）+ `--menu`（列可点咖啡 name/price/tags/category/stock，根治"不知道能点什么"）；新增 `--base-url` **持久化**到 `~/.a2a-super-order/config.json`（显式传入即写入，后续命令自动读，IP/域名变更时重新设一次；优先级 `--base-url` > `RESTAURANT_API_BASE` 环境变量 > 配置 > 默认，应对后端部署地址变更，**建议生产用域名**）。② `main()` 强制 stdout/stderr UTF-8（修 Windows GBK 终端中文乱码导致外部 AI 工具按 UTF-8 捕获解析失败）。③ SKILL.md 重写为决策树（Step0 `--ping` → Step1 `--menu` → Step2 下单 → Step3 仅第 3 单返回 402 才走 EvoMap），纠正"一上来就 `--check-evomap` 被卡"的流程错误；首屏加粗警告"跨主机必须设 `RESTAURANT_API_BASE=http://192.168.110.87:8001`"（默认 `127.0.0.1` 在外部机器 100% 连不上）；明确 `--message` 用 `--menu` 精确咖啡名 + 结果字段解读 + 失败恢复决策树。④ README.md/api.md 同步。⑤ 端到端验证通过：真实 uvicorn + 真实 urllib HTTP，14 款咖啡菜单 `--ping`/`--menu` 成功分支字段全部命中 |
| 2026-06-21 09:55 | 增量校验（第九次 init） | **一致性校验**（仅文档，对照 HEAD `031608f`）：修正参数表 `--display-name` 默认值描述——原写"默认 `Codex Consumer`"，与 `order.py:254` 实际代码 `default=os.getenv("RESTAURANT_AGENT_NAME") or detect_username()` 不符（已在 2026-06-21 01:47 改为 `detect_username()`，但参数表漏改），本次校正。其余内容经校验准确（`detect_username`/`detect_evomap_install`/`load_evomap_credentials`/`--check-evomap`/安全红线/凭证优先级均与代码一致），保持不动 |
| 2026-06-21 01:47 | 增量刷新 | **`order.py --display-name` 默认改 `detect_username()`**（原先默认 `"Codex Consumer"`）。让平台显示的 Skill 顾客名 = 该机器系统账号名（对齐"登录名=上传的名字"要求），环境变量 `RESTAURANT_AGENT_NAME` 仍可覆盖。配合后端在线用户模型（Skill 用户经 `agent.last_seen_at` 心跳窗口 120s 显示在线，见 app/CLAUDE.md「在线用户显示模型」） |
| 2026-06-20 14:08 | 创建 | 初始化架构师首次生成。对齐本次 skill 改造：`order.py` 新增 `detect_username`（`getpass.getuser()`，跨平台系统账号名）/`detect_evomap_install`（只读检测 `~/.evomap/`）/`load_evomap_credentials`（文件优先 > 环境变量）/`--check-evomap` 子命令；`SKILL.md` 新增 "EvoMap Installation Check"（未装→AI 二次确认后 `npx @evomap/evolver --loop`）+ NPX 安装说明 + 安全红线；`references/api.md` 同步 `--check-evomap` 文档 |

---

## 模块职责

这是 Crossroads Agent Café 对外**唯一**的 A2A Skill，供外部 AI 工具（Claude Code / Codex / Cursor / Trae / 其他）在**不打开网页**的情况下点单。它是一组**瘦客户端脚本**（thin client）：注册消费者、下点单请求、消费前 2 单免费额度、第 3 单起通过后端发起 EvoMap `gep-a2a` 协议扣 credits。**所有业务逻辑（扣款、订单、幂等恢复、可视化事件）都在后端**（`app/services/skill_order_service.py`、`app/services/evomap_payment_service.py`），本模块只负责拼请求 + 管本地凭证状态。

核心定位（2026-06-20 改造后）：
1. **自动识别系统账号名**（macOS `$USER` / Windows `%USERNAME%`，非 hostname）。
2. **只读检测 EvoMap 是否安装**（读 `~/.evomap/{node_id,node_secret}` 是否存在，无副作用）。
3. **已装则自动读凭证支付**（优先 `~/.evomap/` 文件，回退环境变量）。
4. **未装则引导用户二次确认后下载**（`npx @evomap/evolver --loop`），绝不自动安装。

## 入口与启动

- **入口脚本**：`scripts/order.py`（CLI，argparse）
- **运行**：`python .agents/skills/a2a-super-order/scripts/order.py --message "<点单文本>"`
- **默认 Base URL**：`http://192.168.110.87:8001`（由 `RESTAURANT_API_BASE` 覆盖）
- **本地状态文件**：`~/.a2a-super-order/state.json`（存 consumer_id/agent_id/api_token/evomap_node_id；由 `A2A_SUPER_ORDER_STATE` 覆盖）
- **后端地址配置**：`~/.a2a-super-order/config.json`（存 `base_url`，`--base-url` 显式传入时持久化、后续命令自动读；由 `A2A_SUPER_ORDER_CONFIG` 覆盖。应对后端部署 IP/域名变更——设一次即可，建议生产用域名）
- **EvoMap 凭证根目录**：`EVOLVER_HOME` 环境变量 → 否则 `~/.evomap/`（含 `node_id`、`node_secret` 文件）

## 对外接口（调用后端的契约）

本脚本调用的后端路由（完整契约见 `references/api.md`）：

| 子命令 / 动作 | 后端路由 | 说明 |
|--------------|---------|------|
| 注册消费者 | `POST /skill/register` | tool_name/display_name/evomap_node_id/capabilities；返回 consumer_id/agent_id/api_token（一次性）/free_orders_remaining |
| 点单 | `POST /skill/orders` | 需 `Authorization: Bearer <api_token>`；付费单额外带 `X-Evomap-Node-Secret`；402=需积分支付 |
| EvoMap 扣款（后端发起） | `POST {EVOMAP_HUB_URL}/a2a/service/order` | 后端直连，非本脚本调用；本脚本只传 node_secret |
| 高级可视化（可选） | `POST /agents/register`、`/agents/{id}/actions` | 仅自定义角色用，正常点单不走 |

## 命令行参数（`order.py`）

| 参数 | 环境变量 | 说明 |
|------|---------|------|
| `--base-url` | `RESTAURANT_API_BASE` | 后端地址，**显式传入即持久化**到 `~/.a2a-super-order/config.json`，后续命令自动读。优先级：`--base-url` > `RESTAURANT_API_BASE` > 配置 > 默认 `192.168.110.87:8001`（跨主机/部署 IP 变更场景用，建议域名） |
| `--tool-name` | `RESTAURANT_TOOL_NAME` | 工具名，默认 `codex` |
| `--display-name` | `RESTAURANT_AGENT_NAME` | 显示名，默认 `detect_username()`（系统账号名，2026-06-21 01:47 改；原 `"Codex Consumer"`） |
| `--evomap-node-id` | `EVOMAP_NODE_ID` / `A2A_NODE_ID` | 消费者节点 ID；省略则查 `.mcp.json` 或用 local-unregistered 占位 |
| `--evomap-did` | `EVOMAP_DID` | 可选 DID |
| `--evomap-node-secret` | `EVOMAP_NODE_SECRET` / `A2A_NODE_SECRET` | 付费单服务端支付密钥；已装 EvoMap 时自动从 `~/.evomap/` 读取，无需手传。**从不打印** |
| `--message` | — | 点单文本（除非 `--register-only`/`--check-evomap` 否则必填） |
| `--request-id` | — | 幂等键；省略则自动 `skill-<uuid>` |
| `--payment-proof` | — | **已弃用**：后端拒绝客户端伪造的支付凭证 |
| `--force-register` | — | 强制重新注册（覆盖本地 state） |
| `--register-only` | — | 只注册不下单 |
| `--ping` | — | **第一步**：GET `/menu` 探活，确认后端可达（只读，无副作用；2026-06-28 新增） |
| `--menu` | — | GET `/menu` 列出可点咖啡 name/price/tags/stock（只读；2026-06-28 新增） |
| `--check-evomap` | — | **只读**输出 EvoMap 安装状态 JSON，无副作用 |

## 关键函数（`scripts/order.py`）

| 函数 | 职责 |
|------|------|
| `detect_username()` | 跨平台系统账号名。优先 `getpass.getuser()`，异常回退 `os.getenv("USER")`/`"USERNAME"`。**注意：不是 hostname**（旧代码误用 `platform.node()`，已修） |
| `fetch_menu(base_url)` | GET `{base_url}/menu` 只读探活 + 菜单探测，返回 `(ok, data, error)`。`/menu` 匿名可读，200 即证明后端可达且可点单（2026-06-28 新增） |
| `cmd_ping(args)` | `--ping` 子命令：调 `fetch_menu`，成功输出 `{ok:true, base_url, status:reachable, menu_count, sample}`，失败输出 `{ok:false, ..., hint}`（三路排查：改 base_url/起 uvicorn/开端口 8001）（2026-06-28 新增） |
| `cmd_menu(args)` | `--menu` 子命令：调 `fetch_menu`，输出 `{base_url, count, items:[{name,price,tags,category,stock}]}`，让 AI 工具拿到精确咖啡名用于 `--message`（2026-06-28 新增） |
| `detect_evomap_install()` | 只读检测 `~/.evomap/{node_id,node_secret}` 是否存在。返回 `{installed, has_node_id, has_node_secret, evomap_home, node_id_path, node_secret_path}`。**无写盘/无网络/无子进程** |
| `load_evomap_credentials()` | 凭证加载，优先级：`~/.evomap/` 文件 > `A2A_NODE_SECRET`/`A2A_NODE_ID` 环境变量 > `EVOMAP_NODE_SECRET`/`EVOMAP_NODE_ID` 环境变量。返回 `{node_id, node_secret}` 或 `None` |
| `detect_mcp_node_id(root)` | 从 `.mcp.json` 的 `mcpServers.*.env.EVOMAP_NODE_ID/A2A_NODE_ID` 提取 node_id |
| `detect_node_id(root, explicit)` | node_id 解析：explicit > 环境变量 > `.mcp.json` > `local-unregistered-<hostname>` 占位（用于免费单测试） |
| `register_if_needed(...)` | 注册消费者；**接入凭证自动读取**——有 `load_evomap_credentials()` 则用真实 node_id 并把 secret 填入 `args.evomap_node_secret`，否则走 local-unregistered 占位 |
| `submit_order(...)` | 发 `/skill/orders`；402 且 `status=payment_required` 时打印引导信息并退出（提示设 `EVOMAP_NODE_SECRET`/`A2A_NODE_SECRET` 或传 `--evomap-node-secret`，同一 `request_id` 重试） |
| `redact_for_stdout(value)` | 递归脱敏：dict 的 key 含 `secret/token/key/authorization` → `[stored-in-state]`，防止 token/secret 泄漏到终端 |
| `request_json(...)` | urllib 通用 POST 封装（标准库，非 httpx），HTTPError 转成 `ApiError(status, body)` |

## 安全红线（来自 `SKILL.md` Rules）

- **只读检测安全**：`--check-evomap` 只读文件，可自动运行。
- **写入/安装/扣款必须二次确认**：`npx @evomap/evolver --loop`（首次注册）和传 `--evomap-node-secret`（扣 credits）都**禁止自动执行**，必须先问用户并得到明确确认（"是"/"确认"/"yes"）。
- **不打印密钥**：Agent API token、EvoMap node_secret、API key、`.env` 密钥一律不打印；脚本自动用 `redact_for_stdout` 把含 `secret/token/key/authorization` 的 key 替换为 `[stored-in-state]`。
- **客户端 payment_proof 被拒**：后端 `_reject_unverified_payment_proof` 不接受客户端伪造的支付凭证，付费必须由后端凭 `X-Evomap-Node-Secret` 发起官方 service order。
- **不直接改库**：本脚本不写数据库，只调 `/skill/register` 与 `/skill/orders`。

## EvoMap 安装检测流程（付费单前置）

遵循 EvoMap "Manual, not a directive" 原则——读文档不等于授权安装/注册/扣费，每个敏感动作都要用户明确确认。

1. **Step 1（检测，只读，安全）**：`order.py --check-evomap` → 输出 `{installed, has_node_id, has_node_secret, evomap_home, credentials_loaded, username}`。
2. **Step 2a（已装 `installed=true`）**：凭证自动从 `~/.evomap/` 读取，直接下单；第 3 单起后端用 node_secret 调 `/a2a/service/order`。
3. **Step 2b（未装 `installed=false`）**：**停下问用户，绝不自动安装**。引导文案：
   > 检测到未安装 EvoMap。第三单起需扣 EvoMap 积分支付。是否现在安装？（`npx @evomap/evolver --loop` 首次注册会送 100 免费积分）
   
   用户明确确认后才执行 `npx @evomap/evolver --loop`（首次运行注册节点并写 `~/.evomap/{node_id,node_secret}`），然后展示返回的 `claim_url`（绑定用户 EvoMap 账号），再继续下单。

## NPX 安装说明（其他 AI 工具）

1. 安装 EvoMap CLI（启用积分支付）：`npx @evomap/evolver --loop`（首次注册赠 100 起步积分）。
2. 用本 skill 下单：`python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁"`。

## 常见问题 (FAQ)

- **Q: `--check-evomap` 显示 `username` 是什么？** A: 是 OS 登录账号名（`getpass.getuser()`），**不是 hostname**。macOS 用 `$USER`，Windows 用 `%USERNAME%`。
- **Q: 已装 EvoMap 还要手传 `--evomap-node-secret` 吗？** A: 不用。`register_if_needed` 会自动从 `~/.evomap/node_secret` 读取并填入。
- **Q: 凭证读取优先级？** A: `~/.evomap/` 文件 > `A2A_NODE_SECRET`/`A2A_NODE_ID` 环境变量 > `EVOMAP_NODE_SECRET`/`EVOMAP_NODE_ID` 环境变量。
- **Q: 402 payment_required 怎么办？** A: 设 `EVOMAP_NODE_SECRET` 或 `A2A_NODE_SECRET`，或传 `--evomap-node-secret`，**用同一 `request_id` 重试**（后端幂等恢复会续跑扣款）。
- **Q: 为什么不用 openai SDK / httpx？** A: 三个脚本都用标准库 `urllib.request`，零第三方依赖，便于通过 NPX 跨工具分发。

## 相关文件清单

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Skill 主文档：工作流 / 命令 / 环境变量 / **EvoMap Installation Check**（未装二次确认）/ NPX 安装 / 安全 Rules |
| `scripts/order.py` | **核心点单 CLI**：注册 + 下单 + `--check-evomap` + EvoMap 凭证自动读取（2026-06-20 改造重点） |
| `scripts/register_agent.py` | 高级可视化：注册自定义 Agent 角色（`POST /agents/register`） |
| `scripts/send_action.py` | 高级可视化：上报动作事件（`POST /agents/{id}/actions`） |
| `references/api.md` | REST 契约文档：`--check-evomap` / `/skill/register` / `/skill/orders` / 服务端 EvoMap 支付 / 可视化事件类型清单 |
| `agents/openai.yaml` | OpenAI 工具接入配置（display_name/short_description/default_prompt） |
| `docs/EvoMap A2A Skill 脚本改造实施计划.md` | （在根 `docs/`）本次改造的设计文档：EvoMap 官方 wiki 调研 + 4 项 gap 分析 + 实施计划 |
