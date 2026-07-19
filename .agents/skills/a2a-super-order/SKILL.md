---
name: a2a-super-order
description: Log in to Crossroads Agent Café and order coffee from Codex, Claude Code, Cursor, or Trae. All commands require a linked café account; orders debit that account's CNY wallet.
---

# A2A Super Order

Use this thin CLI to authenticate through the café web page, inspect the linked account and menu, and place CNY-paid coffee orders. Passwords must only be entered in the café web page; never ask the user to type a username or password into an AI chat or terminal command.

## Required workflow

1. Check login before every operation:
   ```bash
   python .agents/skills/a2a-super-order/scripts/order.py --me
   ```
2. If the result contains `account_login_required`, tell the user that browser login is required, then run:
   ```bash
   python .agents/skills/a2a-super-order/scripts/order.py --login
   ```
   The command opens `/skill/authorize`, waits for the user to log in with the project's existing `/auth/login` account, and stores the resulting Agent token locally. The browser shows “登录授权成功，可以返回 Codex” when complete.
3. Verify reachability and list the authenticated menu:
   ```bash
   python .agents/skills/a2a-super-order/scripts/order.py --ping
   python .agents/skills/a2a-super-order/scripts/order.py --menu
   ```
4. Use an exact menu name to order:
   ```bash
   python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁"
   ```

## Account and payment behavior

- Every Skill business command requires a valid linked café account, including `--ping` and `--menu`.
- `/skill/me` returns the project username, nickname, CNY balance, consumer ID, and Agent ID.
- New orders use the product's CNY price and debit the linked `UserWallet(CNY)` atomically with stock and order persistence.
- New Skill orders do not receive free-order quota and do not spend EvoMap Credits. EvoMap is node identity only.
- A successful response reports `amount_cny`, `currency=CNY`, `balance_after`, `payment_status=paid`, `amount_credits=0`, and `free_orders_remaining=0`.
- HTTP 402 with `code=insufficient_balance` means the café account needs a CNY top-up. Never attempt an EvoMap payment retry for this response.
- Reuse the same `--request-id` when retrying an uncertain result; this prevents a second debit.

## Commands

| Command | Purpose |
|---|---|
| `--login` | Open browser device authorization and store the resulting Skill token |
| `--me` | Validate login and show account/nickname/CNY balance |
| `--logout` | Revoke the current Agent token and remove its local state |
| `--ping` | Authenticated backend/menu reachability check |
| `--menu` | Authenticated product menu |
| `--message "..."` | Place a CNY-paid order |
| `--request-id <id>` | Idempotency key for safe retries |
| `--base-url <url>` | Save the café backend address |
| `--check-evomap` | Read-only local EvoMap identity check |

`--register-only`, `--force-register`, `--payment-proof`, and EvoMap credit payment are legacy behavior and must not be used for new orders.

## Security rules

- Never request or echo the café password, Agent API token, EvoMap node secret, device code, API key, authorization header, or `.env` contents.
- The browser is the only place where a user enters account credentials.
- The CLI stores its token in `~/.a2a-super-order/state.json`, attempts owner-only file permissions, and redacts secret/token/key/authorization fields from output.
- Login, logout, registration, top-up, and ordering change external state. Explain the action and obtain user intent before executing it. Read-only account/menu checks are safe after login.
- Use `/skill/auth/device/*`, `/skill/me`, `/skill/menu`, `/skill/logout`, and `/skill/orders`; never write database rows directly.
- Existing EvoMap/free ledgers are historical records and must not be rewritten or migrated to the linked account.

## 3D visualization

Successful orders still publish the normal customer/staff visualization events. The Skill does not drive the scene directly; placing the order is sufficient.
