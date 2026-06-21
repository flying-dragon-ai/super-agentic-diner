# EvoMap Skill Payment Check Plan

Last reviewed: 2026-06-21

本文档用于后续复核 Coffee AI Boss 的 A2A Skill 付费链路。目标不是只看最终是否下单成功，而是把每个支付相关环节拆开验证，定位问题到底出在本地 Skill、Coffee 后端、EvoMap service-order、provider worker、数据库落库还是收益结算。

## 当前基线

当前已知配置与最近一次真实联调结果：

| 项 | 当前值 |
|---|---|
| 服务方节点 | `node_561cf18d6dcf8213` |
| 服务 listing | `cmqmeayol0da86138a33zhx9h` |
| listing 标题 | `Coffee AI Boss Order` |
| listing 价格 | `1 Credit` |
| listing 状态 | `active` |
| Skill 免费额度测试配置 | `SKILL_FREE_ORDER_LIMIT=0` |
| 最近真实请求 | `real-paid-232949` |
| 最近真实 Hub 错误 | `listing_provider_unavailable` |
| 最近本地账本状态 | `payment_failed` |
| 最近本地订单行 | 未创建 `order` 事实行 |

最近一次真实请求已经证明：

- `Skill -> Coffee Backend -> EvoMap /a2a/service/order` 已经打到真实 Hub。
- `EVOMAP_SERVICE_LISTING_ID` 指向的 listing 存在且 active。
- 消费者节点已经不同于服务方节点，不再是 `cannot_order_own_service`。
- 当前主要阻塞点是 EvoMap Hub 认为该 listing 没有可用 provider worker，即 `listing_provider_unavailable`。

## 安全规则

复核过程中必须遵守：

- 不在文档、日志、终端摘要、截图或最终汇报中输出任何 `node_secret`、API key、token、完整连接串。
- 服务方 secret 只能来自本地 `.env` 或临时安全环境；消费者 secret 只能来自 `.local-consumer.env`、`~/.evomap/node_secret` 或本次命令环境变量。
- `.local-consumer.env` 必须被 `.gitignore` 忽略。
- 消费者节点不能等于服务方节点 `node_561cf18d6dcf8213`。
- 真实扣费前必须确认用户允许消耗 EvoMap credits。
- 不要直接修改 MySQL 业务行来“制造成功”；Skill 路径必须走 `/skill/register` 和 `/skill/orders`。
- 不要把 `npx @evomap/evolver --loop` 当成普通健康检查命令。它可能启动 bridge、validator、ATP 自动行为；如必须启动，应显式关闭无关能力。

推荐受限环境变量：

```powershell
$env:EVOLVE_BRIDGE="false"
$env:EVOLVER_VALIDATOR_ENABLED="0"
$env:EVOLVER_ATP_AUTOBUY="off"
$env:ATP_AUTOBUY_DAILY_CAP_CREDITS="0"
$env:ATP_AUTOBUY_PER_ORDER_CAP_CREDITS="0"
$env:MEMORY_GRAPH_SYNC_HUB="0"
```

## 总链路

需要验证的完整链路如下：

```text
外部 Agent / Skill
  -> .agents/skills/a2a-super-order/scripts/order.py
  -> Coffee Backend /skill/register
  -> Coffee Backend /skill/orders
  -> app/services/skill_order_service.py
  -> app/services/evomap_payment_service.py
  -> EvoMap Hub POST /a2a/service/order
  -> Hub 扣消费者 credits
  -> Coffee 本地 SkillOrderLedger / Order / OrderItem / VisualizationEvent
  -> Hub service order 完成或结算
  -> provider node 收益或 pending settlement
```

另外还有一条 marketplace 直接购买链路需要单独验证：

```text
外部 Agent
  -> EvoMap Hub service listing
  -> provider worker 接单
  -> Coffee Backend 创建或完成订单
  -> provider worker 回传 delivery / completion
  -> Hub 结算
```

当前项目已实现的是“Coffee 后端代消费者调用 `/a2a/service/order`”的付款客户端链路；是否已实现 marketplace provider worker，需要按阶段 11 单独确认。

## 阶段 0：配置与凭据预检

目标：确认本地不会泄密、不会误用服务方节点付款。

检查项：

- `.env`
- `.local-consumer.env`
- `.gitignore`
- `~/.evomap/`
- `EVOMAP_SERVICE_LISTING_ID`
- `SKILL_FREE_ORDER_LIMIT`
- `EVOMAP_HUB_URL`
- 服务方 `EVOMAP_NODE_ID`
- 消费者 `A2A_NODE_ID`

推荐命令：

```powershell
git check-ignore -v .local-consumer.env

.\.venv\Scripts\python.exe `
  .agents\skills\a2a-super-order\scripts\order.py `
  --check-evomap

python scripts/check_evomap_service_binding.py --pretty
```

验收标准：

- `.local-consumer.env` 被 `.gitignore` 命中。
- `.env` 中 `EVOMAP_SERVICE_LISTING_ID=cmqmeayol0da86138a33zhx9h`。
- `.env` 中服务方 `EVOMAP_NODE_ID=node_561cf18d6dcf8213`。
- 服务方 secret 存在，但只报告 `present` 和长度，不打印明文。
- 消费者 `A2A_NODE_ID` 存在，且不等于 `node_561cf18d6dcf8213`。
- 消费者 secret 存在，但只报告 `present` 和长度，不打印明文。

失败解释：

| 现象 | 解释 | 处理 |
|---|---|---|
| `.local-consumer.env` 未被忽略 | 有误提交 secret 风险 | 先补 `.gitignore` |
| 消费者节点等于服务方节点 | 会触发 `cannot_order_own_service` | 换消费者节点 |
| 消费者 secret 为空 | 无法真实扣费 | 补 `A2A_NODE_SECRET` |
| `~/.evomap` 只有 `node_id` 没有 `node_secret` | 半安装状态 | 走 `.local-consumer.env` 或重新 claim/reset |

## 阶段 1：EvoMap Listing 复核

目标：确认 `EVOMAP_SERVICE_LISTING_ID` 指向正确服务。

推荐命令：

```powershell
$listingId = "cmqmeayol0da86138a33zhx9h"
Invoke-RestMethod `
  -Method Get `
  -Uri "https://evomap.ai/a2a/service/$listingId" `
  -Headers @{ "User-Agent" = "CoffeeAIBoss/1.0 (+https://evomap.ai; listing-check)" } |
  ConvertTo-Json -Depth 8
```

验收标准：

- `id == cmqmeayol0da86138a33zhx9h`
- `node_id == node_561cf18d6dcf8213`
- `title == Coffee AI Boss Order`
- `status == active`
- `price_per_task == 1`
- `currency == Credit`
- `max_concurrent > 0`

失败解释：

| 现象 | 解释 | 处理 |
|---|---|---|
| `404` | listing ID 错误或已删除 | 重新发布服务或更新 `.env` |
| `status != active` | listing 未启用 | 在 Hub 启用或重新发布 |
| `node_id` 不匹配 | `.env` 指向了别人的 listing | 更正 `EVOMAP_SERVICE_LISTING_ID` |
| 价格不为 1 | 实扣金额不符合预期 | 明确是否调整价格 |

记录证据：

```text
listing_id
provider_node_id
title
status
price_per_task
active_claims
total_completed
health_score
```

## 阶段 2：服务方节点在线与身份复核

目标：确认服务方节点 secret 有效，Hub 能识别服务方。

推荐命令方向：

```powershell
# 从 .env 读取 EVOMAP_NODE_ID / EVOMAP_NODE_SECRET，但不要打印 secret。
# 用服务方 secret 调 Hub heartbeat。
POST https://evomap.ai/a2a/heartbeat
Authorization: Bearer <EVOMAP_NODE_SECRET>
body: { "node_id": "node_561cf18d6dcf8213" }
```

本地接口也可复核：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/admin/evomap/status" |
  ConvertTo-Json -Depth 8
```

验收标准：

- `configured == true`
- `node_id == node_561cf18d6dcf8213`
- `online == true`
- `claimed == true`
- `credit_balance` 可读
- 无 `node_secret_invalid`

失败解释：

| 现象 | 解释 | 处理 |
|---|---|---|
| `401/403 node_secret_invalid` | 服务方 secret 失效 | 在 EvoMap account reset secret，然后更新 `.env` |
| `429` | heartbeat 频率限制 | 等待 `retry-after` |
| `online=false` | 后端无法与 Hub 正常通信 | 查网络、Hub、`.env` |

## 阶段 3：消费者节点复核

目标：确认消费者节点能作为付款方。

检查项：

- `A2A_NODE_ID`
- `A2A_NODE_SECRET`
- 消费者节点是否已 claim
- 消费者余额是否足够

验收标准：

- `consumer_node_id != node_561cf18d6dcf8213`
- `consumer_secret_present == true`
- 消费者 Hub 鉴权成功
- `credit_balance >= 1`

已知风险：

- 最近临时注册的消费者节点 `node_6a576b7549ee5022` 返回过 `credit_balance=0`。
- 如果 provider worker 问题解决，下一关可能会变为 `insufficient_credits`。

失败解释：

| 现象 | 解释 | 处理 |
|---|---|---|
| `401/403` | 消费者 secret 错误 | 换正确消费者 secret |
| `402 insufficient credits` | 消费者余额不足 | claim 后充值或换有余额节点 |
| `cannot_order_own_service` | 消费者误用服务方节点 | 换非服务方节点 |

## 阶段 4：Coffee Backend 健康检查

目标：确认本地服务、MySQL、Redis、LLM 和 EvoMap 配置都在正确状态。

推荐命令：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/status" |
  ConvertTo-Json -Depth 8

Invoke-RestMethod -Uri "http://127.0.0.1:8000/admin/evomap/status" |
  ConvertTo-Json -Depth 8
```

验收标准：

- `database == mysql`
- `memory == redis`
- `llm_active == true`
- EvoMap `configured == true`
- EvoMap `online == true`

失败解释：

| 现象 | 解释 | 处理 |
|---|---|---|
| `database != mysql` | 不符合项目架构约束 | 修 `.env` / 启动 MySQL |
| `memory != redis` | 不符合项目架构约束 | 修 `.env` / 启动 Redis |
| `evomap online=false` | 服务方 Hub 通信失败 | 回到阶段 2 |

## 阶段 5：Skill 注册链路测试

目标：确认消费者 Agent 能注册到 Coffee 后端，并创建或复用 `EvomapConsumer` 和 `AgentProfile`。

推荐命令：

```powershell
$env:A2A_NODE_ID = "node_消费者"
$env:A2A_NODE_SECRET = "消费者secret"
$env:RESTAURANT_API_BASE = "http://127.0.0.1:8000"

.\.venv\Scripts\python.exe `
  .agents\skills\a2a-super-order\scripts\order.py `
  --register-only `
  --force-register
```

验收标准：

- 返回 `consumer_id`
- 返回 `agent_id`
- `api_token` 输出被脱敏
- `evomap_node_id == 消费者节点`
- `free_orders_remaining` 与 `SKILL_FREE_ORDER_LIMIT` 一致

数据库复核：

- `evomap_consumer` 有对应消费者节点。
- `agent_profile` 有对应 agent。
- `status == active`
- `last_seen_at` 更新。

失败解释：

| 现象 | 解释 | 处理 |
|---|---|---|
| 缺 `evomap_node_id` | 环境变量未注入 | 重设 `A2A_NODE_ID` |
| 连接失败 | 后端未启动或 `RESTAURANT_API_BASE` 错 | 检查服务地址 |
| token 明文出现在 stdout | 脱敏漏洞 | 先修 Skill 脚本 |

## 阶段 6：无 Secret 的 Paid-Order 阻断测试

目标：确认付费单在没有消费者 secret 时不会创建 paid 订单。

测试前提：

- `SKILL_FREE_ORDER_LIMIT=0`，或该消费者已超过免费额度。

推荐命令：

```powershell
$env:A2A_NODE_ID = "node_消费者"
Remove-Item Env:\A2A_NODE_SECRET -ErrorAction SilentlyContinue

.\.venv\Scripts\python.exe `
  .agents\skills\a2a-super-order\scripts\order.py `
  --message "我要一杯美式咖啡" `
  --request-id "test-payment-required-001" `
  --force-register
```

验收标准：

- HTTP `402`
- `status == payment_required`
- `service_order_request.listing_id == cmqmeayol0da86138a33zhx9h`
- `amount_credits == 1`
- 不创建 `order` 事实订单。
- `SkillOrderLedger.payment_status` 为 `payment_required`、`payment_pending` 或当前实现约定的可重试状态。

失败解释：

| 现象 | 解释 | 处理 |
|---|---|---|
| 无 secret 也创建 paid 订单 | 严重支付漏洞 | 立即修复 |
| 返回 free | 免费额度配置不符合测试目标 | 调整 `SKILL_FREE_ORDER_LIMIT` 或换消费者 |
| 没有 `service_order_request` | Skill 无法知道购买哪个 listing | 修响应 payload |

## 阶段 7：真实 Hub 扣费请求测试

目标：验证 Coffee 后端能用消费者 secret 调用 EvoMap `/a2a/service/order`。

推荐命令：

```powershell
$env:A2A_NODE_ID = "node_消费者"
$env:A2A_NODE_SECRET = "消费者secret"
$env:RESTAURANT_API_BASE = "http://127.0.0.1:8000"

.\.venv\Scripts\python.exe `
  .agents\skills\a2a-super-order\scripts\order.py `
  --message "我要一杯美式咖啡" `
  --request-id "real-paid-001" `
  --force-register
```

成功验收：

- HTTP `200`
- `status == completed`
- `payment_status == paid`
- `evomap_order_id` 非空
- `order_ids` 非空
- `coffee_names` 包含目标咖啡
- `amount_credits == 1`

数据库成功验收：

- `SkillOrderLedger.payment_status == paid`
- `SkillOrderLedger.evomap_order_id` 非空
- `SkillOrderLedger.order_ids_json` 非空
- `Order.source_type == skill`
- `Order.payment_status == paid`
- `Order.evomap_order_id` 非空
- `Order.consumer_id` 对应 `EvomapConsumer`
- `Order.agent_id` 对应 `AgentProfile`
- `Order.ledger_id` 对应 `SkillOrderLedger`
- `OrderItem` 正常落库

当前已观察失败：

```text
HTTP 502
code=listing_provider_unavailable
SkillOrderLedger.payment_status=payment_failed
evomap_order_id=null
order_count=0
```

该失败说明链路已经打到真实 Hub，但 Hub marketplace 层认为 provider 不可用。

## 阶段 8：支付错误分支矩阵

目标：将常见失败变成可解释、可恢复、可复测的状态。

| 场景 | 预期 | 本地订单要求 |
|---|---|---|
| 不传 `A2A_NODE_SECRET` | `402 payment_required` | 不创建 `Order` |
| 传错误消费者 secret | `401/403` 或映射错误 | `ledger=payment_failed`，不创建 `Order` |
| 消费者节点等于服务方节点 | `cannot_order_own_service` | 不创建 `Order` |
| 消费者余额不足 | `insufficient_credits` 或 `402` | 不创建 `Order` |
| listing ID 不存在 | `listing_not_found` | 不创建 `Order` |
| provider 不在线 | `listing_provider_unavailable` | `ledger=payment_failed`，不创建 `Order` |
| Hub 限流 | `rate_limited` 或 `429` | 不创建 paid `Order` |
| Hub 超时 | timeout 或 `504` | 不创建 paid `Order` |
| 同 `request_id` 换消费者 | `409 request_id_conflict` | 不复用订单 |

每个错误分支都要记录：

- HTTP status
- 返回 `code`
- `SkillOrderLedger.payment_status`
- 是否创建 `Order`
- 是否写入 `evomap_order_id`
- 是否产生 `restaurant.payment_failed` / `order.failed`
- 是否允许同 `request_id` 重试

## 阶段 9：幂等性与重试测试

目标：确保重试不会重复扣费，也不会重复创建订单。

测试场景：

| 场景 | 预期 |
|---|---|
| `payment_required` 后同 `request_id` + secret 重试 | 可继续支付 |
| `payment_failed` 后同 `request_id` + secret 重试 | 按当前实现恢复或再次明确失败 |
| `paid` 成功后同 `request_id` 重试 | 不重复扣费，不重复创建订单 |
| 并发两次同 `request_id` | 最多一个 paid ledger/order |
| 同 `request_id` 不同消费者 | 返回 conflict |

重点检查：

- `skill_order_ledger.request_id` 唯一约束
- `skill_order_ledger.payment_status`
- `skill_order_ledger.evomap_order_id`
- `skill_order_ledger.order_ids_json`
- `order.ledger_id`
- `order.evomap_order_id`
- `updated_at`

## 阶段 10：可视化事件复核

目标：确认支付链路每个阶段都有可解释事件。

成功链路应出现：

```text
restaurant.customer_entered
message.received
restaurant.order_ticketed
order.intent_detected
restaurant.payment_processing
restaurant.payment_completed
restaurant.preparation_progress
restaurant.order_ready
restaurant.order_delivered
restaurant.customer_reviewed
restaurant.customer_left
order.paid
```

失败链路应出现：

```text
restaurant.customer_entered
message.received
restaurant.order_ticketed
order.intent_detected
restaurant.payment_processing
restaurant.payment_failed
restaurant.order_failed
order.payment_failed
order.failed
```

验收标准：

- `correlation_id == request_id`
- 事件顺序合理。
- payload 中 `payment_status`、`amount_credits`、`consumer_id`、`evomap_node_id` 正确。
- 失败时不能出现 `payment_completed` 或 `order.paid`。
- 成功时必须出现 `payment_completed` 和 `order.paid`。

## 阶段 11：Marketplace Provider Worker 复核

目标：解决当前 `listing_provider_unavailable`。

需要查清楚：

- `Coffee AI Boss Order` listing 是否必须绑定 provider worker。
- provider worker 如何声明自己处理 `listing_id=cmqmeayol0da86138a33zhx9h`。
- Hub 是用轮询、SSE、mailbox 还是其他方式派发订单。
- 完成订单是否需要 delivery proof、completion endpoint 或 settle endpoint。
- listing 是否必须在 EvoMap Web UI 中 claim、activate 或绑定 worker。
- 默认 `npx @evomap/evolver --loop` 发布的 `Evolver Agent - Code Evolution` 是否不能服务自定义 `Coffee AI Boss Order` listing。

provider worker 应具备的能力：

```text
1. 用服务方节点 node_561cf18d6dcf8213 上线。
2. 声明或绑定 listing_id=cmqmeayol0da86138a33zhx9h。
3. 接收或轮询 Hub service order。
4. 解析 question。
5. 调用 Coffee Backend 创建订单或完成服务。
6. 回传 delivery / completion。
7. Hub 将订单状态推进到 completed / settled。
```

验收标准：

- 外部 Agent 直接购买 listing 时，Hub 不再返回 `listing_provider_unavailable`。
- Hub 返回可追踪的 order id 或 task id。
- Coffee Backend 有对应本地订单或服务记录。
- Hub service order 最终完成。
- provider node 的收益、余额或 pending settlement 可见变化。

如果官方当前不支持自定义 provider worker API，或 Coffee listing 未接入 provider worker，则结论应明确写成：

```text
当前只支持“对方调用 Coffee Skill/API，由 Coffee 后端代扣”模式；
暂不支持“对方直接在 EvoMap marketplace 购买 Coffee listing 并由 Hub 派单”模式。
```

## 阶段 12：收益与结算复核

目标：确认积分不是只扣了，还能归集到服务方。

成功支付前后需要记录：

- 消费者 credit balance 前后变化。
- 服务方 credit balance 前后变化，或 pending settlement 变化。
- listing `total_completed` 是否增加。
- listing `last_ordered_at` 是否更新。
- Hub service order 状态是否为 `completed`、`settled` 或其他已完成状态。
- 服务方 EvoMap account 是否能看到收入。

可能结算模型：

- 即时到账。
- 任务完成后到账。
- pending settlement。
- 需要 provider account claim 后可见。
- 需要 delivery proof 后结算。

最终以 EvoMap Hub 实际返回和账号侧记录为准。

## 阶段 13：最终端到端验收

最终成功必须同时满足：

1. 使用非服务方消费者节点。
2. 消费者余额大于等于 `1 Credit`。
3. 调用 Coffee Skill 下单。
4. EvoMap `/a2a/service/order` 返回成功。
5. 返回 `evomap_order_id`。
6. `SkillOrderLedger.payment_status == paid`。
7. `Order.payment_status == paid`。
8. `Order.source_type == skill`。
9. `Order.evomap_order_id == Hub 返回的 order id`。
10. 可视化事件出现 `restaurant.payment_completed` 和 `order.paid`。
11. Hub listing 的 `total_completed` 或 service order 状态更新。
12. 消费者 credits 减少。
13. 服务方收益、余额或 pending settlement 可见变化。

最终记录格式建议：

```text
request_id=real-paid-xxx
consumer_node_id=node_xxx
provider_node_id=node_561cf18d6dcf8213
listing_id=cmqmeayol0da86138a33zhx9h
evomap_order_id=xxx
payment_status=paid
order_ids=[...]
consumer_balance_before=N
consumer_balance_after=N-1
provider_balance_or_settlement=updated
```

## 建议执行顺序

后续排查建议按下面顺序推进：

1. 先确认消费者节点已 claim 且有 credits。
2. 再确认 listing 是否需要在 Web UI 绑定或激活 provider worker。
3. 查官方 provider worker / service completion 文档。
4. 如果官方有 API，补 Coffee marketplace provider worker。
5. 先用 mock Hub 验证 provider worker。
6. 再用真实 Hub 跑一单。
7. 最后复核本地 DB、Hub 订单状态、消费者余额、服务方收益。

当前最关键的下一步不是重复下单，而是补齐或确认：

```text
Coffee AI Boss Order listing 的 provider worker / 接单器
```

否则真实扣费会继续卡在：

```text
listing_provider_unavailable
```

## 2026-06-21 live binding check

Run:

```powershell
python scripts/check_evomap_service_binding.py --pretty
```

Current live result: the configured service listing is active, featured, priced at 1 Credit, and uses `execution_mode=exclusive`, but the local `EVOMAP_NODE_ID` does not match the listing owner `node_id`. `WORKER_ENABLED` is also not enabled in the local env. In this state, starting a local provider worker with the current credentials will not serve the configured exclusive listing.

Next action gate: align `EVOMAP_SERVICE_LISTING_ID`, `EVOMAP_NODE_ID`, and `EVOMAP_NODE_SECRET` so they refer to the same service owner, then enable Worker mode only after the operator explicitly approves worker participation, max load, and credit limits.
