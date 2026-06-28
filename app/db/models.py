"""SQLAlchemy models for orders, menu knowledge, Agents, and Skill payments."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)

from app.db.database import Base
from app.domain_constants import (
    IDENTITY_STATUS_ACTIVE,
    IDENTITY_STATUSES,
    LEDGER_PAYMENT_STATUSES,
   OPTION_SELECTION_TYPES,
    OPTION_SELECTION_SINGLE,
   OPTION_STATUSES,
    OPTION_STATUS_ACTIVE,
    ORDER_PAYMENT_STATUSES,
    ORDER_SOURCE_TYPES,
    ORDER_SOURCE_WEB_DIALOG,
    ORDER_STATUSES,
    PAYMENT_STATUS_PAID,
    PRODUCT_STATUSES,
    PRODUCT_STATUS_AVAILABLE,
    TRANSACTION_TYPES,
    WALLET_CURRENCIES,
)

# 主键类型：MySQL 用 BigInteger(大整数)，SQLite 用 Integer(普通整数)。
# SQLite 要求 INTEGER PRIMARY KEY 才能自动自增，BigInteger 在 SQLite 下不会自增。
_PK = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    """Customer account with local balance and preference data."""

    __tablename__ = "user"

    user_id = Column(_PK, primary_key=True, autoincrement=True)
    nickname = Column(String(64), nullable=True)
    balance = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    taste_preference = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class UserAccount(Base):
    """Login account for the 3D office app. Kept separate from the legacy
    anonymous `user` table so existing chat/order flows stay untouched. On
    register we also create a matching `user` row to back ordering by user_id."""

    __tablename__ = "user_account"

    account_id = Column(_PK, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    nickname = Column(String(64), nullable=True)
    user_id = Column(_PK, ForeignKey("user.user_id"), nullable=False, unique=True)
    status = Column(String(16), nullable=False, default=IDENTITY_STATUS_ACTIVE)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in sorted(IDENTITY_STATUSES))})",
            name="ck_user_account_status",
        ),
    )


class Order(Base):
    """Paid coffee order for a local customer."""

    __tablename__ = "order"

    order_id = Column(_PK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    coffee_name = Column(String(128), nullable=True)
    amount = Column(DECIMAL(10, 2), nullable=True)
    status = Column(SmallInteger, nullable=False, default=0)
    total_amount = Column(DECIMAL(10, 2), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    request_id = Column(String(64), nullable=True, unique=True)
    source_type = Column(String(32), nullable=False, default=ORDER_SOURCE_WEB_DIALOG)
    payment_status = Column(String(32), nullable=False, default=PAYMENT_STATUS_PAID)
    consumer_url = Column(String(512), nullable=True)
    consumer_id = Column(BigInteger, ForeignKey("evomap_consumer.consumer_id"), nullable=True)
    agent_id = Column(BigInteger, ForeignKey("agent_profile.agent_id"), nullable=True)
    ledger_id = Column(BigInteger, ForeignKey("skill_order_ledger.ledger_id"), nullable=True)
    correlation_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"source_type IN ({', '.join(repr(value) for value in sorted(ORDER_SOURCE_TYPES))})",
            name="ck_order_source_type",
        ),
        CheckConstraint(
            f"status IN ({', '.join(str(value) for value in sorted(ORDER_STATUSES))})",
            name="ck_order_status",
        ),
        CheckConstraint(
            f"payment_status IN ({', '.join(repr(value) for value in sorted(ORDER_PAYMENT_STATUSES))})",
            name="ck_order_payment_status",
        ),
        Index("idx_user_created", "user_id", "created_at"),
        Index("idx_order_source_created", "source_type", "created_at"),
        Index("idx_order_payment_status", "payment_status"),
        Index("idx_order_consumer_url", "consumer_url"),
        Index("idx_order_consumer", "consumer_id"),
        Index("idx_order_agent", "agent_id"),
        Index("idx_order_ledger", "ledger_id"),
        Index("idx_order_correlation", "correlation_id"),
    )


class CoffeeKB(Base):
    """Coffee menu knowledge used by keyword RAG and price matching."""

    __tablename__ = "coffee_kb"

    id = Column(_PK, primary_key=True, autoincrement=True)
    coffee_name = Column(String(128), nullable=False)
    content = Column(Text, nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    tags = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class AgentProfile(Base):
    """External Agent tool identity shown in the restaurant scene."""

    __tablename__ = "agent_profile"

    agent_id = Column(_PK, primary_key=True, autoincrement=True)
    tool_name = Column(String(64), nullable=False)
    display_name = Column(String(128), nullable=False)
    role_type = Column(String(32), nullable=False, default="waiter")
    capabilities_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    api_token_hash = Column(String(128), nullable=False)
    sprite_seed = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default=IDENTITY_STATUS_ACTIVE)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in sorted(IDENTITY_STATUSES))})",
            name="ck_agent_profile_status",
        ),
        Index("idx_agent_status_role", "status", "role_type"),
    )


class VisualizationEvent(Base):
    """Persistent event stream for real-time and replayed pixel visualization."""

    __tablename__ = "visualization_event"

    event_id = Column(_PK, primary_key=True, autoincrement=True)
    agent_id = Column(BigInteger, ForeignKey("agent_profile.agent_id"), nullable=True)
    event_type = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    correlation_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_viz_event_created", "created_at"),
        Index("idx_viz_event_correlation", "correlation_id"),
    )


class EvomapConsumer(Base):
    """EvoMap consumer identity used by A2A Skill ordering."""

    __tablename__ = "evomap_consumer"

    consumer_id = Column(_PK, primary_key=True, autoincrement=True)
    evomap_node_id = Column(String(128), nullable=False, unique=True)
    evomap_did = Column(String(255), nullable=True)
    display_name = Column(String(128), nullable=False)
    local_user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=True)
    free_orders_used = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default=IDENTITY_STATUS_ACTIVE)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in sorted(IDENTITY_STATUSES))})",
            name="ck_evomap_consumer_status",
        ),
        Index("idx_evomap_consumer_status", "status"),
    )


class SkillOrderLedger(Base):
    """A2A Skill order ledger for free quota and EvoMap payment proofs."""

    __tablename__ = "skill_order_ledger"

    ledger_id = Column(_PK, primary_key=True, autoincrement=True)
    consumer_id = Column(
        BigInteger,
        ForeignKey("evomap_consumer.consumer_id"),
        nullable=False,
    )
    agent_id = Column(BigInteger, ForeignKey("agent_profile.agent_id"), nullable=False)
    request_id = Column(String(128), nullable=False, unique=True)
    order_ids_json = Column(Text, nullable=True)
    coffee_items_json = Column(Text, nullable=False)
    amount_credits = Column(Integer, nullable=False)
    payment_status = Column(String(32), nullable=False)
    evomap_order_id = Column(String(128), nullable=True)
    payment_proof_json = Column(Text, nullable=True)
    free_order_sequence = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"payment_status IN ({', '.join(repr(value) for value in sorted(LEDGER_PAYMENT_STATUSES))})",
            name="ck_skill_order_ledger_payment_status",
        ),
        Index("idx_skill_order_consumer", "consumer_id", "created_at"),
        Index("idx_skill_order_payment", "payment_status"),
    )


# ---------------------------------------------------------------------------
# Product catalog (normalized menu + RAG source; replaces coffee_kb).
# ---------------------------------------------------------------------------


class Product(Base):
    """Sellable product that also backs keyword/price RAG."""

    __tablename__ = "product"

    product_id = Column(_PK, primary_key=True, autoincrement=True)
    sku = Column(String(64), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    category = Column(String(64), nullable=True)
    description = Column(Text, nullable=False)
    base_price = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    tags = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default=PRODUCT_STATUS_AVAILABLE)
    stock = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(v) for v in sorted(PRODUCT_STATUSES))})",
            name="ck_product_status",
        ),
        CheckConstraint("stock >= 0", name="ck_product_stock_nonneg"),
        Index("idx_product_status", "status"),
        Index("idx_product_category", "category"),
    )


class ProductOptionGroup(Base):
    """A group of configurable options for a product (cup size, milk, etc.)."""

    __tablename__ = "product_option_group"

    group_id = Column(_PK, primary_key=True, autoincrement=True)
    product_id = Column(_PK, ForeignKey("product.product_id"), nullable=False)
    name = Column(String(64), nullable=False)
    selection_type = Column(
        String(16), nullable=False, default=OPTION_SELECTION_SINGLE
    )
    is_required = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"selection_type IN ({', '.join(repr(v) for v in sorted(OPTION_SELECTION_TYPES))})",
            name="ck_product_option_group_selection_type",
        ),
        CheckConstraint(
            "is_required IN (0, 1)", name="ck_product_option_group_required"
        ),
        Index("idx_product_option_group_product", "product_id", "sort_order"),
    )


class ProductOption(Base):
    """A single selectable option inside an option group."""

    __tablename__ = "product_option"

    option_id = Column(_PK, primary_key=True, autoincrement=True)
    group_id = Column(_PK, ForeignKey("product_option_group.group_id"), nullable=False)
    name = Column(String(64), nullable=False)
    price_delta = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default=OPTION_STATUS_ACTIVE)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(v) for v in sorted(OPTION_STATUSES))})",
            name="ck_product_option_status",
        ),
        Index("idx_product_option_group_sort", "group_id", "sort_order"),
    )


# ---------------------------------------------------------------------------
# Order line items (snapshot of the catalog at order time).
# ---------------------------------------------------------------------------


class OrderItem(Base):
    """One line of an order. Unit price + selected options are snapshotted so
    later catalog edits never change historical order totals."""

    __tablename__ = "order_item"

    item_id = Column(_PK, primary_key=True, autoincrement=True)
    order_id = Column(_PK, ForeignKey("order.order_id"), nullable=False)
    product_id = Column(_PK, ForeignKey("product.product_id"), nullable=True)
    product_name_snapshot = Column(String(128), nullable=False)
    unit_price = Column(DECIMAL(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    line_total = Column(DECIMAL(10, 2), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_item_quantity"),
        Index("idx_order_item_order", "order_id"),
        Index("idx_order_item_product", "product_id"),
    )


class OrderItemOption(Base):
    """Snapshot of the option(s) chosen for a single order line."""

    __tablename__ = "order_item_option"

    item_option_id = Column(_PK, primary_key=True, autoincrement=True)
    item_id = Column(_PK, ForeignKey("order_item.item_id"), nullable=False)
    group_id = Column(
        _PK, ForeignKey("product_option_group.group_id"), nullable=True
    )
    option_id = Column(_PK, ForeignKey("product_option.option_id"), nullable=True)
    group_name_snapshot = Column(String(64), nullable=True)
    option_name_snapshot = Column(String(64), nullable=True)
    price_delta = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))

    __table_args__ = (
        Index("idx_order_item_option_item", "item_id"),
    )


# ---------------------------------------------------------------------------
# Unified multi-currency ledger.
# ---------------------------------------------------------------------------


class UserWallet(Base):
    """Per-currency running balance cache.

    ``user_id`` + ``currency`` is the composite primary key. CNY is the
    authoritative local balance; ``credits`` mirrors EvoMap Hub spending and its
    ``balance_after`` is informational only (the Hub remains the source of
    truth for credit balance).
    """

    __tablename__ = "user_wallet"

    user_id = Column(
        _PK, ForeignKey("user.user_id"), primary_key=True, nullable=False
    )
    currency = Column(String(16), primary_key=True, nullable=False)
    balance = Column(DECIMAL(18, 4), nullable=False, default=Decimal("0.0000"))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            f"currency IN ({', '.join(repr(v) for v in sorted(WALLET_CURRENCIES))})",
            name="ck_user_wallet_currency",
        ),
    )


class BalanceTransaction(Base):
    """Append-only ledger row.

    ``amount`` is signed: positive credits the wallet, negative debits it.
    ``balance_after`` snapshots the wallet balance right after this row so the
    chain can be audited independently of the running ``user_wallet`` cache.
    """

    __tablename__ = "balance_transaction"

    transaction_id = Column(_PK, primary_key=True, autoincrement=True)
    user_id = Column(_PK, ForeignKey("user.user_id"), nullable=False)
    currency = Column(String(16), nullable=False)
    type = Column(String(32), nullable=False)
    amount = Column(DECIMAL(18, 4), nullable=False)
    balance_after = Column(DECIMAL(18, 4), nullable=True)
    order_id = Column(BigInteger, ForeignKey("order.order_id"), nullable=True)
    ledger_id = Column(
        BigInteger, ForeignKey("skill_order_ledger.ledger_id"), nullable=True
    )
    correlation_id = Column(String(128), nullable=True)
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            f"currency IN ({', '.join(repr(v) for v in sorted(WALLET_CURRENCIES))})",
            name="ck_balance_transaction_currency",
        ),
        CheckConstraint(
            f"type IN ({', '.join(repr(v) for v in sorted(TRANSACTION_TYPES))})",
            name="ck_balance_transaction_type",
        ),
        Index("idx_balance_txn_user_created", "user_id", "currency", "created_at"),
        Index("idx_balance_txn_order", "order_id"),
        Index("idx_balance_txn_ledger", "ledger_id"),
        Index("idx_balance_txn_correlation", "correlation_id"),
    )


# ---------------------------------------------------------------------------
# Agent collaboration: experience memory (experience_agent 双写 MySQL + Redis).
# ---------------------------------------------------------------------------


class AgentExperience(Base):
    """复盘 Agent(事后复盘) 的经验存储，供推荐 Agent(推荐) 下次引用。

    每条记录描述一次 AI(人工智能) 判断失误的教训：推荐了什么、用户实际想要什么、
    失误类型(误判口味/漏听否定词/选错品类)、以及给下次推荐的行动建议。
    """

    __tablename__ = "agent_experience"

    experience_id = Column(_PK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    agent_role = Column(String(32), nullable=False)
    coffee_name = Column(String(128), nullable=True)
    context_tags = Column(String(255), nullable=True)
    insight = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)
    order_id = Column(BigInteger, nullable=True)
    correlation_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_agent_exp_user_tags", "user_id", "context_tags"),
        Index("idx_agent_exp_created", "created_at"),
    )


# ---------------------------------------------------------------------------
# Visitor insights: per-visit analytics for the monitoring dashboard.
# ---------------------------------------------------------------------------


class VisitorInsight(Base):
    """访客洞察：每次访问的意图、是否下单、流失原因、AI 分析结论。

    每个 user_id 每天一条记录（按 visit_date 去重），实时更新意图和下单状态。
    流失时由 LLM 分析聊天历史生成流失原因，并通过 experience_agent 记录到自进化系统。
    """

    __tablename__ = "visitor_insight"

    insight_id = Column(_PK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    visit_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    first_message = Column(Text, nullable=True)
    last_message = Column(Text, nullable=True)
    message_count = Column(Integer, nullable=False, default=0)
    # primary_intent: order(下单) / recommend(求推荐) / chat(闲聊) / browse(浏览)
    primary_intent = Column(String(32), nullable=False, default="browse")
    ordered = Column(Integer, nullable=False, default=0)
    order_id = Column(BigInteger, nullable=True)
    # churn_reason: LLM 分析的流失原因（如「价格偏高」「未找到心仪口味」）
    churn_reason = Column(Text, nullable=True)
    # ai_insight: LLM 生成的综合洞察
    ai_insight = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_visitor_user_date", "user_id", "visit_date"),
        Index("idx_visitor_date", "visit_date"),
        Index("idx_visitor_ordered", "ordered"),
    )


# ---------------------------------------------------------------------------
# 3D cafe editor: server-side layout persistence (global singleton).
# ---------------------------------------------------------------------------


class OfficeLayout(Base):
    """Server-side layout for the 3D cafe editor. Global singleton keyed by
    ``namespace`` ('default'): staff edits it once and every visitor sees the
    same layout, surviving backend restarts and browser changes. The JSON
    payload matches the frontend ``FurnitureItem[]`` shape, so this table is a
    pure storage blob (no relational decomposition needed for ~100 items)."""

    __tablename__ = "office_layout"

    layout_id = Column(_PK, primary_key=True, autoincrement=True)
    namespace = Column(String(32), nullable=False, unique=True)
    layout_json = Column(Text, nullable=False)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_office_layout_namespace", "namespace"),
    )


# ---------------------------------------------------------------------------
# Chat message log: durable archive of every /chat message for user profiling.
# ---------------------------------------------------------------------------


class ChatMessage(Base):
    """对话消息持久化归档（用户画像的数据源）。

    Redis(缓存中间件) 的对话历史只存最近 10 条、30 分钟过期，无法支撑长期画像。
    本表把每条 user/assistant(用户/助手) 消息落库，供 user_profile_service 增量总结。
    写入由 chat_history.add_message 双写触发，best-effort：失败 swallow 不阻断聊天。
    """

    __tablename__ = "chat_message"

    message_id = Column(_PK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    role = Column(String(16), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        # 按用户拉取历史 + 增量游标（last_msg_id 之后）的主查询索引
        Index("idx_chat_msg_user_id", "user_id", "message_id"),
    )


# ---------------------------------------------------------------------------
# User profile: LLM-summarized taste/persona derived from chat + orders.
# ---------------------------------------------------------------------------


class UserProfile(Base):
    """用户画像：基于聊天历史 + 订单历史 + 经验教训，LLM 归纳的口味偏好摘要。

    每个登录用户一行（user_id 唯一）。summary 是 ≤200 字自然语言摘要，
    同步镜像到 User.taste_preference(口味偏好字段) 供前端 /user 端点零改动展示。
    profile_json 存结构化字段（favorite_tags/avoid_tags/price_tier/persona）。
    last_msg_id 是增量游标：下次只总结该 id 之后的新对话，不重复算旧消息。
    """

    __tablename__ = "user_profile"

    profile_id = Column(_PK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False, unique=True)
    summary = Column(String(200), nullable=True)
    profile_json = Column(Text, nullable=True)
    last_msg_id = Column(BigInteger, nullable=False, default=0)
    order_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_user_profile_user_id", "user_id"),
    )
