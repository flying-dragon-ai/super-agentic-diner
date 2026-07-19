# a2a-super-order

Crossroads Agent Café 的外部 AI 点单客户端，支持 Codex、Claude Code、Cursor、Trae 等工具。

运行环境需要 Python 3.10+；通过 npm/npx 使用时，Node 包装器会自动选择可用的合格 Python 解释器。

## 当前流程

所有 Skill 命令均要求先绑定项目用户账号。用户名和密码只在咖啡厅网页填写，不会进入 AI 对话或 CLI 参数。

```bash
python scripts/order.py --base-url https://cafe.example.com --login
python scripts/order.py --me
python scripts/order.py --ping
python scripts/order.py --menu
python scripts/order.py --message "一杯拿铁"
python scripts/order.py --logout
```

通常不再需要填写 `--base-url`。每次启动会先验证已保存地址；地址失效时依次尝试本机 `8000/8001` 和局域网 UDP 自动发现。也可主动刷新：

```bash
python scripts/order.py --discover
```

`--login` 会打开一次性设备授权页面。登录成功后，Token 保存到 `~/.a2a-super-order/state.json`，后续命令自动验证账号。如果浏览器仍登录旧账号，可在授权页点击“切换其他账号”；只有当前绑定账号可以确认解绑，随后会回到 3D 登录页。

`--logout` 只撤销 Skill Token 和本地状态，不清除浏览器 Cookie，也不解除节点绑定。需要换号时使用授权页的“切换其他账号”。

新 Skill 订单使用项目账号的人民币钱包：按菜单 CNY 价格扣款，库存、订单和钱包流水保持幂等。响应包含 `amount_cny`、`currency` 和 `balance_after`。EvoMap 只用于节点身份，新订单不再使用免费额度或 EvoMap Credits。

配置优先级：`--base-url` > `RESTAURANT_API_BASE` > 已验证缓存 > 本机发现 > 局域网发现。显式地址和环境变量无法验证时会直接停止；缓存失效则自动发现并更新。服务端默认使用 UDP `8137`，可分别通过 `A2A_DISCOVERY_UDP_PORT` 和客户端 `A2A_SUPER_ORDER_DISCOVERY_PORT` 调整。

局域网服务端必须让 HTTP 监听局域网接口，例如 `HOST=0.0.0.0`，并放行 HTTP 端口与 UDP `8137`。`A2A_DISCOVERY_HTTP_PORT` 必须是客户端实际可访问的 HTTP 端口。局域网发现只适用于可信私网；生产或跨公网连接推荐显式 HTTPS 域名。

详细行为见 [SKILL.md](SKILL.md)，接口见 [references/api.md](references/api.md)。

## 安全

- 不要在 AI 输入框或命令行传递咖啡厅密码。
- 不打印 Agent Token、设备密钥、EvoMap node secret 或 `.env` 内容。
- 重试订单必须复用同一个 `--request-id`，避免重复扣款。
- 历史免费单和 EvoMap ledger 仅保留审计，不迁移到登录账号。
- 切换账号会撤销节点的活动 Skill Token，但不会迁移或重写旧账号订单。
