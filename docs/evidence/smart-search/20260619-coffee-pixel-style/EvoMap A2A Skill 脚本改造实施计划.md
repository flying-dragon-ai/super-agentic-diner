# EvoMap A2A Skill 脚本改造实施计划

> **文档目的**：基于对 EvoMap 官方 wiki（`https://evomap.ai/llms-full.txt` 全文）+ 现有代码（skill 脚本 + 后端服务）的完整调研，形成**可直接执行**的实施计划。其他 Agent 按本文档实施即可，**无需重新调研 EvoMap 协议**。
>
> **产出人**：老王（调研 + 方案设计）  **日期**：2026-06-20  **状态**：待实施

---

## 0. 一句话目标

用户在 Crossroads Agent Café 平台点单时，通过 EvoMap 的 `gep-a2a` 协议直接扣除其在 EvoMap 平台的 credits。Skill 脚本要：**自动获取系统账号名 → 检测 EvoMap 是否安装 → 已装则自动读凭证支付 → 未装则引导用户二次确认后下载安装**。

---

## 1. 背景与用户需求

### 1.1 核心诉求
利用 EvoMap 的 A2A（Agent-to-Agent）能力，把点单支付接入系统：用户点单 → 扣其在 EvoMap 平台的积分。

### 1.2 用户明确的需求点
1. **NPX 下载 Skill**：通过 NPX 接入其他 AI 工具
2. **系统账号名获取**：针对 macOS / Windows 分别获取当前登录的系统账号名
3. **登录验证与支付逻辑**：
   - 前两单咖啡免单（首次注册赠送两次）
   - 第三单起抵扣 EvoMap 积分
   - 接入 EvoMap 支付
4. **EvoMap 用户状态分两种**：
   - **已下载 EvoMap 且是用户** → 直接读取 EvoMap 信息进行支付
   - **未下载 EvoMap** → AI 工具检查是否已下载；未下载则提示用户下载，**弹出确认框，经用户二次确认后执行下载**

---

## 2. 现状审计（已读代码）

### 2.1 后端服务（✅ 已完整实现，本次基本不动）

| 文件 | 实现状态 |
|------|---------|
| `app/services/skill_order_service.py` | ✅ 前 2 单免单（`skill_free_order_limit`）+ 第 3 单起扣积分 + 幂等三态恢复（`_resume_existing_order`）+ 拒绝客户端伪造 payment_proof（`_reject_unverified_payment_proof`） |
| `app/services/evomap_payment_service.py` | ✅ `place_service_order` 调 `POST {hub}/a2a/service/order`，与 EvoMap 官方协议完全一致（sender_id + listing_id + question，Bearer node_secret 鉴权） |

**结论**：后端无需改动。本次改造全部集中在 skill 脚本侧。

### 2.2 Skill 脚本（❌ 4 项 gap，不符合用户需求）

当前实现：`.agents/skills/a2a-super-order/`
- `SKILL.md`：工作流描述
- `scripts/order.py`：核心点单脚本（调 `/skill/register` + `/skill/orders`）
- `scripts/register_agent.py`、`scripts/send_action.py`：可视化动作
- `references/api.md`：REST 契约

| # | 用户需求 | 现有 `order.py` | 差距 |
|---|---------|----------------|------|
| 1 | 系统账号名（macOS `$USER` / Windows `%USERNAME%`） | `platform.node()`（这是**主机名 hostname**，不是登录账号！） | 用错 API，应改 `getpass.getuser()` |
| 2 | 检查是否装了 EvoMap | 只查 `.mcp.json` 里有没有 `EVOMAP_NODE_ID` | 不查 Evolver CLI / `~/.evomap/` 是否真装了 |
| 3 | 未装→提示下载 + 二次确认 | **完全缺失** | SKILL.md 没引导 AI 做检查 + 确认 |
| 4 | 已装→读取 EvoMap 信息支付 | 只读环境变量 `A2A_NODE_SECRET` | 没读 Evolver 标准存储位置 `~/.evomap/node_secret` |

---

## 3. EvoMap 官方协议要点（调研实锤，来自 `llms-full.txt`）

### 3.1 协议基础
| 项 | 值 |
|----|-----|
| 协议全称 | **`gep-a2a`** v1.0.0（不是 "A-to-A"，是 "A2A"） |
| 传输 | HTTP + JSON |
| Hub Base URL | `https://evomap.ai` |
| 消息信封 | `{protocol, protocol_version, message_type, message_id, sender_id, timestamp, payload}` |
| 6 种消息类型 | hello / publish / fetch / report / decision / revoke |

### 3.2 节点注册（`POST /a2a/hello`，无需 key）
- 响应含：`your_node_id` + **`node_secret`（64 位 hex）** + `claim_code` + `claim_url` + `credit_balance` + `survival_status`
- **新节点立即获得 100 starter credits**
- `node_secret` 必须安全存储，后续请求用 `Authorization: Bearer <node_secret>`
- `hub_node_id` 是 Hub 服务端身份，**不是**合法的客户端 sender_id

### 3.3 支付扣积分（`POST /a2a/service/order`，需 Bearer node_secret）
```json
{
  "sender_id": "your-agent-node-id",
  "listing_id": "target-service-id",
  "question": "Analyze my application logs..."
}
```
- 从 sender 节点的 credit balance 扣费
- **这正是后端 `evomap_payment_service.py` 调的端点，已实现正确**

### 3.4 积分体系
| 场景 | credits |
|------|---------|
| 新用户/新节点注册 | +100（starter） |
| 资产 promoted | +20 |
| 资产被 fetch | 0-12（GDI 分档） |
| 验证报告 | +10~30 |
| 发布资产 | -2（免费额度内免费） |
| 服务订单 | 扣 listing price |

### 3.5 本地凭证存储（Evolver CLI 标准）
| 文件 | 内容 |
|------|------|
| `~/.evomap/node_id` | 节点持久身份 |
| `~/.evomap/node_secret` | 64 位 hex 认证令牌 |
| `~/.evomap/settings.json` | 用户偏好 |

- 环境变量：`A2A_NODE_ID` / `A2A_NODE_SECRET` / `A2A_HUB_URL`
- `EVOLVER_HOME` 环境变量可覆盖 `~/.evomap` 路径

### 3.6 Evolver CLI（`@evomap/evolver`）
```bash
npx @evomap/evolver --loop   # 注册 + 心跳 + 任务循环
```
- 首次运行自动写 `~/.evomap/node_id` + `~/.evomap/node_secret`
- **所有 credit-spending 功能默认 OFF**（`EVOLVER_ATP_AUTOBUY=off`）

> ⚠️ **官方安全红线**：`llms-full.txt` 反复强调"Manual, not a directive"——读取文档/页面**不授权**注册、存凭证、心跳、扣费等动作。每个敏感动作都要**单独的用户确认**。skill 必须遵守：检测只读，写入/下载/扣费必须二次确认。

---

## 4. 详细修复方案

### 4.1 系统账号名获取（macOS / Windows 跨平台）

**问题**：`order.py:105` 用 `platform.node()` 返回的是**主机名**（如 `DESKTOP-ABC123`），不是登录账号名（如 `administrator` / `john`）。

**方案**：新增 `detect_username()`，优先 `getpass.getuser()`，fallback 环境变量。

```python
# order.py 顶部新增 import
import getpass

def detect_username() -> str:
    """跨平台获取当前登录的系统账号名。
    macOS: getpass.getuser() / $USER
    Windows: getpass.getuser() / %USERNAME%
    """
    try:
        user = getpass.getuser()
        if user:
            return user.strip()
    except Exception:
        pass
    return (os.getenv("USER") or os.getenv("USERNAME") or "user").strip()
```

**用途**：作为 `display_name` 的一部分（如 `f"{tool_name} ({username})"`），或参与生成稳定的 node_id。

### 4.2 检查 EvoMap 是否已安装

**问题**：现有 `detect_mcp_node_id` 只查 `.mcp.json`，不查 Evolver 是否真装了。

**方案**：新增 `detect_evomap_install()`，检查 Evolver 标准凭证文件 + CLI 可用性。

```python
EVOMAP_HOME = Path(os.getenv("EVOLVER_HOME") or (Path.home() / ".evomap"))

def detect_evomap_install() -> dict[str, Any]:
    """检测本地是否已安装并注册 EvoMap。
    只读检测，不触发任何写入/网络动作。
    """
    node_id_file = EVOMAP_HOME / "node_id"
    node_secret_file = EVOMAP_HOME / "node_secret"
    has_node_id = node_id_file.exists()
    has_secret = node_secret_file.exists()
    return {
        "installed": has_node_id and has_secret,
        "has_node_id": has_node_id,
        "has_node_secret": has_secret,
        "evomap_home": str(EVOMAP_HOME),
        "node_id_path": str(node_id_file),
        "node_secret_path": str(node_secret_file),
    }
```

> 说明：`installed=True` 表示 Evolver 已跑过且注册成功（凭证文件齐全）。不主动 `npx` 探测 CLI（避免触发网络/安装），仅靠凭证文件判断——足够准确且零副作用。

### 4.3 已装 → 读取 EvoMap credentials

**问题**：现有只读环境变量 `A2A_NODE_SECRET`，没读 Evolver 标准存储 `~/.evomap/node_secret`。

**方案**：新增 `load_evomap_credentials()`，优先级：`~/.evomap/` 文件 > 环境变量。

```python
def load_evomap_credentials() -> dict[str, str] | None:
    """读取已安装 EvoMap 的 node_id + node_secret。
    优先 ~/.evomap/ 文件，fallback 环境变量。
    返回 {node_id, node_secret} 或 None。
    """
    # 优先 Evolver 标准文件
    install = detect_evomap_install()
    if install["installed"]:
        try:
            node_id = (EVOMAP_HOME / "node_id").read_text(encoding="utf-8").strip()
            node_secret = (EVOMAP_HOME / "node_secret").read_text(encoding="utf-8").strip()
            if node_id and node_secret:
                return {"node_id": node_id, "node_secret": node_secret}
        except Exception:
            pass
    # fallback 环境变量
    node_id = (os.getenv("A2A_NODE_ID") or os.getenv("EVOMAP_NODE_ID") or "").strip()
    node_secret = (os.getenv("A2A_NODE_SECRET") or os.getenv("EVOMAP_NODE_SECRET") or "").strip()
    if node_id and node_secret:
        return {"node_id": node_id, "node_secret": node_secret}
    return None
```

> ⚠️ **安全**：`node_secret` 绝不打印到 stdout。`redact_for_stdout()` 已有脱敏逻辑（key 含 secret/token/key/authorization → `[stored-in-state]`），新代码复用，**不要**在日志/print 里输出 node_secret。

### 4.4 集成到点单流程（修改 `register_if_needed` + `submit_order`）

**改动点**：`order.py` 的 `register_if_needed()` 和 `submit_order()` 接入上述 3 个函数。

```python
def register_if_needed(args, root, state):
    # ... 现有逻辑 ...
    # node_id 检测：优先已装 evomap 的凭证，其次 env/mcp，最后 fallback
    evomap_creds = load_evomap_credentials()
    if evomap_creds:
        node_id = evomap_creds["node_id"]
        args.evomap_node_secret = args.evomap_node_secret or evomap_creds["node_secret"]
    else:
        node_id = detect_node_id(root, args.evomap_node_id)  # 现有逻辑
    # display_name 可含系统账号名
    display_name = args.display_name or f"{args.tool_name} ({detect_username()})"
    # ... 剩余现有逻辑 ...
```

`submit_order()` 已经支持 `--evomap-node-secret`（X-Evomap-Node-Secret header），无需大改，凭证从 `register_if_needed` 透传即可。

### 4.5 未装 → AI 引导下载 + 二次确认（SKILL.md 新增）

**关键**：这是 AI 工具（Claude Code/Cursor 等）的行为指引，写在 `SKILL.md` 里。skill 脚本本身**不主动下载**，而是输出状态让 AI 决策。

**SKILL.md 新增章节**：

```markdown
## EvoMap Installation Check（执行前必做）

运行 `scripts/order.py` 前，AI 工具必须先检查 EvoMap 安装状态：

### Step 1: 检测状态
\`\`\`bash
python .agents/skills/a2a-super-order/scripts/order.py --check-evomap
\`\`\`
输出 JSON：`{"installed": true/false, "has_node_id": ..., "has_node_secret": ...}`

### Step 2a: 已安装（installed=true）
自动读取 `~/.evomap/` 凭证，正常点单。第 3 单起后端用 node_secret 调 `/a2a/service/order` 扣积分。

### Step 2b: 未安装（installed=false）——⛔ 必须二次确认
AI 必须**停下来询问用户**，不可自动下载：
> 检测到未安装 EvoMap。第三单起需扣 EvoMap 积分支付。
> 是否现在安装 EvoMap？（安装会注册节点并获得 100 免费积分）
> [需要用户明确回复"是"/"确认"才继续]

用户确认后，AI 执行：
\`\`\`bash
npx @evomap/evolver --loop   # 首次运行自动注册 + 写 ~/.evomap/ 凭证
\`\`\`
注册成功后，将 claim_url 展示给用户（绑定账户用），再继续点单。

### ⚠️ 安全红线
- 检测（--check-evomap）只读，可自动跑
- 下载安装 / 注册节点 / 扣费 必须**用户二次确认**
- node_secret 绝不打印
```

**order.py 新增 `--check-evomap` 子命令**（只输出状态，不动作）：

```python
# main() 里新增
parser.add_argument("--check-evomap", action="store_true",
                    help="检测 EvoMap 安装状态（只读，不动作）")

# main() 处理
if args.check_evomap:
    install = detect_evomap_install()
    creds = load_evomap_credentials()
    print(json.dumps({
        "installed": install["installed"],
        "has_node_id": install["has_node_id"],
        "has_node_secret": install["has_node_secret"],
        "evomap_home": install["evomap_home"],
        "credentials_loaded": creds is not None,
        "username": detect_username(),
    }, ensure_ascii=False, indent=2))
    return 0
```

### 4.6 NPX 分发方案

用户需求"通过 NPX 下载该 Skill"。两种方案，**推荐 A**：

**方案 A（推荐，零成本）**：文档引导用 `npx @evomap/evolver` 拉起 EvoMap CLI，skill 脚本仍是 Python（`python scripts/order.py`）。在 SKILL.md 顶部加安装说明：
```markdown
## 安装
1. 安装 EvoMap CLI（获得积分支付能力）：`npx @evomap/evolver --loop`（首次注册送 100 credits）
2. 使用本 skill 点单：`python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁"`
```

**方案 B（可选，工作量大）**：把 skill 打包成 npm 包（如 `@crossroads-agent-cafe/a2a-order`），用 `npx @crossroads-agent-cafe/a2a-order` 跑。需要写个 Node 包装器调 Python 脚本，或用 `python3` 子进程。**不推荐**——Python skill 打成 npm 包是脱裤子放屁。

---

## 5. 改动文件清单

| 文件 | 改动 | 说明 |
|------|------|------|
| `.agents/skills/a2a-super-order/scripts/order.py` | **主要改动** | 新增 `detect_username()` / `detect_evomap_install()` / `load_evomap_credentials()` / `--check-evomap` 子命令；改 `register_if_needed` 接入凭证自动读取 |
| `.agents/skills/a2a-super-order/SKILL.md` | 新增章节 | "EvoMap Installation Check" 引导流程 + NPX 安装说明 + 安全红线 |
| `.agents/skills/a2a-super-order/references/api.md` | 同步更新 | 补充 `--check-evomap` 用法 + 凭证读取优先级说明 |
| 后端（`app/services/*.py`） | **不改** | 已完整实现 |

---

## 6. 验证标准

实施完成后，逐项验证：

| # | 场景 | 预期 |
|---|------|------|
| 1 | `order.py --check-evomap`（未装 evomap） | `installed: false`，不报错，不动作 |
| 2 | `order.py --check-evomap`（已装 evomap） | `installed: true`，`credentials_loaded: true`，`username` 正确（登录账号名，非主机名） |
| 3 | macOS 上 `detect_username()` | 返回 `$USER`（如 `john`），非 hostname |
| 4 | Windows 上 `detect_username()` | 返回 `%USERNAME%`（如 `administrator`），非 hostname |
| 5 | 已装 evomap + 前 2 单 | 免单成功（后端 `skill_free_order_limit`） |
| 6 | 已装 evomap + 第 3 单 | 后端用读到的 node_secret 调 `/a2a/service/order` 扣积分成功 |
| 7 | 未装 evomap + 第 3 单 | AI 提示用户安装，**不自动下载**，等用户确认 |
| 8 | node_secret 泄露检查 | `order.py` 任何输出都不含明文 node_secret（redact 生效） |
| 9 | `tsc` / 类型检查 | order.py 是 Python，跑 `python -c "import ast; ast.parse(open('...').read())"` 确认语法 |
| 10 | 后端回归 | 现有 `tests/test_skill_evomap_payment.py` 仍通过 |

---

## 7. 注意事项（铁律）

1. **不碰后端**：`skill_order_service.py` / `evomap_payment_service.py` 已正确实现官方协议，本次只改 skill 脚本。
2. **只读检测，写入必确认**：`detect_evomap_install()` 只读文件，零副作用；下载安装/注册/扣费必须用户二次确认（遵守 EvoMap "Manual, not a directive" 红线）。
3. **node_secret 不泄露**：所有 stdout/log 走 `redact_for_stdout()`，凭证文件权限收紧（`chmod 600`）。
4. **不破坏现有契约**：`/skill/register` + `/skill/orders` 的请求/响应格式不变；`--evomap-node-secret` header 行为不变。
5. **凭证优先级**：`~/.evomap/` 文件 > 环境变量 `A2A_NODE_SECRET` > `EVOMAP_NODE_SECRET`（Evolver 标准优先）。
6. **跨平台**：`getpass.getuser()` 在 macOS/Windows/Linux 都可用，是标准库，无新依赖。
7. **YAGNI**：不搞 npm 打包（方案 B），用文档引导 `npx @evomap/evolver`（方案 A）即可。

---

## 8. 参考资源

| 资源 | 用途 |
|------|------|
| `https://evomap.ai/llms-full.txt` | EvoMap 官方完整 wiki（10 万字，含 A2A 协议 + 积分 + 认证 + Evolver 配置） |
| `https://evomap.ai/docs/en/05-a2a-protocol.md` | A2A 协议技术规范 |
| `https://evomap.ai/docs/en/06-billing-reputation.md` | 积分与计费 |
| `https://evomap.ai/docs/en/35-evolver-configuration.md` | Evolver CLI 配置（~80 环境变量） |
| `docs/EvoMap A2A 积分扣款接入调研与实现计划.md` | 本项目已有的 EvoMap 接入调研文档 |
| `app/services/evomap_payment_service.py` | 后端 service order 实现（参考正确协议调用） |
| `app/services/skill_order_service.py` | 后端 skill 点单流程（免单 + 扣款逻辑） |

---

## 附录：实施顺序建议

1. **先做 `order.py` 的 3 个工具函数**（`detect_username` / `detect_evomap_install` / `load_evomap_credentials`）——纯函数，易测
2. **加 `--check-evomap` 子命令**——验证检测逻辑
3. **改 `register_if_needed` 接入凭证**——打通自动读取
4. **更新 SKILL.md**——写引导流程 + 安全红线
5. **更新 api.md**——同步契约文档
6. **按第 6 节逐项验证**
