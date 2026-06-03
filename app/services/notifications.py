"""
/* ========================================================================== */
/* GEB L3: 通知服务                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session/select/func、utcnow 与 app.models 的 Notification/Approval
 * [OUTPUT]: 对外提供 create_notification、notify_approval_requested、list_notifications、update_notification_status、resolve_approval_notifications
 * [POS]: services 的通知状态机，把需要人工处理的业务事件固化为租户隔离的未读/已读/归档消息
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow
from app.services.catalog_domain.common import page as clamp_page


NotificationStatus = Literal["unread", "read", "archived"]


def create_notification(
    session: Session,
    seller_id: int,
    *,
    type: str,
    title: str,
    body: str | None = None,
    severity: str = "info",
    target_type: str | None = None,
    target_id: int | None = None,
    context: dict[str, Any] | None = None,
) -> models.Notification:
    notification = models.Notification(
        seller_id=seller_id,
        type=type,
        severity=severity,
        title=title,
        body=body,
        target_type=target_type,
        target_id=target_id,
        context=context or {},
        status="unread",
    )
    session.add(notification)
    session.flush()
    return notification


def notify_approval_requested(session: Session, approval: models.Approval) -> models.Notification:
    return create_notification(
        session,
        approval.seller_id,
        type="approval_requested",
        severity=_approval_severity(approval),
        title=_approval_title(approval),
        body=approval.summary,
        target_type="approval",
        target_id=approval.id,
        context={
            "approval_type": approval.type,
            "reason": approval.reason,
            "conversation_id": approval.conversation_id,
            "inquiry_id": approval.inquiry_id,
        },
    )


def list_notifications(
    session: Session,
    seller_id: int,
    *,
    status: NotificationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[models.Notification], int, int, int]:
    page, page_size = clamp_page(page, page_size)
    statement = select(models.Notification).where(models.Notification.seller_id == seller_id)
    count = select(func.count()).select_from(models.Notification).where(models.Notification.seller_id == seller_id)
    if status:
        statement = statement.where(models.Notification.status == status)
        count = count.where(models.Notification.status == status)
    total = session.scalar(count) or 0
    notifications = session.scalars(
        statement.order_by(models.Notification.created_at.desc(), models.Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return notifications, total, page, page_size


def update_notification_status(
    session: Session,
    seller_id: int,
    notification_id: int,
    status: NotificationStatus,
) -> models.Notification:
    notification = session.get(models.Notification, notification_id)
    if notification is None or notification.seller_id != seller_id:
        raise LookupError("Notification not found")
    _set_status(notification, status)
    session.flush()
    return notification


def resolve_approval_notifications(session: Session, seller_id: int, approval_id: int) -> int:
    notifications = session.scalars(
        select(models.Notification).where(
            models.Notification.seller_id == seller_id,
            models.Notification.target_type == "approval",
            models.Notification.target_id == approval_id,
            models.Notification.status == "unread",
        )
    ).all()
    for notification in notifications:
        _set_status(notification, "read")
    session.flush()
    return len(notifications)


def _set_status(notification: models.Notification, status: NotificationStatus) -> None:
    if status not in {"unread", "read", "archived"}:
        raise ValueError("Notification status must be unread, read, or archived")
    notification.status = status
    if status == "unread":
        notification.read_at = None
    elif notification.read_at is None:
        notification.read_at = utcnow()


def _approval_title(approval: models.Approval) -> str:
    labels = {
        "handoff": "Human takeover requested",
        "message_send": "Outbound message needs approval",
        "quotation_send": "Quotation needs approval",
        "pi_generate": "PI generation needs approval",
    }
    return labels.get(approval.type, "Approval requested")


def _approval_severity(approval: models.Approval) -> str:
    if approval.reason in {"below_floor_price", "large_order_amount"}:
        return "warning"
    if approval.reason in {"sensitive_commitment", "pi_requires_approval"}:
        return "warning"
    return "info"
