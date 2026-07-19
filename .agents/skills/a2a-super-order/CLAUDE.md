# a2a-super-order 开发说明

## 当前架构（2026-07-19）

- CLI：`scripts/order.py`，仅使用 Python 标准库。
- 认证：网页设备授权；复用项目 `/auth/login`、`UserAccount` 和签名 httpOnly Cookie。
- Skill Token：设备码兑换时一次性返回，哈希存于 `agent_profile.api_token_hash`，本地状态文件保存原 Token 并对输出脱敏。
- 账号绑定：`evomap_consumer.local_user_id` 指向真实登录账号的 `user.user_id`。
- 余额：`GET /skill/me` 返回 `UserWallet(CNY)`；新订单调用 CNY 钱包和商品库存事务。
- 支付：新订单 `payment_status=paid`、`amount_credits=0`、`free_orders_remaining=0`。历史 EvoMap/free 流程仅用于旧 ledger 对账。

## 关键接口

- `POST /skill/auth/device/start`
- `POST /skill/auth/device/token`
- `POST /skill/auth/device/approve`、`/deny`、`/unbind`
- `GET /skill/me`、`GET /skill/menu`
- `POST /skill/logout`
- `POST /skill/orders`

除设备授权和退出恢复路径外，所有 Skill 业务请求必须持有已绑定项目账号的 Agent Token。旧 `/skill/register` 已弃用，不能产生可下单的登录态。

## 开发约束

- 密码只允许进入现有网页 `/auth/login`；不得进入 CLI、日志、文档示例或 AI 上下文。
- 数据库、Redis、EvoMap 和 Agent 凭证不得硬编码或回显。
- 设备码只保存 SHA-256 哈希，10 分钟过期且只能兑换一次。
- 节点绑定其他真实账号时禁止直接换绑；账号切换必须由当前绑定账号在授权页确认 `/unbind`，并撤销该节点全部活动 Token。
- 解绑只清除当前 `local_user_id` 关系，不迁移或重写历史订单与 ledger。
- 新 Skill 订单必须原子检查 CNY 余额、扣库存并写订单/钱包流水；重试复用 `request_id`。
- 不迁移或重写旧订单归属、免费额度、EvoMap 支付 ledger。
- 数据模型变更同时更新 `scripts/migrate_order_sources.py`，并保持 SQLite/MySQL 幂等。

运行验证：

```bash
python -m pytest -q
pnpm --dir frontend build
```
