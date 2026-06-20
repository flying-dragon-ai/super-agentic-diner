 # A2A 超级点单 Skill 与 EvoMap 积分接入计划

  ## Summary

  - 唯一对外 Skill 位于 .agents/skills/a2a-super-order/，面向 Claude Code、Codex、Cursor、Trae 等 Agent 使用。
  - Skill 不打开网页即可完成注册、点单、EvoMap 能力检测、积分扣减和订单提交；如果可视化页已打开，人物实时走动；如果未打开，事件持久化后可回放。
  - 前两单按 EvoMap 用户维度免费，不限金额；第三单开始必须检测并使用用户本地 Agent 的 EvoMap Skill/MCP/CLI 扣积分。
  - 网页端不再是点单入口的唯一来源，只作为实时可视化终端；后端成为订单、消费者身份、支付证明和动画事件的事实源。

  ## Key Changes

  - Skill 形态：使用 .agents/skills/a2a-super-order，更新 SKILL.md、agents/openai.yaml，保留注册和动作脚本能力，并新增一条主命令脚本 scripts/
    order.py。

  - 注册流程：新增 Skill 注册 API，记录 Agent 工具身份、EvoMap 节点身份、消费者身份、免费次数和可视化角色；注册成功后广播消费者人物进入餐厅。
  - 点单流程：新增 Skill 专用点单 API，支持一句话点单并默认自动确认；它复用现有咖啡解析逻辑，但订单支付走 EvoMap 积分，不再扣本地 User.balance。
  - 免费次数：新增订单账本记录每个 EvoMap 用户的 Skill 成功订单数；第 1、2 单 payment_status=free，第 3 单起返回 payment_required。
  - EvoMap 扣费：Skill 脚本在第三单起先检测 EvoMap 能力，再通过本地 Evolver ATP 能力发起积分消费，并把消费证明提交给后端；扣费失败则订单不创建。
  - 可视化同步：Skill 注册、点单、等待支付、支付成功、制作、完成、失败都写入 VisualizationEvent 并通过 /ws/visualization 广播，驱动人物同步移动。

  ## API And Data Model

  - 新增模型：
      - EvomapConsumer：consumer_id、evomap_node_id、evomap_did、display_name、free_orders_used、last_seen_at。
      - SkillOrderLedger：ledger_id、consumer_id、agent_id、order_id、request_id、amount_credits、payment_status、evomap_order_id、payment_proof_json、free_order_sequence。

  - 扩展 AgentProfile：增加可选 consumer_id、evomap_node_id、evomap_capability_status，继续保留现有 token 鉴权。
  - 新增 POST /skill/register：
      - 输入 tool_name、display_name、evomap_node_id、可选 evomap_did、capabilities。
      - 输出 consumer_id、agent_id、api_token、free_orders_remaining、sprite_seed。

  - 新增 POST /skill/orders：
      - 输入 consumer_id、agent_id、message、request_id、auto_confirm=true、可选 payment_proof。
      - 免费订单直接创建；付费订单若缺少有效证明则返回 402 payment_required 和 payment_request。

  - payment_request 固定包含 credits、evomap_caps、question、request_id、consumer_node_id，Skill 用它发起 EvoMap ATP 消费。
  - 新增 app/services/skill_order_service.py：封装 Skill 点单、免费次数判断、EvoMap 证明校验、外部支付后创建订单。
  - 新增 app/services/evomap_payment_service.py：只做支付请求生成、证明解析、严格校验；不保存任何密钥。
  - 订单价格默认按 咖啡金额 1:1 转 EvoMap credits，向上取整，最低 1 credit；后续可用 EVOMAP_CREDIT_RATE 调整。

  ## Skill Workflow

  - scripts/order.py --message "我要一杯拿铁" 是主入口：
      1. 读取 RESTAURANT_API_BASE，默认 http://127.0.0.1:8000。
      2. 若无本地注册信息，先调用 /skill/register，并保存 consumer_id、agent_id、api_token 到当前 Agent 本地配置文件。
      3. 调用 /skill/orders 提交点单；前两单免费时直接返回订单结果。
      4. 第三单起若收到 payment_required，执行 EvoMap preflight。
      5. 若 EvoMap CLI/MCP/Skill 不可用，输出登录、下载、注册指引，并调用 agent.action=error 让人物停在收银台。
      6. 若可用，运行 Evolver ATP 消费命令，随后用 evolver orders --json 拉取最近消费证明并回传 /skill/orders。
      7. 后端确认证明后创建订单，广播 order.paid、coffee.making、order.completed。

  - EvoMap preflight 判定：
      - evolver --help 或本地 node_modules/.bin/evolver 可执行。
      - A2A_HUB_URL 已配置，推荐为 https://evomap.ai。
      - evolver orders --json 可成功返回，说明本地身份和 Hub 连接可用。
      - 若检测到 MCP 配置但 ATP CLI 不可用，提示用户先登录或安装/启用 EvoMap Skill/MCP。

  - Evolver ATP 命令默认形态：
      - evolver buy <evomap_caps> --budget=<credits> --question="<A2A order request_id...>" --routing=fastest --verify=auto --timeout=120
      - 成功后运行 evolver orders --role=consumer --limit=10 --json，按 request_id、budget、时间窗口匹配证明。

  - Skill 只暴露一个入口，不再要求外部 Agent 直接调用 /agents/register 或 /agents/{id}/actions。

  ## Visualization Behavior

  - 注册成功：消费者人物从入口进入，显示 EvoMap 用户身份摘要。
  - Skill 发起点单：顾客走向点单台，服务员接单。
  - 免费订单：收银员显示“免费额度”，咖啡师制作，顾客取餐离开。
  - 第三单起待支付：顾客移动到收银台，时间线显示“需要 EvoMap 积分支付”。
  - EvoMap 已接入：收银员显示“积分扣减中”，扣费成功后继续制作流程。
  - EvoMap 未接入：人物停在收银台，气泡显示“请先登录 EvoMap”，订单不创建。
  - 无网页输入场景：Skill 调用后事件仍写入数据库；网页稍后打开时通过历史事件生成角色和最近动作状态。

  ## Test Plan

  - 启动服务后不使用网页输入，只运行 Skill 命令完成注册：确认 /agents 或新消费者接口能看到用户 A，打开网页后出现消费者人物。
  - 第 1 单通过 Skill 点单：确认无需 EvoMap 扣费，创建订单，free_orders_used=1，人物完成完整动线。
  - 第 2 单通过 Skill 点单：确认仍免费，free_orders_used=2，金额不限。
  - 第 3 单在未配置 EvoMap 时点单：确认返回支付阻断，订单不创建，人物停在收银台并显示错误状态。
  - 第 3 单在 EvoMap 可用时点单：确认 Skill 发起 ATP 消费、提交证明、订单创建、账本记录 payment_status=paid。
  - 使用相同 request_id 重试：确认不会重复创建订单、不会重复计免费次数、不会重复扣费。
  - 打开网页后重复 Skill 点单：确认 WebSocket 实时驱动画面，不需要从网页按钮下单。
  - 关闭网页后 Skill 点单，再打开网页：确认事件历史可回放，最近状态可见。
  - 检查 .env、.mcp.json、Agent token、EvoMap token 不进入日志、文档或 Git 输出。

  ## Assumptions

  - 唯一对外 Skill 名称采用 a2a-super-order，不保留第二个公开 Skill。
  - 第三单起必须真实扣 EvoMap 积分；本地 mock 只允许测试错误分支，不作为成功验收。
  - 免费次数按 evomap_node_id 统计，而不是按本地 user_id 或临时 agent_id 统计。
  - Skill 订单使用 EvoMap 积分支付，不扣现有咖啡馆本地余额；网页 /chat 原有本地余额逻辑保持兼容。
  - 当前阶段使用 Evolver ATP CLI 作为扣费通道；若 EvoMap 后续提供更直接的 MCP 扣费工具，再替换 evomap_payment_service 适配层。
