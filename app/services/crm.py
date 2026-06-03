"""
/* ========================================================================== */
/* GEB L3: CRM 查询服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session/select/func/or_ 与 app.models 的 Customer/Inquiry/Conversation/Quotation/FollowupTask
 * [OUTPUT]: 对外提供 list_customers、get_customer、get_customer_profile、update_customer_profile、get_customer_activity
 * [POS]: services 的客户画像真源，被 Agent 工具层与 customers HTTP 路由消费
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.services.catalog_domain.common import blank_to_none, page as clamp_page


def list_customers(
    session: Session,
    seller_id: int,
    *,
    status: str | None = None,
    grade: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[models.Customer], int, int, int]:
    page, page_size = clamp_page(page, page_size)
    query = _customer_query(seller_id)
    count_query = select(func.count()).select_from(models.Customer).where(*_customer_scope(seller_id))
    for condition in _customer_filters(status, grade, q):
        query = query.where(condition)
        count_query = count_query.where(condition)
    total = session.scalar(count_query) or 0
    customers = session.scalars(
        query.order_by(models.Customer.updated_at.desc(), models.Customer.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return customers, total, page, page_size


def get_customer(session: Session, seller_id: int, customer_id: int) -> models.Customer:
    customer = session.get(models.Customer, customer_id)
    if customer is None or customer.seller_id != seller_id or customer.deleted_at is not None:
        raise LookupError("Customer not found")
    return customer


def get_customer_profile(
    session: Session,
    seller_id: int,
    *,
    customer_id: int | None = None,
    inquiry_id: int | None = None,
) -> dict:
    if customer_id is None and inquiry_id is not None:
        inquiry = session.get(models.Inquiry, inquiry_id)
        if inquiry is None or inquiry.seller_id != seller_id:
            raise LookupError("Inquiry not found")
        customer_id = inquiry.customer_id
    if customer_id is None:
        raise ValueError("customer_id or inquiry_id is required")

    customer = get_customer(session, seller_id, customer_id)

    return {
        "id": customer.id,
        "name": customer.name,
        "company": customer.company,
        "country": customer.country,
        "email": customer.email,
        "phone": customer.phone,
        "channels": customer.channels or {},
        "grade": customer.grade,
        "enrichment": customer.enrichment or {},
        "preferences": customer.preferences or {},
        "status": customer.status,
    }


def update_customer_profile(
    session: Session,
    seller_id: int,
    customer_id: int,
    data: dict[str, Any],
) -> models.Customer:
    customer = get_customer(session, seller_id, customer_id)
    for field in ["name", "company", "country", "email", "phone", "channels", "grade", "enrichment", "preferences", "status"]:
        if field not in data:
            continue
        value = data[field]
        if field in {"name", "company", "country", "email", "phone", "status"}:
            value = blank_to_none(value)
        if field in {"channels", "enrichment", "preferences"}:
            value = value or {}
        setattr(customer, field, value)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="customer_updated",
            target_type="customer",
            target_id=customer.id,
            is_auto=False,
            snapshot={key: data[key] for key in data if key not in {"enrichment", "preferences"}},
        )
    )
    session.flush()
    return customer


def get_customer_activity(session: Session, seller_id: int, customer_id: int) -> dict[str, list[dict[str, Any]]]:
    customer = get_customer(session, seller_id, customer_id)
    inquiries = _list_customer_inquiries(session, seller_id, customer.id)
    conversations = _list_customer_conversations(session, seller_id, customer.id)
    quotations = _list_customer_quotations(session, seller_id, customer.id)
    followups = _list_customer_followups(session, seller_id, customer.id)
    return {
        "inquiries": [_activity_inquiry(inquiry) for inquiry in inquiries],
        "conversations": [_activity_conversation(conversation) for conversation in conversations],
        "quotations": [_activity_quotation(quotation) for quotation in quotations],
        "followups": [_activity_followup(task) for task in followups],
    }


def _customer_query(seller_id: int):
    return select(models.Customer).where(*_customer_scope(seller_id))


def _customer_scope(seller_id: int):
    return models.Customer.seller_id == seller_id, models.Customer.deleted_at.is_(None)


def _customer_filters(status: str | None, grade: str | None, q: str | None):
    filters = []
    if status:
        filters.append(models.Customer.status == status)
    if grade:
        filters.append(models.Customer.grade == grade)
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                models.Customer.name.ilike(like),
                models.Customer.company.ilike(like),
                models.Customer.email.ilike(like),
                models.Customer.phone.ilike(like),
                models.Customer.country.ilike(like),
            )
        )
    return filters


def _list_customer_inquiries(session: Session, seller_id: int, customer_id: int) -> list[models.Inquiry]:
    return session.scalars(
        select(models.Inquiry)
        .where(models.Inquiry.seller_id == seller_id)
        .where(models.Inquiry.customer_id == customer_id)
        .order_by(models.Inquiry.received_at.desc().nullslast(), models.Inquiry.id.desc())
        .limit(20)
    ).all()


def _list_customer_conversations(session: Session, seller_id: int, customer_id: int) -> list[models.Conversation]:
    return session.scalars(
        select(models.Conversation)
        .where(models.Conversation.seller_id == seller_id)
        .where(models.Conversation.customer_id == customer_id)
        .order_by(models.Conversation.updated_at.desc(), models.Conversation.id.desc())
        .limit(20)
    ).all()


def _list_customer_quotations(session: Session, seller_id: int, customer_id: int) -> list[models.Quotation]:
    return session.scalars(
        select(models.Quotation)
        .where(models.Quotation.seller_id == seller_id)
        .where(models.Quotation.customer_id == customer_id)
        .order_by(models.Quotation.created_at.desc(), models.Quotation.id.desc())
        .limit(20)
    ).all()


def _list_customer_followups(session: Session, seller_id: int, customer_id: int) -> list[models.FollowupTask]:
    inquiry_ids = select(models.Inquiry.id).where(
        models.Inquiry.seller_id == seller_id,
        models.Inquiry.customer_id == customer_id,
    )
    return session.scalars(
        select(models.FollowupTask)
        .where(models.FollowupTask.seller_id == seller_id)
        .where(models.FollowupTask.inquiry_id.in_(inquiry_ids))
        .order_by(models.FollowupTask.created_at.desc(), models.FollowupTask.id.desc())
        .limit(20)
    ).all()


def _activity_inquiry(inquiry: models.Inquiry) -> dict[str, Any]:
    return {
        "id": inquiry.id,
        "source_channel": inquiry.source_channel,
        "grade": inquiry.grade,
        "score": float(inquiry.score) if inquiry.score is not None else None,
        "status": inquiry.status,
        "summary": inquiry.raw_content[:160] if inquiry.raw_content else None,
        "received_at": inquiry.received_at,
    }


def _activity_conversation(conversation: models.Conversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "inquiry_id": conversation.inquiry_id,
        "channel": conversation.channel,
        "language": conversation.language,
        "status": conversation.status,
        "is_human_takeover": conversation.is_human_takeover,
        "updated_at": conversation.updated_at,
    }


def _activity_quotation(quotation: models.Quotation) -> dict[str, Any]:
    return {
        "id": quotation.id,
        "inquiry_id": quotation.inquiry_id,
        "currency": quotation.currency,
        "total_amount": float(quotation.total_amount) if quotation.total_amount is not None else None,
        "valid_until": quotation.valid_until,
        "is_pi": quotation.is_pi,
        "status": quotation.status,
        "hits_floor": quotation.hits_floor,
    }


def _activity_followup(task: models.FollowupTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "inquiry_id": task.inquiry_id,
        "conversation_id": task.conversation_id,
        "status": task.status,
        "next_run_at": task.next_run_at,
        "stop_reason": task.stop_reason,
        "schedule": task.schedule or {},
    }
