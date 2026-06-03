"""
/* ========================================================================== */
/* GEB L3: 会话路由                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、SQLAlchemy 查询、MessageCreate、utcnow、channel_delivery 与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 conversations 详情、消息、接管、释放与人工发送接口
 * [POS]: routers 的会话资源边界，处理人工接管态下的人机协作入口
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_session, utcnow
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import customer_summary, message_item, require_conversation
from app.schemas import MessageCreate
from app.services.channel_delivery import deliver_message


router = APIRouter(prefix="/api/v1")


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    conversation = require_conversation(session, seller_id, conversation_id)
    customer = session.get(models.Customer, conversation.customer_id)
    return {
        "id": conversation.id,
        "inquiry_id": conversation.inquiry_id,
        "customer": customer_summary(customer),
        "channel": conversation.channel,
        "language": conversation.language,
        "is_human_takeover": conversation.is_human_takeover,
        "status": conversation.status,
    }


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    conversation = require_conversation(session, seller_id, conversation_id)
    query = (
        select(models.Message)
        .where(models.Message.conversation_id == conversation.id)
        .order_by(models.Message.sent_at.asc().nullslast(), models.Message.id.asc())
    )
    messages = session.scalars(query).all()
    return {"items": [message_item(message) for message in messages], "total": len(messages)}


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def create_message(
    conversation_id: int,
    payload: MessageCreate,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    conversation = require_conversation(session, seller_id, conversation_id)
    if not conversation.is_human_takeover:
        raise api_error(409, "conversation_not_taken_over", "Human messages require takeover mode")
    message = models.Message(
        conversation_id=conversation.id,
        sender_role="human",
        content=payload.content,
        language=payload.language or conversation.language,
        sent_at=utcnow(),
    )
    session.add(message)
    session.flush()
    delivery = deliver_message(session, seller_id, conversation, message)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="reply_sent",
            target_type="conversation",
            target_id=conversation.id,
            is_auto=False,
            snapshot={"content": payload.content, "delivery": delivery},
        )
    )
    session.commit()
    return message_item(message) | {"status": "sent", "delivery": delivery}


@router.post("/conversations/{conversation_id}/takeover")
def takeover_conversation(
    conversation_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    conversation = require_conversation(session, seller_id, conversation_id)
    conversation.is_human_takeover = True
    session.commit()
    return {"id": conversation.id, "is_human_takeover": True}


@router.post("/conversations/{conversation_id}/release")
def release_conversation(
    conversation_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    conversation = require_conversation(session, seller_id, conversation_id)
    conversation.is_human_takeover = False
    session.commit()
    return {"id": conversation.id, "is_human_takeover": False}
