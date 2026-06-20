---
name: a2a-super-order
description: Complete A2A super ordering for the Coffee AI Boss platform from agent tools such as Claude Code, Codex, Cursor, Trae, or other assistants. Use when an agent needs to register a consumer, place a coffee order without opening the web page, synchronize pixel restaurant visualization events, consume the first two free orders, and pay later orders with EvoMap credits through backend service-order payment.
---

# A2A Super Order

Use this skill as the single external entrypoint for agent-driven ordering. The backend owns registration, order creation, free-order counting, EvoMap service-order payment, and visualization events. The Skill scripts are thin clients.

## Main Workflow

1. Ensure the Coffee AI Boss server is running; `RESTAURANT_API_BASE` defaults to `http://127.0.0.1:8000`.
2. Run `scripts/order.py --message "<order text>"`.
3. Let the script register this tool as an EvoMap consumer if no local registration exists.
4. For the first two successful Skill orders, accept the free quota.
5. From the third successful order onward, provide the consumer node secret per request so the backend can place the official EvoMap service order and deduct credits on the Hub.
6. If the visualization page is open, characters move live through `/ws/visualization`; if it is closed, events are persisted and visible when the page opens later.

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

## Environment

- `RESTAURANT_API_BASE`: Coffee AI Boss API base URL.
- `EVOMAP_NODE_ID` or `A2A_NODE_ID`: EvoMap consumer node id; if omitted, the script checks `.mcp.json`, then uses a local unregistered placeholder for free-order testing.
- `EVOMAP_DID`: optional EvoMap DID.
- `EVOMAP_NODE_SECRET` or `A2A_NODE_SECRET`: optional local secret for server-side EvoMap service-order payment; never print it.
- `A2A_HUB_URL`: optional Hub URL used by local EvoMap tooling; the backend uses its own `EVOMAP_HUB_URL`.
- `A2A_SUPER_ORDER_STATE`: optional state file path; defaults to `~/.a2a-super-order/state.json`.

## Rules

- Do not modify database rows directly from the Skill; call `/skill/register` and `/skill/orders`.
- Treat the first two successful Skill orders per EvoMap node as free.
- Treat third-and-later orders as blocked until the backend successfully creates the EvoMap service order.
- Do not print Agent API tokens, EvoMap node secrets, API keys, or `.env` secrets.
- Read `references/api.md` when you need the REST contract or event list.

## Advanced Visualization Actions

Use `scripts/register_agent.py` and `scripts/send_action.py` only for custom visual roles or manual progress events. Normal ordering should use `scripts/order.py`.
