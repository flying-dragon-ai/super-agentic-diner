# EvoMap A2A 积分扣款接入调研与实现计划

## Summary

- 你的目标是把本平台“咖啡点单确认后扣本地余额”的链路，改为通过 EvoMap 官方 A2A/服务订单能力扣用户 EvoMap Credits。
- 官方资料显示，最匹配的路径是 POST /a2a/service/order：以服务 listing 的 price_per_task 作为扣款金额，创建服务订单并从调用方 Agent/账户扣 Credits。
- 本项目当前在 app/services/order_service.py:103 中用 User.balance 本地扣款；app/db/models.py:126 已有 EvomapConsumer 和 SkillOrderLedger，适合作为 EvoMap 用户绑定与支付账本基础。

## Official Findings

- A2A 基础协议：gep-a2a v1.0.0，HTTP + JSON，Base URL 为 https://evomap.ai；多数变更型端点需要 Authorization: Bearer <node_secret>。
- 节点注册：POST /a2a/hello 返回 your_node_id、node_secret、claim_url、credit_balance；node_secret 只能在用户明确授权后保存。
- 服务扣款：POST /a2a/service/order 请求包含 sender_id、listing_id、question；文档说明服务价格会从所选 Agent 节点 Credits 中扣除，常见错误包括 Insufficient credits、Service at
  capacity、Cannot order own service。

- 积分规则：Credits 是 EvoMap 通用货币；服务市场订单按 listing 价格扣款，服务市场佣金为 30%，订单过期未履约可 100% 退款。
- 充值不是扣款：POST /a2a/credit/topup 是程序化充值，参数含 sender_id/node_id、amount、idempotency_key、node_secret，最小充值 100、单次最大 10,000、余额上限 100,000。
- API Key 限制：ek_ API Key 当前主要 scoped 到 Knowledge Graph，不应作为 A2A 服务订单扣款凭证。
- 证据文件已保存到 C:\tmp\smart-search-evidence\20260619-evomap-a2a\，关键来源包括 05-a2a-protocol.md、06-billing-reputation.md、17-credit-marketplace.md、28-api-access.md、33-agent-
  infrastructure、/atp。

## Key Changes

- 新增 EvoMap 支付配置：EVOMAP_HUB_URL=https://evomap.ai、EVOMAP_SERVICE_LISTING_ID、EVOMAP_PAYMENT_MODE=service_order，真实节点密钥只放本地 .env 或安全存储，不进入 .env.example。
- 新增 EvoMap 客户端模块：封装 POST /a2a/service/order，统一处理 401、402/insufficient credits、429、超时、网络错误和响应解析。
- 调整确认下单链路：用户确认后先检查 SkillOrderLedger.request_id 幂等记录，再调用 EvoMap 服务订单扣 Credits；成功后创建本地 Order，但不再扣 User.balance。
- 复用现有账本：EvomapConsumer 存 EvoMap node_id/DID/local_user_id 绑定关系，SkillOrderLedger 存 request_id、咖啡明细、amount_credits、payment_status、evomap_order_id、
  payment_proof_json。

- v1 价格模型默认采用“固定每单扣积分”：因为官方 service/order 以 listing 的固定 price_per_task 扣款；按咖啡总价动态扣积分需要额外 listing 策略或确认 EvoMap 是否支持动态金额。
- 保留两段式确认：用户先得到订单摘要，回复确认后才触发 EvoMap 扣款；扣款成功才落本地订单，扣款失败不创建已支付订单。

## Test Plan

- 单元测试：mock EvoMap 成功、余额不足、未授权、限流、超时、重复 request_id，验证账本和本地订单状态。
- 事务测试：EvoMap 扣款成功但本地订单写入失败时，记录 payment_status=needs_reconcile，避免静默丢单。
- 幂等测试：同一 request_id 重复确认不会重复调用 EvoMap 扣款，不会重复创建订单。
- 安全测试：确认 .env、node_secret、.mcp.json 不被 Git 跟踪；日志中不输出 Bearer token。
- 人工联调：使用低价测试 service listing 和测试 Agent 节点完成一次真实扣款，核对 EvoMap 订单、Credits 变化、本地 skill_order_ledger 和 orders 一致。

## Assumptions

- 已选择“服务订单”作为后续接入路径。
- 价格模型未收到进一步确认，默认采用“固定每单扣积分”。
- 不启动 Evolver loop、ATP autobuy、validator staking 或 heartbeat 常驻流程；这些都会带来额外凭据、联网或积分影响。
- 不使用未文档化的“任意扣用户 Credits”接口；所有扣款走官方服务订单或后续官方确认的支付接口。