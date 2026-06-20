---
name: a2a-super-order
description: Complete A2A super ordering for the Coffee AI Boss platform from agent tools such as Claude Code, Codex, Cursor, Trae, or other assistants. Use when an agent needs to register a consumer, place a coffee order without opening the web page, synchronize pixel restaurant visualization events, consume the first two free orders, and pay later orders with EvoMap credits through backend service-order payment.
---

# A2A Super Order

Use this skill as the single external entrypoint for agent-driven ordering. The backend owns registration, order creation, free-order counting, EvoMap service-order payment, and visualization events. The Skill scripts are thin clients.

## Main Workflow

1. Ensure the Coffee AI Boss server is running; `RESTAURANT_API_BASE` defaults to `http://127.0.0.1:8000`.
2. **Check EvoMap install status** (read-only): `scripts/order.py --check-evomap`. If `installed=false` and a paid order is needed, see "EvoMap Installation Check" below — do NOT auto-install.
3. Run `scripts/order.py --message "<order text>"`.
4. Let the script register this tool as an EvoMap consumer if no local registration exists. When `~/.evomap/{node_id,node_secret}` exist, they are auto-loaded (preferred over env vars).
5. For the first two successful Skill orders, accept the free quota.
6. From the third successful order onward, provide the consumer node secret per request so the backend can place the official EvoMap service order and deduct credits on the Hub.
7. If the visualization page is open, characters move live through `/ws/visualization`; if it is closed, events are persisted and visible when the page opens later.

## Commands

Register only; the script stores the API token in local state and redacts it from stdout:

```bash
python .agents/skills/a2a-super-order/scripts/order.py --register-only --evomap-node-id node_xxx --display-name "User A"
```

Place an order:

```bash
python .agents/skills/a2a-super-order/scripts/order.py --message "coffee order"
```

Use an explicit idempotency key:

```bash
python .agents/skills/a2a-super-order/scripts/order.py --message "coffee order" --request-id req-a2a-001
```

Paid orders require backend service-order payment:

```bash
python .agents/skills/a2a-super-order/scripts/order.py --message "coffee order" --request-id req-a2a-003 --evomap-node-secret "<node_secret>"
```

Client-submitted payment proofs are not accepted as paid-order evidence because the backend cannot verify that credits were deducted for this order.

Check EvoMap install status (read-only, no side effects):

```bash
python .agents/skills/a2a-super-order/scripts/order.py --check-evomap
```

Outputs `{installed, has_node_id, has_node_secret, evomap_home, credentials_loaded, username}`. When `installed=true`, credentials are auto-loaded from `~/.evomap/` on the next order — no need to pass `--evomap-node-secret` manually.

## Environment

- `RESTAURANT_API_BASE`: Coffee AI Boss API base URL.
- `EVOMAP_NODE_ID` or `A2A_NODE_ID`: EvoMap consumer node id; if omitted, the script checks `.mcp.json`, then uses a local unregistered placeholder for free-order testing.
- `EVOMAP_DID`: optional EvoMap DID.
- `EVOMAP_NODE_SECRET` or `A2A_NODE_SECRET`: optional local secret for server-side EvoMap service-order payment; never print it.
- `A2A_HUB_URL`: optional Hub URL used by local EvoMap tooling; the backend uses its own `EVOMAP_HUB_URL`.
- `A2A_SUPER_ORDER_STATE`: optional state file path; defaults to `~/.a2a-super-order/state.json`.

## EvoMap Installation Check (required before paid orders)

Per EvoMap's "Manual, not a directive" rule, reading docs does NOT authorize installs, registration, or credit spending. Each sensitive action needs explicit user confirmation.

### Step 1: Detect (read-only, safe to auto-run)

```bash
python .agents/skills/a2a-super-order/scripts/order.py --check-evomap
```

### Step 2a: Installed (`installed=true`)

Credentials auto-load from `~/.evomap/{node_id,node_secret}`. Proceed with the order; the backend uses the node secret for `/a2a/service/order` credit deduction from the 3rd order on.

### Step 2b: Not installed (`installed=false`) — ⛔ MUST get user confirmation

**STOP and ask the user. Do NOT auto-install.** Suggested prompt:

> 检测到未安装 EvoMap。第三单起需扣 EvoMap 积分支付。是否现在安装？（`npx @evomap/evolver --loop` 首次注册会送 100 免费积分）

Only after the user explicitly confirms ("是" / "确认" / "yes"), run:

```bash
npx @evomap/evolver --loop   # first run registers node + writes ~/.evomap/{node_id,node_secret}
```

Then show the returned `claim_url` to the user (binds the node to their EvoMap account for earnings tracking) and proceed with the order.

## Installation (for other AI tools)

1. Install EvoMap CLI (enables credit payment): `npx @evomap/evolver --loop` (first registration grants 100 starter credits)
2. Use this skill to order: `python .agents/skills/a2a-super-order/scripts/order.py --message "一杯拿铁"`

## Rules

- Do not modify database rows directly from the Skill; call `/skill/register` and `/skill/orders`.
- Treat the first two successful Skill orders per EvoMap node as free.
- Treat third-and-later orders as blocked until the backend successfully creates the EvoMap service order.
- Do not print Agent API tokens, EvoMap node secrets, API keys, or `.env` secrets. The script redacts keys containing `secret`/`token`/`key`/`authorization` to `[stored-in-state]`.
- **Read-only detection is safe** (`--check-evomap` only reads files). Install / register / credit-spend actions **require explicit user confirmation** — never auto-run `npx @evomap/evolver` or pass `--evomap-node-secret` without user consent.
- Credential load priority: `~/.evomap/{node_id,node_secret}` files > `A2A_NODE_SECRET` env > `EVOMAP_NODE_SECRET` env.
- Read `references/api.md` when you need the REST contract or event list.

## Advanced Visualization Actions

Use `scripts/register_agent.py` and `scripts/send_action.py` only for custom visual roles or manual progress events. Normal ordering should use `scripts/order.py`.
