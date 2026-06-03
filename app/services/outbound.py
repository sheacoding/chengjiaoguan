"""
/* ========================================================================== */
/* GEB L3: 出站消息服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models、utcnow、channel_delivery、seller_settings、notifications、Decimal 与敏感/金额解析规则
 * [OUTPUT]: 对外提供 send_message
 * [POS]: services 的出站护栏核心，在安全时经渠道投递边界发消息，在风险时创建 approval
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from decimal import Decimal, InvalidOperation
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow
from app.services.channel_delivery import deliver_message
from app.services.notifications import notify_approval_requested
from app.services.seller_settings import apply_ai_disclosure


SENSITIVE_KEYWORDS = {
    "bank account",
    "contract",
    "delivery guarantee",
    "exclusive",
    "guarantee",
    "legal",
    "net 30",
    "payment terms",
    "penalty",
    "refund",
}
AMOUNT_PATTERN = re.compile(
    r"(?:(?:usd|us\$|\$)\s*)(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:usd|us\$)",
    re.IGNORECASE,
)


def send_message(
    session: Session,
    seller_id: int,
    *,
    conversation_id: int,
    content: str,
    language: str | None = None,
) -> dict:
    if not content.strip():
        raise ValueError("content is required")
    conversation = _require_conversation(session, seller_id, conversation_id)
    inquiry = session.get(models.Inquiry, conversation.inquiry_id)
    if inquiry is None or inquiry.seller_id != seller_id:
        raise LookupError("Inquiry not found")

    reasons = _guardrail_reasons(session, seller_id, conversation, content)
    if reasons:
        approval = _create_message_approval(session, seller_id, conversation, inquiry, content, language, reasons)
        return {
            "status": "pending_approval",
            "approval_id": approval.id,
            "reason": approval.reason,
            "reasons": reasons,
        }

    disclosed_content = apply_ai_disclosure(session, seller_id, content)
    message = models.Message(
        conversation_id=conversation.id,
        sender_role="ai",
        content=disclosed_content,
        language=language or conversation.language,
        sent_at=utcnow(),
    )
    session.add(message)
    session.flush()
    delivery = deliver_message(session, seller_id, conversation, message)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="ai",
            action_type="message_sent",
            target_type="conversation",
            target_id=conversation.id,
            is_auto=True,
            snapshot={"content": disclosed_content, "delivery": delivery},
        )
    )
    session.flush()
    return {
        "status": "sent",
        "message_id": message.id,
        "conversation_id": conversation.id,
        "content": message.content,
        "language": message.language,
        "delivery": delivery,
    }


def _require_conversation(session: Session, seller_id: int, conversation_id: int) -> models.Conversation:
    conversation = session.get(models.Conversation, conversation_id)
    if conversation is None or conversation.seller_id != seller_id:
        raise LookupError("Conversation not found")
    return conversation


def _guardrail_reasons(
    session: Session,
    seller_id: int,
    conversation: models.Conversation,
    content: str,
) -> list[str]:
    reasons: list[str] = []
    lowered = content.lower()
    if conversation.is_human_takeover:
        reasons.append("human_takeover_active")
    if any(keyword in lowered for keyword in SENSITIVE_KEYWORDS):
        reasons.append("sensitive_commitment")
    if _contains_below_floor_price(session, seller_id, content):
        reasons.append("below_floor_price")
    if _contains_large_amount(session, seller_id, content):
        reasons.append("large_order_amount")
    return reasons


def _contains_below_floor_price(session: Session, seller_id: int, content: str) -> bool:
    floor_prices = [
        Decimal(str(value))
        for value in session.scalars(
            select(models.PricingRule.floor_price)
            .where(models.PricingRule.seller_id == seller_id)
            .where(models.PricingRule.deleted_at.is_(None))
        ).all()
        if value is not None
    ]
    if not floor_prices:
        return False
    min_floor = min(floor_prices)
    return any(amount < min_floor for amount in _extract_amounts(content))


def _contains_large_amount(session: Session, seller_id: int, content: str) -> bool:
    seller = session.get(models.Seller, seller_id)
    threshold = (
        Decimal(str((seller.settings or {}).get("large_order_approval_threshold", "10000")))
        if seller
        else Decimal("10000")
    )
    return any(amount >= threshold for amount in _extract_amounts(content))


def _extract_amounts(content: str) -> list[Decimal]:
    amounts = []
    for match in AMOUNT_PATTERN.finditer(content):
        value = match.group(1) or match.group(2)
        try:
            amounts.append(Decimal(value))
        except InvalidOperation:
            continue
    return amounts


def _create_message_approval(
    session: Session,
    seller_id: int,
    conversation: models.Conversation,
    inquiry: models.Inquiry,
    content: str,
    language: str | None,
    reasons: list[str],
) -> models.Approval:
    reason = "below_floor_price" if "below_floor_price" in reasons else reasons[0]
    conversation.is_human_takeover = True
    inquiry.status = "pending_approval"
    approval = models.Approval(
        seller_id=seller_id,
        conversation_id=conversation.id,
        inquiry_id=inquiry.id,
        type="message_send",
        reason=reason,
        summary=f"AI outbound message paused: {', '.join(reasons)}",
        suggestion=content,
        payload={"content": content, "language": language or conversation.language},
        status="pending",
        executed=False,
    )
    session.add(approval)
    session.flush()
    notify_approval_requested(session, approval)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="ai",
            action_type="approval_requested",
            target_type="approval",
            target_id=approval.id,
            is_auto=True,
            snapshot={"type": "message_send", "reasons": reasons, "content": content},
        )
    )
    session.flush()
    return approval
