"""
/* ========================================================================== */
/* GEB L3: 报价记录服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models、utcnow、channel_delivery、seller_settings、notifications、PI 文档产物与 Decimal 金额规整
 * [OUTPUT]: 对外提供 get_quotation、patch_quotation、generate_pi_document、request_quotation_send_approval、send_quotation
 * [POS]: services 的报价持久化、PI 文档产物与发送边界，配合 approvals 执行地板价移交
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow
from app.services.channel_delivery import deliver_message
from app.services.notifications import notify_approval_requested
from app.services.pi_documents import write_pi_document_file, write_pi_document_pdf
from app.services.seller_settings import apply_ai_disclosure


def get_quotation(session: Session, seller_id: int, quotation_id: int) -> models.Quotation:
    quotation = session.get(models.Quotation, quotation_id)
    if quotation is None or quotation.seller_id != seller_id:
        raise LookupError("Quotation not found")
    return quotation


def patch_quotation(
    session: Session,
    seller_id: int,
    quotation_id: int,
    *,
    terms: dict[str, Any] | None = None,
    valid_until=None,
    status: str | None = None,
    total_amount: Decimal | None = None,
    hits_floor: bool | None = None,
    items: list[dict[str, Any]] | None = None,
) -> models.Quotation:
    quotation = get_quotation(session, seller_id, quotation_id)
    if terms is not None:
        merged_terms = dict(quotation.terms or {})
        merged_terms.update(terms)
        quotation.terms = merged_terms
    if valid_until is not None:
        quotation.valid_until = valid_until
    if status is not None:
        quotation.status = status
    if hits_floor is not None:
        quotation.hits_floor = hits_floor
    if items is not None:
        quotation.items.clear()
        computed_total = Decimal("0")
        for item in items:
            quantity = int(item["quantity"])
            unit_price = _money(item["unit_price"])
            amount = _money(item.get("amount") or unit_price * Decimal(quantity))
            computed_total += amount
            quotation.items.append(
                models.QuotationItem(
                    product_id=int(item["product_id"]),
                    quantity=quantity,
                    unit_price=unit_price,
                    amount=amount,
                )
            )
        quotation.total_amount = _money(total_amount or computed_total)
    elif total_amount is not None:
        quotation.total_amount = _money(total_amount)

    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="quotation_patched",
            target_type="quotation",
            target_id=quotation.id,
            is_auto=False,
            snapshot={"status": quotation.status, "total_amount": str(quotation.total_amount)},
        )
    )
    session.flush()
    return quotation


def generate_pi_document(session: Session, seller_id: int, quotation_id: int) -> dict:
    quotation = get_quotation(session, seller_id, quotation_id)
    pi_number = f"PI-{quotation.id:06d}"
    terms = dict(quotation.terms or {})
    terms["pi_number"] = pi_number
    terms["pi_document"] = _render_pi_document(session, quotation, pi_number)
    terms["pi_document_file"] = write_pi_document_file(seller_id, pi_number, terms["pi_document"])
    terms["pi_pdf_file"] = write_pi_document_pdf(seller_id, pi_number, terms["pi_document"])
    quotation.terms = terms
    quotation.is_pi = True
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="pi_generated",
            target_type="quotation",
            target_id=quotation.id,
            is_auto=False,
            snapshot={"pi_number": pi_number, "pi_document_file": terms["pi_document_file"], "pi_pdf_file": terms["pi_pdf_file"]},
        )
    )
    session.flush()
    return {
        "quotation_id": quotation.id,
        "pi_number": pi_number,
        "is_pi": True,
        "status": quotation.status,
        "pi_document": terms["pi_document"],
        "pi_document_file": terms["pi_document_file"],
        "pi_pdf_file": terms["pi_pdf_file"],
    }


def request_quotation_send_approval(session: Session, seller_id: int, quotation_id: int) -> dict:
    quotation = get_quotation(session, seller_id, quotation_id)
    conversation = _quotation_conversation(session, seller_id, quotation)
    inquiry = session.get(models.Inquiry, quotation.inquiry_id)
    if inquiry is not None:
        inquiry.status = "pending_approval"
    conversation.is_human_takeover = True
    approval = models.Approval(
        seller_id=seller_id,
        conversation_id=conversation.id,
        inquiry_id=quotation.inquiry_id,
        type="quotation_send",
        reason="below_floor_price",
        summary=f"Quotation #{quotation.id} hits the floor-price guardrail and needs approval before sending.",
        suggestion=_quote_message(quotation),
        payload={"quotation_id": quotation.id},
        status="pending",
        executed=False,
    )
    session.add(approval)
    session.flush()
    notify_approval_requested(session, approval)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="approval_requested",
            target_type="approval",
            target_id=approval.id,
            is_auto=False,
            snapshot={"type": "quotation_send", "quotation_id": quotation.id},
        )
    )
    session.flush()
    return {
        "status": "pending_approval",
        "approval_id": approval.id,
        "reason": approval.reason,
        "quotation_id": quotation.id,
    }


def send_quotation(
    session: Session,
    seller_id: int,
    quotation_id: int,
    *,
    approved: bool = False,
) -> dict:
    quotation = get_quotation(session, seller_id, quotation_id)
    if quotation.hits_floor and not approved:
        raise PermissionError("below_floor_price")

    conversation = _quotation_conversation(session, seller_id, quotation)

    content = apply_ai_disclosure(session, seller_id, _quote_message(quotation))
    message = models.Message(
        conversation_id=conversation.id,
        sender_role="ai",
        content=content,
        language=conversation.language,
        sent_at=utcnow(),
    )
    quotation.status = "sent"
    session.add(message)
    session.flush()
    delivery = deliver_message(session, seller_id, conversation, message)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="ai" if approved else "human",
            action_type="quotation_sent",
            target_type="quotation",
            target_id=quotation.id,
            is_auto=approved,
            snapshot={"message_id": message.id, "approved": approved, "delivery": delivery},
        )
    )
    session.flush()
    return {"status": "sent", "quotation_id": quotation.id, "message_id": message.id, "delivery": delivery}


def _quotation_conversation(session: Session, seller_id: int, quotation: models.Quotation) -> models.Conversation:
    conversation = session.scalar(
        select(models.Conversation).where(
            models.Conversation.seller_id == seller_id,
            models.Conversation.inquiry_id == quotation.inquiry_id,
        )
    )
    if conversation is None:
        raise LookupError("Conversation not found")
    return conversation


def _quote_message(quotation: models.Quotation) -> str:
    terms = quotation.terms or {}
    if terms.get("message"):
        return str(terms["message"])
    return f"Quotation #{quotation.id}: {quotation.currency} {quotation.total_amount}"


def _render_pi_document(session: Session, quotation: models.Quotation, pi_number: str) -> str:
    customer = session.get(models.Customer, quotation.customer_id)
    seller = session.get(models.Seller, quotation.seller_id)
    lines = [
        "PROFORMA INVOICE",
        f"PI No.: {pi_number}",
        f"Seller: {seller.name if seller else quotation.seller_id}",
        f"Buyer: {_buyer_name(customer)}",
        f"Currency: {quotation.currency}",
        f"Valid Until: {quotation.valid_until.isoformat() if quotation.valid_until else 'N/A'}",
        "",
        "Items:",
    ]
    for item in quotation.items:
        product = session.get(models.Product, item.product_id)
        product_name = product.name if product else f"Product #{item.product_id}"
        lines.append(
            f"- {product_name}: {item.quantity} pcs x {quotation.currency} {item.unit_price} = {quotation.currency} {item.amount}"
        )
    lines.extend(
        [
            "",
            f"Total: {quotation.currency} {quotation.total_amount}",
            f"Terms: {(quotation.terms or {}).get('payment_terms', 'To be confirmed by seller')}",
        ]
    )
    return "\n".join(lines)


def _buyer_name(customer: models.Customer | None) -> str:
    if customer is None:
        return "Unknown buyer"
    return customer.company or customer.name or customer.email or f"Customer #{customer.id}"


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
