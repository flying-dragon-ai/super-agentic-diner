# Skill 设备授权 API（Browser Device Authorization）

> 对应源码：`app/services/skill_auth_service.py` + `app/main.py` 路由 `/skill/auth/*`
>
> 这是 A2A Skill 的**账号绑定**流程，用 OAuth 2.0 设备码模式把一个 EvoMap 节点
> 绑定到咖啡厅用户账号。旧的 `POST /skill/register` 只发一次性 token、不绑账号；
> 本流程在浏览器审批后签发**可吊销的 Agent token**，并能查余额、代客下单。

---

## 流程总览

```
CLI / Skill                         咖啡厅后端                      浏览器（用户）
   |                                    |                               |
   |-- POST /skill/auth/device/start -->|                               |
   |    (X-Evomap-Node-Secret)          |                               |
   |<-- device_code, user_code ---------|                               |
   |                                    |                               |
   |   （轮询）                          |                               |
   |-- POST /skill/auth/device/token -->|                               |
   |<-- 202 authorization_pending -------|                               |
   |                                    |                               |
   |                                    |<-- 打开 /skill/authorize ------|
   |                                    |    ?code=XXXX-XXXX            |
   |                                    |    （需登录账号）               |
   |                                    |<-- POST .../approve -----------|
   |                                    |                               |
   |-- POST /skill/auth/device/token -->|                               |
   |<-- 200 authorized, api_token ------|                               |
   |                                    |                               |
   |-- GET /skill/me (Bearer token) --->|                               |
   |<-- 账号信息 + 余额 ------------------|                               |
```

---

## 1. 启动设备授权

`POST /skill/auth/device/start`

**Headers:**

```text
X-Evomap-Node-Secret: <节点密钥>
Content-Type: application/json
```

> 本地开发可用 `X-Evomap-Node-Secret: local-dev` 绕过节点身份验证。

**Request body:**

```json
{
  "tool_name": "codex",
  "display_name": "用户 A",
  "evomap_node_id": "node_xxx",
  "evomap_did": "did:evomap:node_xxx"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `tool_name` | 是 | 工具名，1-64 字符 |
| `display_name` | 是 | 展示名，1-128 字符 |
| `evomap_node_id` | 是 | EvoMap 节点 ID，1-128 字符 |
| `evomap_did` | 否 | EvoMap DID，最长 255 字符 |

**Response 200:**

```json
{
  "status": "authorization_required",
  "device_code": "<43 字符 opaque token>",
  "user_code": "ABCD-EFGH",
  "verification_uri": "http://127.0.0.1:8000/skill/authorize",
  "verification_uri_complete": "http://127.0.0.1:8000/skill/authorize?code=ABCD-EFGH",
  "expires_in": 600,
  "interval": 2
}
```

| 字段 | 说明 |
|------|------|
| `device_code` | CLI 轮询换 token 用的凭证，**只返回一次** |
| `user_code` | 用户在浏览器输入的 8 位授权码 |
| `verification_uri` | 用户浏览器打开的审批页 |
| `verification_uri_complete` | 带 code 的完整 URL，可直接跳转 |
| `expires_in` | 过期秒数（600 秒 = 10 分钟） |
| `interval` | 轮询间隔秒数 |

---

## 2. 浏览器审批

用户打开 `verification_uri_complete`（或手动输入 user_code）：

1. **未登录** → 自动跳转 `/3d/login?next=/skill/authorize?code=XXXX-XXXX`
2. **已登录** → 显示账号信息 + 确认/拒绝按钮

审批页面对应的 HTML：`app/static/skill-authorize.html`

### 2a. 确认授权

`POST /skill/auth/device/approve`

> 需要浏览器登录 cookie（`require_account` 依赖）。CLI 不直接调此接口。

**Request body:**

```json
{ "user_code": "ABCD-EFGH" }
```

**Response 200:**

```json
{ "ok": true, "status": "approved" }
```

### 2b. 拒绝授权

`POST /skill/auth/device/deny`

**Request body:** 同 approve

**Response 200:**

```json
{ "ok": true, "status": "denied" }
```

### 2c. 解绑节点

`POST /skill/auth/device/unbind`

把当前审批请求对应的 EvoMap 节点与旧账号解绑，让用户能换账号重新绑。
只有当前绑定账号的拥有者才能解绑。

**Response 200:**

```json
{ "ok": true, "status": "unbound" }
```

---

## 3. 轮询换 Token

`POST /skill/auth/device/token`

**Request body:**

```json
{ "device_code": "<step 1 返回的 device_code>" }
```

**三种响应：**

### 3a. 待审批 — `202`

```json
{ "status": "authorization_pending", "interval": 2 }
```

继续每 `interval` 秒轮询。

### 3b. 已授权 — `200`

```json
{
  "status": "authorized",
  "api_token": "pa_xxxxxxxxxxxx",
  "authenticated": true,
  "username": "alice",
  "nickname": "爱丽丝",
  "display_name": "爱丽丝",
  "currency": "CNY",
  "balance": 100.0,
  "consumer_id": 1,
  "agent_id": 5,
  "evomap_node_id": "node_xxx",
  "scopes": ["profile:read", "wallet:read", "order:create"]
}
```

| 字段 | 说明 |
|------|------|
| `api_token` | Agent 令牌，**只返回一次**，后续用作 `Authorization: Bearer` |
| `balance` | 账号 CNY 余额（免费额度用完后从这里扣） |
| `scopes` | 令牌权限范围 |

### 3c. 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `authorization_denied` | 用户点了拒绝 |
| 409 | `device_code_consumed` | device_code 已兑换过 |
| 410 | `authorization_expired` | 10 分钟过期 |
| 404 | `invalid_device_code` | device_code 不存在 |

---

## 4. 查询当前账号

`GET /skill/me`

**Headers:**

```text
Authorization: Bearer <api_token>
```

或

```text
X-Agent-Token: <api_token>
```

**Response 200:**（字段同 3b，去掉 `status` 和 `api_token`）

---

## 5. 查看菜单（需绑定）

`GET /skill/menu`

**Headers:** 同 `/skill/me`

返回完整菜单（含价格、标签、库存）。

---

## 6. 匿名探测

`GET /skill/discovery`

无需认证。返回服务身份信息：

```json
{
  "service": "crossroads-agent-cafe",
  "protocol_version": 1,
  "name": "Crossroads Agent Café"
}
```

CLI 在连接前可先调此接口确认目标服务。

---

## Scopes（令牌权限）

设备授权流程签发的 token 固定包含以下 scope（`SKILL_SCOPES`）：

| Scope | 含义 |
|-------|------|
| `profile:read` | 读取账号昵称、用户名 |
| `wallet:read` | 读取 CNY 余额 |
| `order:create` | 代客下单 |

---

## 安全设计要点

1. **device_code / user_code 只返回一次**，后端只存 SHA-256 hash
2. **api_token 只返回一次**，后端只存 hash；丢失需重新走设备授权
3. **重新授权会轮换 token**：同一节点再次走设备码流程时，旧 Agent token 自动失活
4. **节点绑定唯一账号**：一个 EvoMap 节点同时只能绑一个账号，换绑需先解绑
5. **密码不落 CLI**：用户密码只在浏览器登录接口提交，CLI 只拿 opaque token
6. **TTL 600 秒**：device_code 和 user_code 10 分钟过期
7. **限流**：start 10 次/5分钟、token 320 次/10分钟、approve/deny 20 次/5分钟

---

## 与旧流程 (`/skill/register`) 的对比

| 维度 | `POST /skill/register`（旧） | 设备授权（新） |
|------|------------------------------|----------------|
| 账号绑定 | 无，匿名消费者 | 绑定到浏览器登录账号 |
| Token | 一次性，不可吊销 | 可吊销，重新授权轮换 |
| 余额 | 只有免费额度 | 免费额度 + 账号 CNY 余额 |
| 安全 | 谁拿到 token 谁能用 | 浏览器审批 + 可解绑 |
| 适用 | 快速试用、PoC | 生产环境、多用户 |

---

## CLI 接入示例（伪代码）

```python
import requests, time

# 1. 启动授权
resp = requests.post(f"{BASE}/skill/auth/device/start",
    json={"tool_name": "my-cli", "display_name": "Alice",
          "evomap_node_id": NODE_ID},
    headers={"X-Evomap-Node-Secret": NODE_SECRET})
data = resp.json()
device_code = data["device_code"]
print(f"请在浏览器打开: {data['verification_uri_complete']}")

# 2. 轮询换 token
while True:
    time.sleep(data["interval"])
    r = requests.post(f"{BASE}/skill/auth/device/token",
        json={"device_code": device_code})
    if r.status_code == 202:
        print("等待审批...")
        continue
    result = r.json()
    if result["status"] == "authorized":
        API_TOKEN = result["api_token"]
        print(f"授权成功，token: {API_TOKEN[:8]}...")
        break

# 3. 查询账号
me = requests.get(f"{BASE}/skill/me",
    headers={"Authorization": f"Bearer {API_TOKEN}"}).json()
print(f"当前用户: {me['display_name']}, 余额: {me['balance']} CNY")
```

---

## 已知前置条件

1. **数据库表 `skill_device_authorization` 必须存在**。若接口返回 500 且无 JSON body，
   多半是表没建。运行 `python scripts/init_db.py` 补建（幂等，不影响已有数据）。

2. **MySQL IP 白名单**：`coffee` 用户需要允许 CLI/后端的出口 IP。
   报错 `Access denied for 'coffee'@'x.x.x.x'` 时需在 MySQL 服务器执行：
   ```sql
   -- 查看允许的 IP
   SELECT host FROM mysql.user WHERE user = 'coffee';
   -- 授权新 IP（或用通配符）
   CREATE USER 'coffee'@'%' IDENTIFIED BY 'coffee123';
   GRANT ALL ON coffee_ai.* TO 'coffee'@'%';
   FLUSH PRIVILEGES;
   ```

3. **浏览器需先注册账号**：`/3d/login` 页面目前只有登录，新用户需先在注册页创建账号。
