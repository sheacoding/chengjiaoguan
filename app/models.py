"""
/* ========================================================================== */
/* GEB L3: ORM 数据模型                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy ORM、PostgreSQL JSONB 变体与 app.database.Base/utcnow
 * [OUTPUT]: 对外提供 Seller、SellerApiKey、ChannelAccount、Product、PricingRule、PricingRuleVersion、Customer、Inquiry、Conversation、Message、DeliveryAttempt、Quotation、QuotationItem、FollowupTask、KnowledgeChunk、Notification、AuditLog、Approval
 * [POS]: app 的数据库结构真源，必须与 migrations/001_initial.sql 保持同构
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base, utcnow


JsonDict = MutableDict.as_mutable(JSON().with_variant(JSONB, "postgresql"))
JsonList = MutableList.as_mutable(JSON().with_variant(JSONB, "postgresql"))


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SoftDeleteMixin:
    deleted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Seller(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "seller"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    plan: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    ai_disclosure: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict] = mapped_column(JsonDict, default=dict)


class SellerApiKey(IdMixin, TimestampMixin, Base):
    __tablename__ = "seller_api_key"
    __table_args__ = (
        Index("ix_seller_api_key_seller_status", "seller_id", "status"),
        UniqueConstraint("token_hash", name="uq_seller_api_key_token_hash"),
    )

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list] = mapped_column(JsonList, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class ChannelAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "channel_account"
    __table_args__ = (Index("ix_channel_account_seller_id", "seller_id"),)

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))
    credentials: Mapped[dict] = mapped_column(JsonDict, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="connected", nullable=False)


class Product(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "product"
    __table_args__ = (Index("ix_product_seller_id", "seller_id"),)

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(80))
    specs: Mapped[dict] = mapped_column(JsonDict, default=dict)
    cost: Mapped[object | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    moq: Mapped[int | None] = mapped_column(Integer)
    images: Mapped[list] = mapped_column(JsonList, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class PricingRule(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pricing_rule"
    __table_args__ = (Index("ix_pricing_rule_seller_id", "seller_id"),)

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"))
    margin_rate: Mapped[object | None] = mapped_column(Numeric(6, 4))
    logistics_template: Mapped[dict] = mapped_column(JsonDict, default=dict)
    exchange_source: Mapped[str | None] = mapped_column(String(40))
    tiered_prices: Mapped[list] = mapped_column(JsonList, default=list)
    valid_days: Mapped[int | None] = mapped_column(Integer)
    floor_price: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)


class PricingRuleVersion(IdMixin, Base):
    __tablename__ = "pricing_rule_version"
    __table_args__ = (
        Index("ix_pricing_rule_version_rule_id", "pricing_rule_id"),
        Index("ix_pricing_rule_version_seller_id", "seller_id"),
        UniqueConstraint("pricing_rule_id", "version", name="uq_pricing_rule_version_rule_version"),
    )

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    pricing_rule_id: Mapped[int] = mapped_column(ForeignKey("pricing_rule.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(12))
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Customer(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "customer"
    __table_args__ = (
        Index("ix_customer_seller_email", "seller_id", "email"),
        Index("ix_customer_seller_grade", "seller_id", "grade"),
    )

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(160))
    company: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40))
    channels: Mapped[dict] = mapped_column(JsonDict, default=dict)
    grade: Mapped[str | None] = mapped_column(String(1))
    enrichment: Mapped[dict] = mapped_column(JsonDict, default=dict)
    preferences: Mapped[dict] = mapped_column(JsonDict, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class Inquiry(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "inquiry"
    __table_args__ = (
        Index("ix_inquiry_seller_status", "seller_id", "status"),
        Index("ix_inquiry_seller_grade", "seller_id", "grade"),
        Index("ix_inquiry_customer_id", "customer_id"),
    )

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), nullable=False)
    channel_account_id: Mapped[int | None] = mapped_column(ForeignKey("channel_account.id"))
    source_channel: Mapped[str | None] = mapped_column(String(20))
    raw_content: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[dict] = mapped_column(JsonDict, default=dict)
    grade: Mapped[str | None] = mapped_column(String(1))
    score: Mapped[object | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    language: Mapped[str | None] = mapped_column(String(12))
    received_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship()


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversation"
    __table_args__ = (Index("ix_conversation_seller_id", "seller_id"),)

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), nullable=False)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiry.id"), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str | None] = mapped_column(String(12))
    is_human_takeover: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)

    customer: Mapped[Customer] = relationship()
    inquiry: Mapped[Inquiry] = relationship()


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "message"
    __table_args__ = (
        Index("ix_message_conversation_sent_at", "conversation_id", "sent_at"),
        UniqueConstraint("channel_message_id", name="uq_message_channel_message_id"),
    )

    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversation.id"), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(12), nullable=False)
    channel_message_id: Mapped[str | None] = mapped_column(String(120))
    content: Mapped[str | None] = mapped_column(Text)
    attachments: Mapped[list] = mapped_column(JsonList, default=list)
    language: Mapped[str | None] = mapped_column(String(12))
    sent_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class DeliveryAttempt(IdMixin, TimestampMixin, Base):
    __tablename__ = "delivery_attempt"
    __table_args__ = (
        Index("ix_delivery_attempt_seller_status", "seller_id", "status"),
        Index("ix_delivery_attempt_next_retry", "next_retry_at", "status"),
        Index("ix_delivery_attempt_message_id", "message_id"),
    )

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), nullable=False)
    channel_account_id: Mapped[int | None] = mapped_column(ForeignKey("channel_account.id"))
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    client: Mapped[str | None] = mapped_column(String(40))
    provider_message_id: Mapped[str | None] = mapped_column(String(120))
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_retry_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JsonDict, default=dict)
    response: Mapped[dict] = mapped_column(JsonDict, default=dict)


class Quotation(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "quotation"
    __table_args__ = (
        Index("ix_quotation_inquiry_id", "inquiry_id"),
        Index("ix_quotation_seller_status", "seller_id", "status"),
    )

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiry.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    total_amount: Mapped[object | None] = mapped_column(Numeric(14, 2))
    terms: Mapped[dict] = mapped_column(JsonDict, default=dict)
    valid_until: Mapped[object | None] = mapped_column(Date)
    is_pi: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(8))
    hits_floor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    items: Mapped[list["QuotationItem"]] = relationship(cascade="all, delete-orphan")


class QuotationItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "quotation_item"
    __table_args__ = (Index("ix_quotation_item_quotation_id", "quotation_id"),)

    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotation.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)


class FollowupTask(IdMixin, TimestampMixin, Base):
    __tablename__ = "followup_task"
    __table_args__ = (Index("ix_followup_next_status", "next_run_at", "status"),)

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiry.id"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversation.id"), nullable=False)
    schedule: Mapped[dict] = mapped_column(JsonDict, default=dict)
    next_run_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(40))


class KnowledgeChunk(IdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_chunk"
    __table_args__ = (Index("ix_knowledge_chunk_seller_id", "seller_id"),)

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(20))
    source_ref: Mapped[str | None] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(JsonList, default=list)


class Notification(IdMixin, TimestampMixin, Base):
    __tablename__ = "notification"
    __table_args__ = (
        Index("ix_notification_seller_status", "seller_id", "status"),
        Index("ix_notification_target", "target_type", "target_id"),
    )

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[int | None] = mapped_column(Integer)
    context: Mapped[dict] = mapped_column(JsonDict, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="unread", nullable=False)
    read_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_seller_created_at", "seller_id", "created_at"),)

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(12))
    action_type: Mapped[str | None] = mapped_column(String(40))
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[int | None] = mapped_column(Integer)
    is_auto: Mapped[bool | None] = mapped_column(Boolean)
    snapshot: Mapped[dict] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Approval(IdMixin, TimestampMixin, Base):
    __tablename__ = "approval"
    __table_args__ = (
        Index("ix_approval_seller_status", "seller_id", "status"),
        Index("ix_approval_conversation_id", "conversation_id"),
    )

    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversation.id"), nullable=False)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiry.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JsonDict, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    executed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
