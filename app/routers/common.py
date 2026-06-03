"""
/* ========================================================================== */
/* GEB L3: 路由共享序列化                                                     */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models、api_error 与 credentials 配置状态 helper
 * [OUTPUT]: 对外提供 require helper 与 api-key/customer/inquiry/message/product/pricing-rule-version/approval/notification/quotation/delivery_attempt 等响应序列化函数
 * [POS]: routers 的共享边界层，让各资源路由复用一致的租户校验与响应形状
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from sqlalchemy.orm import Session

from app import models
from app.errors import api_error
from app.services.credentials import credentials_key_status, is_credentials_configured


def require_inquiry(session: Session, seller_id: int, inquiry_id: int) -> models.Inquiry:
    inquiry = session.get(models.Inquiry, inquiry_id)
    if inquiry is None or inquiry.seller_id != seller_id:
        raise api_error(404, "inquiry_not_found", "Inquiry not found")
    return inquiry


def require_conversation(session: Session, seller_id: int, conversation_id: int) -> models.Conversation:
    conversation = session.get(models.Conversation, conversation_id)
    if conversation is None or conversation.seller_id != seller_id:
        raise api_error(404, "conversation_not_found", "Conversation not found")
    return conversation


def customer_summary(customer: models.Customer | None) -> dict | None:
    if customer is None:
        return None
    return {
        "id": customer.id,
        "company": customer.company,
        "name": customer.name,
        "country": customer.country,
        "email": customer.email,
        "phone": customer.phone,
    }


def api_key_item(api_key: models.SellerApiKey) -> dict:
    return {
        "id": api_key.id,
        "name": api_key.name,
        "token_prefix": api_key.token_prefix,
        "scopes": api_key.scopes or [],
        "status": api_key.status,
        "last_used_at": api_key.last_used_at,
        "revoked_at": api_key.revoked_at,
        "created_at": api_key.created_at,
    }


def customer_item(customer: models.Customer) -> dict:
    return customer_summary(customer) | {
        "channels": customer.channels or {},
        "grade": customer.grade,
        "enrichment": customer.enrichment or {},
        "preferences": customer.preferences or {},
        "status": customer.status,
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
    }


def inquiry_list_item(session: Session, inquiry: models.Inquiry) -> dict:
    customer = session.get(models.Customer, inquiry.customer_id)
    return {
        "id": inquiry.id,
        "customer": customer_summary(customer),
        "source_channel": inquiry.source_channel,
        "grade": inquiry.grade,
        "score": float(inquiry.score) if inquiry.score is not None else None,
        "status": inquiry.status,
        "summary": inquiry.raw_content[:160] if inquiry.raw_content else None,
        "received_at": inquiry.received_at,
    }


def inquiry_detail(session: Session, inquiry: models.Inquiry) -> dict:
    return inquiry_list_item(session, inquiry) | {
        "customer_id": inquiry.customer_id,
        "raw_content": inquiry.raw_content,
        "parsed": inquiry.parsed or {},
        "language": inquiry.language,
    }


def message_item(message: models.Message) -> dict:
    return {
        "id": message.id,
        "sender_role": message.sender_role,
        "channel_message_id": message.channel_message_id,
        "content": message.content,
        "language": message.language,
        "sent_at": message.sent_at,
    }


def delivery_attempt_item(attempt: models.DeliveryAttempt) -> dict:
    return {
        "id": attempt.id,
        "message_id": attempt.message_id,
        "channel_account_id": attempt.channel_account_id,
        "channel": attempt.channel,
        "external_id": attempt.external_id,
        "status": attempt.status,
        "client": attempt.client,
        "provider_message_id": attempt.provider_message_id,
        "attempt_count": attempt.attempt_count,
        "next_retry_at": attempt.next_retry_at,
        "error": attempt.error,
        "payload": attempt.payload or {},
        "response": attempt.response or {},
        "created_at": attempt.created_at,
    }


def knowledge_item(chunk: models.KnowledgeChunk, score: float | None) -> dict:
    return {
        "chunk_id": chunk.id,
        "source_type": chunk.source_type,
        "source_ref": chunk.source_ref,
        "content": chunk.content,
        "score": score,
    }


def product_item(product: models.Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "specs": product.specs or {},
        "cost": float(product.cost) if product.cost is not None else None,
        "currency": product.currency,
        "moq": product.moq,
        "images": product.images or [],
        "description": product.description,
        "status": product.status,
    }


def pricing_rule_item(rule: models.PricingRule) -> dict:
    return {
        "id": rule.id,
        "product_id": rule.product_id,
        "margin_rate": float(rule.margin_rate) if rule.margin_rate is not None else None,
        "logistics_template": rule.logistics_template or {},
        "exchange_source": rule.exchange_source,
        "tiered_prices": rule.tiered_prices or [],
        "valid_days": rule.valid_days,
        "floor_price": float(rule.floor_price),
        "currency": rule.currency,
    }


def pricing_rule_version_item(version: models.PricingRuleVersion) -> dict:
    return {
        "id": version.id,
        "pricing_rule_id": version.pricing_rule_id,
        "version": version.version,
        "actor": version.actor,
        "action_type": version.action_type,
        "snapshot": version.snapshot or {},
        "created_at": version.created_at,
    }


def channel_item(channel: models.ChannelAccount) -> dict:
    return {
        "id": channel.id,
        "channel_type": channel.channel_type,
        "name": channel.name,
        "status": channel.status,
        "credentials_configured": is_credentials_configured(channel.credentials),
        "credentials_key_status": credentials_key_status(channel.credentials),
    }


def approval_item(approval: models.Approval) -> dict:
    return {
        "id": approval.id,
        "conversation_id": approval.conversation_id,
        "inquiry_id": approval.inquiry_id,
        "type": approval.type,
        "reason": approval.reason,
        "summary": approval.summary,
        "suggestion": approval.suggestion,
        "payload": approval.payload or {},
        "status": approval.status,
        "executed": approval.executed,
        "created_at": approval.created_at,
    }


def notification_item(notification: models.Notification) -> dict:
    return {
        "id": notification.id,
        "type": notification.type,
        "severity": notification.severity,
        "title": notification.title,
        "body": notification.body,
        "target_type": notification.target_type,
        "target_id": notification.target_id,
        "context": notification.context or {},
        "status": notification.status,
        "read_at": notification.read_at,
        "created_at": notification.created_at,
    }


def quotation_detail(quotation: models.Quotation) -> dict:
    return {
        "id": quotation.id,
        "inquiry_id": quotation.inquiry_id,
        "customer_id": quotation.customer_id,
        "currency": quotation.currency,
        "total_amount": float(quotation.total_amount) if quotation.total_amount is not None else None,
        "valid_until": quotation.valid_until,
        "is_pi": quotation.is_pi,
        "status": quotation.status,
        "created_by": quotation.created_by,
        "hits_floor": quotation.hits_floor,
        "terms": quotation.terms or {},
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "amount": float(item.amount),
            }
            for item in quotation.items
        ],
    }
