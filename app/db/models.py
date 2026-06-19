"""SQLAlchemy models for orders, menu knowledge, Agents, and Skill payments."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    BigInteger,
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

_PK = BigInteger


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


class Order(Base):
    """Paid coffee order for a local customer."""

    __tablename__ = "order"

    order_id = Column(_PK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    coffee_name = Column(String(128), nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)
    request_id = Column(String(64), nullable=True, unique=True)
    source_type = Column(String(32), nullable=False, default="web_dialog")
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
        Index("idx_user_created", "user_id", "created_at"),
        Index("idx_order_source_created", "source_type", "created_at"),
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
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("idx_agent_status_role", "status", "role_type"),)


class VisualizationEvent(Base):
    """Persistent event stream for real-time and replayed pixel visualization."""

    __tablename__ = "visualization_event"

    event_id = Column(_PK, primary_key=True, autoincrement=True)
    agent_id = Column(BigInteger, ForeignKey("agent_profile.agent_id"), nullable=True)
    event_type = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    correlation_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

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
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("idx_evomap_consumer_status", "status"),)


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
        Index("idx_skill_order_consumer", "consumer_id", "created_at"),
        Index("idx_skill_order_payment", "payment_status"),
    )
