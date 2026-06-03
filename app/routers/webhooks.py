"""
/* ========================================================================== */
/* GEB L3: Webhook 路由                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、数据库 session、seller 依赖、InboundMessage 与渠道适配服务
 * [OUTPUT]: 对外提供 router，暴露 POST /api/v1/webhooks/{channel}
 * [POS]: routers 的公开入站边界，把渠道 payload 归一化后交给 channel_gateway
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.schemas import InboundMessage, WebhookIngestResponse
from app.services.channel_gateway import ingest_inbound_message
from app.services.whatsapp_adapter import WhatsAppAdapter


router = APIRouter(prefix="/api/v1")


@router.post("/webhooks/{channel}", response_model=WebhookIngestResponse, status_code=201)
def ingest_webhook(
    channel: str,
    payload: dict,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> WebhookIngestResponse:
    if payload.get("channel") and payload["channel"] != channel:
        raise api_error(400, "channel_mismatch", "Path channel must match payload channel")
    if channel == "site_form":
        inbound = InboundMessage.model_validate(payload)
    elif channel == "whatsapp":
        try:
            inbound = WhatsAppAdapter().normalize_webhook(payload)
        except ValueError as exc:
            raise api_error(400, "invalid_webhook_payload", str(exc)) from exc
    else:
        raise api_error(400, "unsupported_channel", f"{channel} webhook is not implemented")
    if channel != inbound.channel:
        raise api_error(400, "channel_mismatch", "Path channel must match payload channel")
    inquiry, conversation, message, duplicate = ingest_inbound_message(session, seller_id, inbound)
    session.commit()
    return WebhookIngestResponse(
        inquiry_id=inquiry.id,
        conversation_id=conversation.id,
        message_id=message.id,
        customer_id=inquiry.customer_id,
        duplicate=duplicate,
    )
