"""Shared domain constants for orders, payment, and identities."""

ORDER_SOURCE_WEB_DIALOG = "web_dialog"
ORDER_SOURCE_SKILL = "skill"
ORDER_SOURCE_TYPES = frozenset({ORDER_SOURCE_WEB_DIALOG, ORDER_SOURCE_SKILL})

ORDER_STATUS_PENDING = 0
ORDER_STATUS_PAID = 1
ORDER_STATUS_FAILED = 2
ORDER_STATUS_CANCELLED = 3
ORDER_STATUS_REFUNDED = 4
ORDER_STATUSES = frozenset(
    {
        ORDER_STATUS_PENDING,
        ORDER_STATUS_PAID,
        ORDER_STATUS_FAILED,
        ORDER_STATUS_CANCELLED,
        ORDER_STATUS_REFUNDED,
    }
)

PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_PAYMENT_PENDING = "payment_pending"
PAYMENT_STATUS_PAYMENT_REQUIRED = "payment_required"
PAYMENT_STATUS_PAYMENT_FAILED = "payment_failed"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_FREE = "free"
PAYMENT_STATUS_NEEDS_RECONCILE = "needs_reconcile"
PAYMENT_STATUS_REFUNDED = "refunded"

ORDER_PAYMENT_STATUSES = frozenset(
    {
        PAYMENT_STATUS_PAYMENT_PENDING,
        PAYMENT_STATUS_PAYMENT_REQUIRED,
        PAYMENT_STATUS_PAYMENT_FAILED,
        PAYMENT_STATUS_PAID,
        PAYMENT_STATUS_FREE,
        PAYMENT_STATUS_NEEDS_RECONCILE,
        PAYMENT_STATUS_REFUNDED,
    }
)

LEDGER_PAYMENT_STATUSES = frozenset(
    {
        PAYMENT_STATUS_PENDING,
        PAYMENT_STATUS_PAYMENT_PENDING,
        PAYMENT_STATUS_PAYMENT_REQUIRED,
        PAYMENT_STATUS_PAYMENT_FAILED,
        PAYMENT_STATUS_PAID,
        PAYMENT_STATUS_FREE,
        PAYMENT_STATUS_NEEDS_RECONCILE,
        PAYMENT_STATUS_REFUNDED,
    }
)

IDENTITY_STATUS_ACTIVE = "active"
IDENTITY_STATUS_INACTIVE = "inactive"
IDENTITY_STATUS_DISABLED = "disabled"
IDENTITY_STATUSES = frozenset(
    {IDENTITY_STATUS_ACTIVE, IDENTITY_STATUS_INACTIVE, IDENTITY_STATUS_DISABLED}
)

# ---------------------------------------------------------------------------
# Product catalog domain constants.
# ---------------------------------------------------------------------------

PRODUCT_STATUS_AVAILABLE = "available"
PRODUCT_STATUS_DISABLED = "disabled"
PRODUCT_STATUS_SOLD_OUT = "sold_out"
PRODUCT_STATUSES = frozenset(
    {PRODUCT_STATUS_AVAILABLE, PRODUCT_STATUS_DISABLED, PRODUCT_STATUS_SOLD_OUT}
)

# How many options a customer may pick within one option group.
OPTION_SELECTION_SINGLE = "single"
OPTION_SELECTION_MULTI = "multi"
OPTION_SELECTION_TYPES = frozenset({OPTION_SELECTION_SINGLE, OPTION_SELECTION_MULTI})

OPTION_STATUS_ACTIVE = "active"
OPTION_STATUS_DISABLED = "disabled"
OPTION_STATUSES = frozenset({OPTION_STATUS_ACTIVE, OPTION_STATUS_DISABLED})

# ---------------------------------------------------------------------------
# Unified multi-currency ledger domain constants.
# ---------------------------------------------------------------------------

WALLET_CURRENCY_CNY = "CNY"
WALLET_CURRENCY_CREDITS = "credits"
WALLET_CURRENCIES = frozenset({WALLET_CURRENCY_CNY, WALLET_CURRENCY_CREDITS})

# balance_transaction.type values. amount sign convention: + = credit, - = debit.
TRANSACTION_TYPE_TOPUP = "topup"
TRANSACTION_TYPE_CONSUME = "consume"
TRANSACTION_TYPE_REFUND = "refund"
TRANSACTION_TYPE_FREE_ORDER = "free_order"
TRANSACTION_TYPE_ADJUST = "adjust"
TRANSACTION_TYPES = frozenset(
    {
        TRANSACTION_TYPE_TOPUP,
        TRANSACTION_TYPE_CONSUME,
        TRANSACTION_TYPE_REFUND,
        TRANSACTION_TYPE_FREE_ORDER,
        TRANSACTION_TYPE_ADJUST,
    }
)
