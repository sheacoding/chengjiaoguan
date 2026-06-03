"""
/* ========================================================================== */
/* GEB L3: Pydantic 契约                                                      */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 Pydantic BaseModel/Field、Decimal、date/datetime 与 typing Literal/Any
 * [OUTPUT]: 对外提供 webhook、询盘、消息、客户补丁、卖家设置补丁、API key、产品创建/补丁、价格规则、汇率缓存刷新、渠道、知识、审批、通知、报价补丁等请求/响应模型
 * [POS]: app 的输入输出类型边界，被 main.py、adapters 与 tests 消费
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChannelContact(BaseModel):
    name: str | None = None
    company: str | None = None
    country: str | None = None
    email: str | None = None
    phone: str | None = None


class InboundMessage(BaseModel):
    channel: Literal["site_form", "email", "whatsapp"]
    channel_message_id: str
    from_: ChannelContact = Field(alias="from")
    content: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    received_at: datetime | None = None
    language: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class WebhookIngestResponse(BaseModel):
    inquiry_id: int
    conversation_id: int
    message_id: int
    customer_id: int
    duplicate: bool = False


class InquiryPatch(BaseModel):
    grade: str | None = None
    status: str | None = None


class MessageCreate(BaseModel):
    content: str
    language: str | None = None


class CustomerPatch(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    company: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    channels: dict[str, Any] | None = None
    grade: Literal["A", "B", "C"] | None = None
    enrichment: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=20)


class SellerSettingsPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    plan: str | None = Field(default=None, min_length=1, max_length=20)
    ai_disclosure: bool | None = None
    settings: dict[str, Any] | None = None


class ApiKeyCreate(BaseModel):
    name: str = Field(default="API key", min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list)


class KnowledgeCreate(BaseModel):
    source_type: str = Field(default="faq", min_length=1, max_length=20)
    source_ref: str | None = Field(default=None, max_length=120)
    content: str = Field(min_length=1)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=80)
    specs: dict[str, Any] = Field(default_factory=dict)
    cost: Decimal | None = None
    currency: str = Field(default="USD", max_length=8)
    moq: int | None = Field(default=None, gt=0)
    images: list[str] = Field(default_factory=list)
    description: str | None = None
    status: str = Field(default="active", max_length=20)


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=80)
    specs: dict[str, Any] | None = None
    cost: Decimal | None = None
    currency: str | None = Field(default=None, max_length=8)
    moq: int | None = Field(default=None, gt=0)
    images: list[str] | None = None
    description: str | None = None
    status: str | None = Field(default=None, max_length=20)


class PricingRuleCreate(BaseModel):
    product_id: int | None = None
    margin_rate: Decimal | None = None
    logistics_template: dict[str, Any] = Field(default_factory=dict)
    exchange_source: str | None = Field(default=None, max_length=40)
    tiered_prices: list[dict[str, Any]] = Field(default_factory=list)
    valid_days: int | None = Field(default=None, gt=0)
    floor_price: Decimal
    currency: str = Field(default="USD", max_length=8)


class PricingRulePatch(BaseModel):
    product_id: int | None = None
    margin_rate: Decimal | None = None
    logistics_template: dict[str, Any] | None = None
    exchange_source: str | None = Field(default=None, max_length=40)
    tiered_prices: list[dict[str, Any]] | None = None
    valid_days: int | None = Field(default=None, gt=0)
    floor_price: Decimal | None = None
    currency: str | None = Field(default=None, max_length=8)


class ExchangeRateCacheRefresh(BaseModel):
    target_currencies: list[str] = Field(min_length=1)
    source_currency: str | None = Field(default=None, max_length=8)
    ttl_days: int = Field(default=1, gt=0)
    source: str | None = Field(default=None, max_length=40)
    rates: dict[str, Any] | None = None
    endpoint: str | None = None


class ChannelAccountCreate(BaseModel):
    channel_type: Literal["site_form", "email", "whatsapp", "alibaba", "instagram", "facebook"]
    name: str | None = Field(default=None, max_length=120)
    credentials: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="connected", max_length=20)


class ApprovalPatch(BaseModel):
    payload: dict[str, Any] | None = None
    suggestion: str | None = None
    summary: str | None = None


class ApprovalReject(BaseModel):
    reason: str | None = None


class NotificationPatch(BaseModel):
    status: Literal["unread", "read", "archived"]


class QuotationItemPatch(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: Decimal
    amount: Decimal | None = None


class QuotationPatch(BaseModel):
    terms: dict[str, Any] | None = None
    valid_until: date | None = None
    status: str | None = None
    total_amount: Decimal | None = None
    hits_floor: bool | None = None
    items: list[QuotationItemPatch] | None = None
