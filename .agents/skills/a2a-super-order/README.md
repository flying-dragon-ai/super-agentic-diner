# a2a-super-order

Crossroads Agent Café 的外部 AI 点单客户端，支持 Codex、Claude Code、Cursor、Trae 等工具。

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

`--login` 会打开一次性设备授权页面。登录成功后，Token 保存到 `~/.a2a-super-order/state.json`，后续命令自动验证账号。如果浏览器仍登录旧账号，可在授权页点击“切换其他账号”；只有当前绑定账号可以确认解绑，随后会回到 3D 登录页。

`--logout` 只撤销 Skill Token 和本地状态，不清除浏览器 Cookie，也不解除节点绑定。需要换号时使用授权页的“切换其他账号”。

新 Skill 订单使用项目账号的人民币钱包：按菜单 CNY 价格扣款，库存、订单和钱包流水保持幂等。响应包含 `amount_cny`、`currency` 和 `balance_after`。EvoMap 只用于节点身份，新订单不再使用免费额度或 EvoMap Credits。

配置优先级：`--base-url` > `RESTAURANT_API_BASE` > `~/.a2a-super-order/config.json` > 默认地址。生产环境推荐使用 HTTPS 域名。

详细行为见 [SKILL.md](SKILL.md)，接口见 [references/api.md](references/api.md)。

## 安全

- 不要在 AI 输入框或命令行传递咖啡厅密码。
- 不打印 Agent Token、设备密钥、EvoMap node secret 或 `.env` 内容。
- 重试订单必须复用同一个 `--request-id`，避免重复扣款。
- 历史免费单和 EvoMap ledger 仅保留审计，不迁移到登录账号。
- 切换账号会撤销节点的活动 Skill Token，但不会迁移或重写旧账号订单。
