# Database Schema Inventory

This project uses SQLAlchemy models as the canonical schema source. The runtime
supports `DB_MODE=sqlite` for zero-config local development and `DB_MODE=mysql`
for the MySQL-backed deployment path. `Base.metadata.create_all()` is used for
fresh databases; existing databases are upgraded by idempotent scripts under
`scripts/`.

The schema cleanup policy is conservative: preserve all historical data, add
missing structures, and soft-retire confirmed dead tables by renaming them to
`*_deprecated`.

## Table Status

| Table | Status | Owner / Purpose |
|---|---|---|
| `user` | active-compat | Legacy customer row; still anchors orders, wallets, profiles, and accounts. `balance` is compatibility-only. |
| `user_account` | active-canonical | Login identity for the 3D cafe app. Links one account to one `user`. |
| `order` | active-canonical-header | Canonical order header for web dialog and A2A Skill orders. Legacy `coffee_name` and `amount` remain compatibility fields. |
| `order_item` | active-canonical | Order line item snapshot. This is the canonical product/price history for new order reads. |
| `order_item_option` | active-canonical | Snapshot of selected options for each order line. |
| `coffee_kb` | active-compat | Legacy menu/RAG table. Kept for rollback and seed compatibility; new reads should use `product`. |
| `product` | active-canonical | Sellable catalog and keyword RAG source. |
| `product_option_group` | active-canonical | Product option grouping, such as cup size or milk type. |
| `product_option` | active-canonical | Selectable product option with price delta. |
| `user_wallet` | active-canonical | Per-user, per-currency running balance cache. |
| `balance_transaction` | active-canonical | Append-only balance ledger. |
| `agent_profile` | active-canonical | Tool/customer/staff agent identity shown in the visualization scene. |
| `evomap_consumer` | active-canonical | EvoMap consumer identity used by A2A Skill ordering. |
| `skill_order_ledger` | active-canonical | A2A Skill order/payment ledger for free quota and EvoMap credit payment proofs. |
| `visualization_event` | active-canonical | Persistent visualization event stream for replay and WebSocket sync. |
| `office_layout` | active-canonical | Server-side 3D cafe layout persistence. |
| `chat_message` | active-canonical | Durable chat archive used by long-term profile summarization. |
| `user_profile` | active-canonical | LLM-summarized user preference/profile row. |
| `agent_experience` | active-canonical | Reviewer/recommender agent experience memory persisted beside Redis. |
| `visitor_insight` | active-canonical | Per-visit analytics for dashboard and churn analysis. |
| `chat_messages` | deprecated-if-present | Old plural chat table. Rename to `chat_messages_deprecated` if found. |
| `pending_orders` | deprecated-if-present | Old pending-order table. Redis-backed pending order memory replaced it. Rename to `pending_orders_deprecated` if found. |

## Compatibility Boundaries

- `order.coffee_name` and `order.amount` are still written for existing readers
  and tests. New domain reads should prefer `order_item` and fall back to these
  fields only for historical rows without line items.
- `coffee_kb` is seeded for rollback compatibility. Menu, price matching, and
  keyword RAG should read `product`.
- `user.balance` is retained for legacy visibility. Balance-changing code should
  read and write `user_wallet` plus `balance_transaction`.
- `chat_message` is the durable archive. Redis/fakeredis remains the short-term
  conversation and pending-order memory layer.

## Migration Entry Points

Fresh local database:

```powershell
python scripts/init_db.py
```

Existing database consistency pass:

```powershell
python scripts/migrate_schema_consistency.py
```

Existing MySQL databases that predate the catalog/order/wallet refactor should
run the focused migrations first, then the consistency pass:

```powershell
python scripts/migrate_product_catalog.py
python scripts/migrate_order_lineitem.py
python scripts/migrate_wallet_ledger.py
python scripts/migrate_order_sources.py
python scripts/migrate_chat_message.py
python scripts/migrate_user_profile.py
python scripts/migrate_agent_experience.py
python scripts/migrate_schema_consistency.py
```

All scripts must be safe to run more than once. They must not print secrets or
hard-code connection strings; connection details come from `.env` through
`app.config`.

## Phase 2 Refactor Target

The next domain refactor should introduce one internal order summary reader that
returns names, quantities, selected options, and totals from `order_item` first
and from `order.coffee_name` / `order.amount` only as a fallback. Use that reader
for order history, reorder, Skill visualization payloads, and dashboard views
before removing any compatibility fields in a later migration.
