# A2A Super Order API

Base URL defaults to `http://127.0.0.1:8000`.

## Register Skill Consumer

`POST /skill/register`

Request:

```json
{
  "tool_name": "codex",
  "display_name": "User A",
  "evomap_node_id": "node_xxx",
  "evomap_did": "did:evomap:node_xxx",
  "role_type": "customer",
  "capabilities": ["a2a_super_order", "evomap_credit_payment"],
  "metadata": {"workspace": "coffee-ai-boss"},
  "evomap_capability_status": "detected"
}
```

Response:

```json
{
  "consumer_id": 1,
  "agent_id": 1,
  "api_token": "pa_...",
  "role_type": "customer",
  "sprite_seed": 123456,
  "free_orders_remaining": 2,
  "evomap_node_id": "node_xxx"
}
```

Store `consumer_id`, `agent_id`, and `api_token`. The token is shown only once.

## Place Skill Order

`POST /skill/orders`

Headers:

```text
Authorization: Bearer <api_token>
X-Evomap-Node-Secret: <node secret for paid server-side payment>
```

Request:

```json
{
  "consumer_id": 1,
  "agent_id": 1,
  "message": "coffee order",
  "request_id": "req-a2a-001",
  "auto_confirm": true,
  "payment_proof": null
}
```

`payment_proof` must be `null` for normal operation. The backend does not accept client-submitted proofs as paid-order evidence because it cannot verify that credits were deducted for this order.

Free-order success:

```json
{
  "ok": true,
  "status": "completed",
  "reply": "Skill order completed",
  "request_id": "req-a2a-001",
  "consumer_id": 1,
  "ledger_id": 1,
  "order_ids": [10],
  "coffee_names": ["Hazelnut Latte"],
  "amount_credits": 1,
  "payment_status": "free",
  "free_orders_remaining": 1,
  "evomap_order_id": null,
  "payment_request": null
}
```

Paid-order block when the node secret is missing:

```json
{
  "detail": {
    "ok": false,
    "status": "payment_required",
    "reply": "This order requires EvoMap Credits. Provide the node secret for a server-side service order.",
    "request_id": "req-a2a-003",
    "amount_credits": 1,
    "payment_request": null,
    "payment_method": "evomap_service_order",
    "service_order_request": {
      "sender_id": "node_xxx",
      "listing_id": "your-evomap-service-listing-id",
      "question": "Coffee order payment request_id=req-a2a-003; ..."
    }
  }
}
```

Retry the same `/skill/orders` request with `X-Evomap-Node-Secret` after the user has authorized spending EvoMap credits. If the backend has `EVOMAP_SERVICE_LISTING_ID`, it creates the EvoMap service order through `/a2a/service/order`; only then is the local order marked `paid`.

## EvoMap Service Order

The backend sends:

```json
{
  "sender_id": "node_xxx",
  "listing_id": "your-evomap-service-listing-id",
  "question": "Coffee order payment request_id=req-a2a-003; consumer_node_id=node_xxx; coffees=Hazelnut Latte; credits=1"
}
```

The EvoMap Hub charges the service listing price from the sender node/account. `amount_credits` in Coffee AI Boss is local ledger metadata and should match the configured listing price operationally.

## Visualization

The browser page subscribes to:

```text
ws://127.0.0.1:8000/ws/visualization
```

Event history:

```text
GET /visualization/events?limit=50
```

Important event types:

- `agent.registered`
- `agent.heartbeat`
- `agent.action`
- `message.received`
- `order.intent_detected`
- `order.pending_confirmation`
- `order.payment_required`
- `order.paid`
- `order.failed`
- `order.reply`

## Advanced Agent Actions

Legacy visual action endpoints remain available for custom roles:

- `POST /agents/register`
- `POST /agents/{agent_id}/heartbeat`
- `POST /agents/{agent_id}/actions`

Use these only for visual progress events; do not use them to create orders or alter balances.
