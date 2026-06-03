"""
/* ========================================================================== */
/* GEB L3: 数据隐私擦除                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session/select/or_、utcnow 与 app.models 的客户关联实体
 * [OUTPUT]: 对外提供 erase_customer_data，按租户擦除 customer 及其询盘、会话、消息、报价、跟进、投递、审批、通知与审计快照
 * [POS]: services 的 GDPR/MVP 隐私边界，让客户删除成为可审计、不可继续触发出站动作的确定性服务
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow


ERASED_TEXT = "[erased]"
ERASED_MARK = {"erased": True}


def erase_customer_data(session: Session, seller_id: int, customer_id: int) -> dict[str, Any]:
    customer = _require_customer(session, seller_id, customer_id)
    stamp = utcnow()
    graph = _load_customer_graph(session, seller_id, customer.id)
    audit_logs = _scrub_audit_logs(session, seller_id, customer.id, graph, stamp)

    _erase_customer(customer, stamp)
    _erase_inquiries(graph["inquiries"], stamp)
    _erase_conversations(graph["conversations"])
    _erase_messages(graph["messages"])
    _erase_quotations(graph["quotations"], stamp)
    _erase_followups(graph["followups"])
    _erase_delivery_attempts(graph["delivery_attempts"])
    _erase_approvals(graph["approvals"])
    _erase_notifications(graph["notifications"])

    counts = _counts(graph) | {"audit_logs": audit_logs}
    session.add(_erasure_audit(seller_id, customer.id, counts, stamp))
    session.flush()
    return {"id": customer.id, "status": customer.status, "erased": counts}


def _require_customer(session: Session, seller_id: int, customer_id: int) -> models.Customer:
    customer = session.get(models.Customer, customer_id)
    if customer is None or customer.seller_id != seller_id or customer.deleted_at is not None:
        raise LookupError("Customer not found")
    return customer


def _load_customer_graph(session: Session, seller_id: int, customer_id: int) -> dict[str, list[Any]]:
    inquiries = _by_customer(session, models.Inquiry, seller_id, customer_id)
    conversations = _by_customer(session, models.Conversation, seller_id, customer_id)
    quotations = _by_customer(session, models.Quotation, seller_id, customer_id)
    followups = _followups(session, seller_id, [inquiry.id for inquiry in inquiries])
    messages = _messages(session, [conversation.id for conversation in conversations])
    attempts = _delivery_attempts(session, seller_id, [message.id for message in messages])
    approvals = _approvals(
        session,
        seller_id,
        [inquiry.id for inquiry in inquiries],
        [conversation.id for conversation in conversations],
    )
    notifications = _notifications(session, seller_id, [approval.id for approval in approvals])
    return {
        "inquiries": inquiries,
        "conversations": conversations,
        "messages": messages,
        "delivery_attempts": attempts,
        "quotations": quotations,
        "followups": followups,
        "approvals": approvals,
        "notifications": notifications,
    }


def _by_customer(session: Session, model, seller_id: int, customer_id: int) -> list[Any]:
    return session.scalars(
        select(model)
        .where(model.seller_id == seller_id)
        .where(model.customer_id == customer_id)
        .order_by(model.id.asc())
    ).all()


def _followups(session: Session, seller_id: int, inquiry_ids: list[int]) -> list[models.FollowupTask]:
    if not inquiry_ids:
        return []
    return session.scalars(
        select(models.FollowupTask)
        .where(models.FollowupTask.seller_id == seller_id)
        .where(models.FollowupTask.inquiry_id.in_(inquiry_ids))
        .order_by(models.FollowupTask.id.asc())
    ).all()


def _messages(session: Session, conversation_ids: list[int]) -> list[models.Message]:
    if not conversation_ids:
        return []
    return session.scalars(
        select(models.Message)
        .where(models.Message.conversation_id.in_(conversation_ids))
        .order_by(models.Message.id.asc())
    ).all()


def _delivery_attempts(session: Session, seller_id: int, message_ids: list[int]) -> list[models.DeliveryAttempt]:
    if not message_ids:
        return []
    return session.scalars(
        select(models.DeliveryAttempt)
        .where(models.DeliveryAttempt.seller_id == seller_id)
        .where(models.DeliveryAttempt.message_id.in_(message_ids))
        .order_by(models.DeliveryAttempt.id.asc())
    ).all()


def _approvals(
    session: Session,
    seller_id: int,
    inquiry_ids: list[int],
    conversation_ids: list[int],
) -> list[models.Approval]:
    filters = []
    if inquiry_ids:
        filters.append(models.Approval.inquiry_id.in_(inquiry_ids))
    if conversation_ids:
        filters.append(models.Approval.conversation_id.in_(conversation_ids))
    if not filters:
        return []
    return session.scalars(
        select(models.Approval)
        .where(models.Approval.seller_id == seller_id)
        .where(or_(*filters))
        .order_by(models.Approval.id.asc())
    ).all()


def _notifications(session: Session, seller_id: int, approval_ids: list[int]) -> list[models.Notification]:
    if not approval_ids:
        return []
    return session.scalars(
        select(models.Notification)
        .where(models.Notification.seller_id == seller_id)
        .where(models.Notification.target_type == "approval")
        .where(models.Notification.target_id.in_(approval_ids))
        .order_by(models.Notification.id.asc())
    ).all()


def _scrub_audit_logs(session: Session, seller_id: int, customer_id: int, graph: dict[str, list[Any]], stamp) -> int:
    filters = _audit_filters(customer_id, graph)
    if not filters:
        return 0
    logs = session.scalars(
        select(models.AuditLog)
        .where(models.AuditLog.seller_id == seller_id)
        .where(or_(*filters))
        .order_by(models.AuditLog.id.asc())
    ).all()
    for log in logs:
        log.snapshot = {"erased": True, "erased_at": stamp.isoformat()}
    return len(logs)


def _audit_filters(customer_id: int, graph: dict[str, list[Any]]) -> list[Any]:
    mapping = {
        "customer": [customer_id],
        "inquiry": graph["inquiries"],
        "conversation": graph["conversations"],
        "quotation": graph["quotations"],
        "followup_task": graph["followups"],
        "approval": graph["approvals"],
    }
    return [
        (models.AuditLog.target_type == target_type) & (models.AuditLog.target_id.in_(_ids(records)))
        for target_type, records in mapping.items()
        if records
    ]


def _erase_customer(customer: models.Customer, stamp) -> None:
    customer.deleted_at = stamp
    customer.status = "erased"
    customer.name = None
    customer.company = None
    customer.country = None
    customer.email = None
    customer.phone = None
    customer.channels = {}
    customer.grade = None
    customer.enrichment = {}
    customer.preferences = {}


def _erase_inquiries(inquiries: Iterable[models.Inquiry], stamp) -> None:
    for inquiry in inquiries:
        inquiry.deleted_at = stamp
        inquiry.raw_content = ERASED_TEXT
        inquiry.parsed = {}
        inquiry.grade = None
        inquiry.score = None
        inquiry.status = "erased"
        inquiry.language = None


def _erase_conversations(conversations: Iterable[models.Conversation]) -> None:
    for conversation in conversations:
        conversation.status = "erased"
        conversation.is_human_takeover = False
        conversation.language = None


def _erase_messages(messages: Iterable[models.Message]) -> None:
    for message in messages:
        message.content = ERASED_TEXT
        message.attachments = []
        message.language = None
        message.channel_message_id = f"erased:{message.id}" if message.id is not None else None


def _erase_quotations(quotations: Iterable[models.Quotation], stamp) -> None:
    for quotation in quotations:
        quotation.deleted_at = stamp
        quotation.status = "erased"
        quotation.terms = dict(ERASED_MARK)


def _erase_followups(tasks: Iterable[models.FollowupTask]) -> None:
    for task in tasks:
        task.status = "stopped"
        task.stop_reason = "customer_erased"
        task.schedule = {}
        task.next_run_at = None


def _erase_delivery_attempts(attempts: Iterable[models.DeliveryAttempt]) -> None:
    for attempt in attempts:
        attempt.status = "erased"
        attempt.external_id = f"erased:{attempt.id}"
        attempt.provider_message_id = None
        attempt.next_retry_at = None
        attempt.error = None
        attempt.payload = dict(ERASED_MARK)
        attempt.response = dict(ERASED_MARK)


def _erase_approvals(approvals: Iterable[models.Approval]) -> None:
    for approval in approvals:
        approval.reason = "customer_erased"
        approval.summary = "Customer data erased."
        approval.suggestion = None
        approval.payload = dict(ERASED_MARK)
        if approval.status == "pending":
            approval.status = "cancelled"


def _erase_notifications(notifications: Iterable[models.Notification]) -> None:
    for notification in notifications:
        notification.title = "Customer data erased."
        notification.body = ERASED_TEXT
        notification.context = dict(ERASED_MARK)
        notification.status = "archived"


def _erasure_audit(seller_id: int, customer_id: int, counts: dict[str, int], stamp) -> models.AuditLog:
    return models.AuditLog(
        seller_id=seller_id,
        actor="human",
        action_type="customer_erased",
        target_type="customer",
        target_id=customer_id,
        is_auto=False,
        snapshot={"erased_at": stamp.isoformat(), "counts": counts},
    )


def _counts(graph: dict[str, list[Any]]) -> dict[str, int]:
    return {"customer": 1} | {name: len(records) for name, records in graph.items()}


def _ids(records: Iterable[Any]) -> list[int]:
    return [record if isinstance(record, int) else record.id for record in records]
