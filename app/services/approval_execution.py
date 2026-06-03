"""
/* ========================================================================== */
/* GEB L3: 审批执行器                                                         */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models、utcnow、channel_delivery、seller_settings 与 quotations 服务
 * [OUTPUT]: 对外提供 execute_approval，执行 message_send、quotation_send、pi_generate、handoff 审批动作
 * [POS]: services 的审批动作执行层，被 approvals.py 调用，隔离队列状态管理与副作用执行
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from sqlalchemy.orm import Session

from app import models
from app.database import utcnow
from app.services.channel_delivery import deliver_message
from app.services.quotations import generate_pi_document, send_quotation
from app.services.seller_settings import apply_ai_disclosure


def execute_approval(session: Session, approval: models.Approval) -> dict:
    if approval.type == "message_send":
        return _execute_message_send(session, approval)
    if approval.type in {"quotation_send", "quote_send"}:
        quotation_id = int((approval.payload or {})["quotation_id"])
        return send_quotation(session, approval.seller_id, quotation_id, approved=True)
    if approval.type == "pi_generate":
        quotation_id = int((approval.payload or {})["quotation_id"])
        return generate_pi_document(session, approval.seller_id, quotation_id)
    if approval.type == "handoff":
        return {"status": "handoff_acknowledged", "approval_id": approval.id}
    raise ValueError(f"Unsupported approval type: {approval.type}")


def _execute_message_send(session: Session, approval: models.Approval) -> dict:
    conversation = session.get(models.Conversation, approval.conversation_id)
    if conversation is None or conversation.seller_id != approval.seller_id:
        raise LookupError("Conversation not found")
    payload = approval.payload or {}
    content = payload.get("content") or approval.suggestion
    if not content:
        raise ValueError("Approval payload content is required")
    disclosed_content = apply_ai_disclosure(session, approval.seller_id, content)
    message = models.Message(
        conversation_id=conversation.id,
        sender_role="ai",
        content=disclosed_content,
        language=payload.get("language") or conversation.language,
        sent_at=utcnow(),
    )
    conversation.is_human_takeover = False
    inquiry = session.get(models.Inquiry, approval.inquiry_id)
    if inquiry is not None:
        inquiry.status = "responded"
    session.add(message)
    session.flush()
    delivery = deliver_message(session, approval.seller_id, conversation, message)
    return {"status": "sent", "message_id": message.id, "conversation_id": conversation.id, "delivery": delivery}
