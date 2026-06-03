"""
/* ========================================================================== */
/* GEB L3: 出站渠道投递边界                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models、EmailAdapter、WhatsAppAdapter、credentials 与 channel_delivery_clients
 * [OUTPUT]: 对外提供 deliver_message，为 email/whatsapp/site_form 生成投递结果、payload 与可插拔客户端执行状态
 * [POS]: services 的外部渠道发送边界，把数据库消息与真实渠道客户端之间的接缝收束到单一位置
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.channel_delivery_clients import send_with_delivery_client
from app.services.credentials import reveal_credentials
from app.services.delivery_attempts import record_delivery_attempt
from app.services.email_adapter import EmailAdapter, OutboundEmail
from app.services.whatsapp_adapter import WhatsAppAdapter


def deliver_message(
    session: Session,
    seller_id: int,
    conversation: models.Conversation,
    message: models.Message,
) -> dict[str, Any]:
    customer = session.get(models.Customer, conversation.customer_id)
    seller = session.get(models.Seller, seller_id)
    channel = conversation.channel or "site_form"
    external_id = f"closer:{channel}:out:{message.id}"
    message.channel_message_id = external_id
    account = _channel_account(session, seller_id, channel)
    credentials = reveal_credentials(account.credentials) if account is not None else {}

    if channel == "email":
        result = _email_delivery(seller, customer, conversation, message, external_id, credentials)
    elif channel == "whatsapp":
        result = _whatsapp_delivery(customer, message, external_id, credentials)
    else:
        result = {
            "status": "recorded",
            "channel": channel,
            "external_id": external_id,
            "payload": {"content": message.content},
            "client": {"status": "recorded", "client": "local_record"},
        }

    result["channel_account_id"] = account.id if account else None
    attempt = record_delivery_attempt(session, seller_id, message, result)
    result["delivery_attempt_id"] = attempt.id
    return result


def _email_delivery(
    seller: models.Seller | None,
    customer: models.Customer | None,
    conversation: models.Conversation,
    message: models.Message,
    external_id: str,
    credentials: dict[str, Any],
) -> dict[str, Any]:
    if customer is None or not customer.email:
        return _missing_recipient("email", external_id)
    outbound = OutboundEmail(
        from_email=seller.email if seller else "seller@example.com",
        to_email=customer.email,
        subject=f"Re: Inquiry #{conversation.inquiry_id}",
        body=message.content or "",
        message_id=external_id,
    )
    smtp_message = EmailAdapter().compose_smtp_message(outbound)
    payload = _email_payload(smtp_message)
    client = _send_client("email", payload, credentials)
    return {
        "status": client["status"],
        "channel": "email",
        "external_id": external_id,
        "payload": payload,
        "client": client,
    }


def _whatsapp_delivery(
    customer: models.Customer | None,
    message: models.Message,
    external_id: str,
    credentials: dict[str, Any],
) -> dict[str, Any]:
    phone = _customer_phone(customer)
    if not phone:
        return _missing_recipient("whatsapp", external_id)
    payload = WhatsAppAdapter().compose_text_payload(phone, message.content or "")
    client = _send_client("whatsapp", payload, credentials)
    return {
        "status": client["status"],
        "channel": "whatsapp",
        "external_id": external_id,
        "payload": payload,
        "client": client,
    }


def _customer_phone(customer: models.Customer | None) -> str | None:
    if customer is None:
        return None
    channels = customer.channels or {}
    return customer.phone or channels.get("whatsapp") or channels.get("phone")


def _missing_recipient(channel: str, external_id: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "channel": channel,
        "external_id": external_id,
        "reason": "missing_recipient",
        "payload": {},
        "client": {"status": "skipped", "client": "none"},
    }


def _send_client(channel: str, payload: dict[str, Any], credentials: dict[str, Any]) -> dict[str, Any]:
    try:
        return send_with_delivery_client(channel, payload, credentials)
    except Exception as exc:
        return {"status": "failed", "client": "delivery_client", "error": str(exc)}


def _email_payload(message: EmailMessage) -> dict[str, str]:
    return {
        "from": str(message["From"]),
        "to": str(message["To"]),
        "subject": str(message["Subject"]),
        "message_id": str(message["Message-ID"]),
        "body": message.get_content(),
    }


def _channel_account(session: Session, seller_id: int, channel: str) -> models.ChannelAccount | None:
    return session.scalar(
        select(models.ChannelAccount)
        .where(models.ChannelAccount.seller_id == seller_id)
        .where(models.ChannelAccount.channel_type == channel)
        .order_by(models.ChannelAccount.id.desc())
    )
