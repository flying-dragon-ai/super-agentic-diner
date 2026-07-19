# A2A Super Order API

All Skill business APIs require a browser-linked project account. Passwords are accepted only by the existing web `/auth/login` and `/auth/register` endpoints.

## Device authorization

### `POST /skill/auth/device/start`

Header: `X-Evomap-Node-Secret` when the backend requires remote EvoMap verification.

Request fields: `tool_name`, `display_name`, `evomap_node_id`, optional `evomap_did`.

Response fields: `device_code`, `user_code`, `verification_uri`, `verification_uri_complete`, `expires_in=600`, `interval=2`. The device code is secret and must remain in CLI memory only.

### Browser approval

Open `verification_uri_complete`. The page checks the existing httpOnly café session. A logged-out user is sent to `/welcome?next=...`, which uses the normal `/auth/login` or `/auth/register` backend and returns to the approval page.

- `POST /skill/auth/device/approve` with `{ "user_code": "ABCD-EFGH" }`
- `POST /skill/auth/device/deny` with the same body

Both require the signed project account cookie.

### `POST /skill/auth/device/token`

Request: `{ "device_code": "opaque-secret" }`.

- `202 authorization_pending`: wait the returned interval and retry.
- `200 authorized`: returns the Agent `api_token` once plus `consumer_id`, `agent_id`, account profile and CNY balance.
- `403 authorization_denied`, `409 device_code_consumed`, or `410 authorization_expired`: stop polling.

## Authenticated account operations

All use `Authorization: Bearer <api_token>`.

- `GET /skill/me`: username, nickname, display name, CNY balance, IDs, node and scopes.
- `GET /skill/menu`: product menu; unlike the web `/menu`, this Skill route requires login.
- `POST /skill/logout`: marks the current Agent token inactive. The node/account link remains.

Missing, legacy-unlinked or revoked tokens return HTTP 401 with `code=account_login_required`.

## CNY order

`POST /skill/orders`

```json
{
  "consumer_id": 1,
  "agent_id": 2,
  "message": "一杯拿铁",
  "request_id": "req-a2a-001",
  "auto_confirm": true
}
```

Success:

```json
{
  "ok": true,
  "status": "completed",
  "coffee_names": ["拿铁"],
  "amount_cny": 18.0,
  "currency": "CNY",
  "balance_after": 32.0,
  "amount_credits": 0,
  "free_orders_remaining": 0,
  "payment_status": "paid",
  "request_id": "req-a2a-001"
}
```

The server atomically checks/debits the linked `UserWallet(CNY)`, decrements stock and creates the Skill-source order. Reusing `request_id` returns the existing order without a second debit. Insufficient funds return HTTP 402 with `code=insufficient_balance`.

`POST /skill/register`, free-order quota, client payment proofs and EvoMap credit payment are legacy-only. Historical ledgers remain available for audit/reconciliation but new CLI traffic must use device authorization and CNY payment.
