---
name: a2a-super-order
description: Order coffee at Crossroads Agent Café from any AI assistant (Claude Code, Codex, Cursor, Trae). Use when the user wants to place a coffee order without opening a web page, see what coffees are available, or check whether the café backend is reachable. Handles consumer registration, the first two free orders per EvoMap node, and EvoMap credit payment from the 3rd order on. The backend drives all 3D visualization (customer avatar + staff) automatically once an order succeeds.
---

# A2A Super Order

Thin-client CLI for ordering coffee at Crossroads Agent Café from any AI tool. The backend owns registration, ordering, free-quota counting, EvoMap credit payment, and 3D visualization events. This skill only posts requests and manages local credentials.

## ⚠️ Before You Start (read first)

1. **Backend address — set once, it persists.** The default is `http://127.0.0.1:8000`, which only reaches *the same machine the script runs on*. If the café backend runs on **another machine**, point the skill at it once; the value is saved to `~/.a2a-super-order/config.json` and every later command auto-reads it:
   ```bash
   python .agents/skills/a2a-super-order/scripts/order.py --base-url http://<server>:8000 --ping
   ```
   Prefer a **domain** (e.g. `https://cafe.example.com`) over a raw IP — domains survive redeployments that rotate the IP. When the address does change, just re-run the line above with the new value; all subsequent commands follow automatically. Precedence: explicit `--base-url` > `RESTAURANT_API_BASE` env > saved config > default. Skip this on a remote backend and every command fails with "connection refused".
2. **Python ≥ 3.7** must be on PATH.
3. **The first 2 orders per EvoMap node are free** and need **no** EvoMap install. EvoMap is only required from the **3rd order on** (paid via credits). Do not run `--check-evomap` or try to install EvoMap before then — it is not needed.

## Decision Tree (run these steps in order)

### Step 0 — Verify the backend is reachable (always first)

```bash
python .agents/skills/a2a-super-order/scripts/order.py --ping
```

- `"ok": true` → continue to Step 1.
- `"ok": false` → the backend is unreachable. Diagnose in this order:
  1. `--base-url` / `RESTAURANT_API_BASE` points at the wrong host (most common for remote tools) → set `--base-url` to the server address or domain once (it persists) and retry.
  2. Backend not started → ask the user to run `uvicorn app.main:app` on the server.
  3. Firewall → ask the user to open port 8000.
  Do **not** proceed until `--ping` returns `"ok": true`.

### Step 1 — See what you can order

```bash
python .agents/skills/a2a-super-order/scripts/order.py --menu
```

Returns `items[]` with `name`, `price`, `tags`, `category`, `stock`. Pick the coffee you want and remember its **exact** `name` (e.g. `拿铁`, `美式咖啡`). `stock: 0` means sold out — pick something else.

### Step 2 — Place the order (free for the first 2)

```bash
python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁"
```

Put the **exact coffee name** from `--menu` in the message. Optionally set a friendly customer name shown in the 3D scene (otherwise it defaults to the OS username, which may be `root`/`Administrator`):

```bash
python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁" --display-name "Alice"
```

#### How to read the result

- `"status": "completed"` + `"payment_status": "free"` → success. Tell the user the `coffee_names`, the `amount_credits` charged (0 here), and `free_orders_remaining`.
- `"status": "completed"` + `"payment_status": "paid"` → paid success (only from the 3rd order on; see Step 3).
- HTTP **402** + `"status": "payment_required"` → this is the 3rd+ order and needs EvoMap credits. Go to **Step 3**. Keep the `request_id`.
- The reply lists no `coffee_names`, or mentions it could not identify the coffee → the name did not match. Re-run `--menu` and use the exact name; retry with the **same** `--request-id`.

### Step 3 — Paid order (3rd onward, requires EvoMap)

Only reach this step when `--ping` works AND the user already has 2 free orders AND the 3rd order returned 402.

1. Check EvoMap install (read-only):
   ```bash
   python .agents/skills/a2a-super-order/scripts/order.py --check-evomap
   ```
2. `"installed": true` → credentials auto-load from `~/.evomap/`. Retry the **same** order with the **same** `--request-id` (no need to pass `--evomap-node-secret` manually):
   ```bash
   python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁" --request-id req-a2a-003
   ```
   The backend uses the node secret to place an official EvoMap service order and deduct credits on the Hub.
3. `"installed": false` → **STOP and ask the user** (see "EvoMap Installation Check"). Do not auto-install.

## Command Reference

| Command | What it does | Side effects |
|---------|--------------|--------------|
| `--ping` | GET `/menu`, report reachability + menu count | None (read-only) |
| `--menu` | GET `/menu`, list coffees with price/tags/stock | None (read-only) |
| `--message "<text>"` | Register (if needed) + place an order | Creates order + 3D events |
| `--register-only` | Register consumer, store token, no order | Writes `~/.a2a-super-order/state.json` |
| `--request-id <key>` | Idempotency key; **reuse the same value** to retry a failed order safely | — |
| `--check-evomap` | Read `~/.evomap/` files, report install status | None (read-only) |
| `--base-url <url>` / `RESTAURANT_API_BASE` | Backend address (default `http://127.0.0.1:8000`; **must change for remote backends**) | — |
| `--display-name "<name>"` / `RESTAURANT_AGENT_NAME` | Customer name in the 3D scene (default = OS username) | — |
| `--evomap-node-secret "<secret>"` / `EVOMAP_NODE_SECRET` | Paid-order secret; auto-loaded from `~/.evomap/` when installed. **Never print.** | — |

`--payment-proof` is deprecated and ignored — the backend rejects client-forged proofs.

## `--message` Format

`--message` is one natural-language order line. For best recognition:

- ✅ Use the exact name from `--menu`: `一杯拿铁`, `来杯美式咖啡`, `两杯生椰拿铁`.
- ✅ Quantity is fine: `三杯拿铁`.
- ❌ Avoid vague text: `随便`, `推荐一杯`, `有啥` — these route to recommendation/chat, **not** a direct order.
- ❌ Avoid typos in the name. If unsure, run `--menu` first.

## Success Response (key fields)

| Field | Meaning |
|-------|---------|
| `status` | `completed` = success |
| `coffee_names` | What was ordered — report this to the user |
| `payment_status` | `free` or `paid` |
| `amount_credits` | Credits charged (0 for free orders) |
| `free_orders_remaining` | Free orders left for this node |
| `request_id` | Keep it; reuse it to retry safely |

## EvoMap Installation Check (only for paid orders)

Per EvoMap's "Manual, not a directive" rule, reading docs does NOT authorize installs, registration, or spending. Each sensitive action needs explicit user confirmation.

### Step 1: Detect (read-only, safe to auto-run)
`--check-evomap` → `{installed, has_node_id, has_node_secret, evomap_home, credentials_loaded, username}`.

### Step 2a: `installed=true`
Credentials auto-load from `~/.evomap/{node_id,node_secret}`. Retry the order with the same `--request-id`; the backend uses the node secret for `/a2a/service/order` credit deduction.

### Step 2b: `installed=false` — ⛔ MUST get user confirmation
**STOP. Do NOT auto-install.** Ask:
> 检测到未安装 EvoMap。第三单起需扣 EvoMap 积分支付。是否现在安装？（`npx @evomap/evolver --loop` 首次注册会送 100 免费积分）

Only after the user explicitly confirms ("是" / "确认" / "yes"):
```bash
npx @evomap/evolver --loop   # registers node + writes ~/.evomap/{node_id,node_secret}
```
Show the returned `claim_url` to the user, then retry the order.

## 3D Visualization (what the user sees, automatically)

On a successful order the backend broadcasts live events over `/ws/visualization`: the customer avatar enters the 3D scene, then staff animate — waiter walks to the counter, cashier takes the order, barista prepares the coffee, waiter delivers. If the 3D page is open the user sees it live; if it is closed, events are persisted and replayed when the page opens. **You do not drive visualization from this skill — placing the order is enough to trigger it.**

## Rules

- Call `/skill/register` and `/skill/orders` via this script — never write DB rows directly.
- First 2 successful orders per EvoMap node are free; the 3rd+ is blocked until the EvoMap service order succeeds.
- Never print API tokens, node secrets, API keys, or `.env` secrets. The script redacts keys containing `secret`/`token`/`key`/`authorization` to `[stored-in-state]`.
- Read-only checks (`--ping`, `--menu`, `--check-evomap`) are safe. Install / register / credit-spend **require explicit user confirmation** — never auto-run `npx @evomap/evolver` or pass `--evomap-node-secret` without consent.
- Credential priority: `~/.evomap/{node_id,node_secret}` files > `A2A_NODE_SECRET` env > `EVOMAP_NODE_SECRET` env.
- For the REST contract or event list, read `references/api.md`.

## Advanced Visualization Actions

`scripts/register_agent.py` and `scripts/send_action.py` are for custom visual roles or manual progress events only. Normal ordering uses `scripts/order.py`.
