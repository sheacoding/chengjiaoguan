"""
/* ========================================================================== */
/* GEB L3: 审批服务                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models、approval_execution.execute_approval 与 notifications 服务
 * [OUTPUT]: 对外提供 list_approvals、request_handoff、patch_approval、approve_approval、reject_approval
 * [POS]: services 的人工审批队列状态核心，把具体副作用交给 approval_execution
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.approval_execution import execute_approval
from app.services.notifications import notify_approval_requested, resolve_approval_notifications


def list_approvals(session: Session, seller_id: int, *, status: str | None = "pending") -> list[models.Approval]:
    statement = select(models.Approval).where(models.Approval.seller_id == seller_id)
    if status:
        statement = statement.where(models.Approval.status == status)
    return session.scalars(statement.order_by(models.Approval.id.desc())).all()


def request_handoff(
    session: Session,
    seller_id: int,
    *,
    conversation_id: int,
    reason: str,
    summary: str,
    suggestion: str | None = None,
    payload: dict[str, Any] | None = None,
) -> models.Approval:
    conversation = session.get(models.Conversation, conversation_id)
    if conversation is None or conversation.seller_id != seller_id:
        raise LookupError("Conversation not found")
    inquiry = session.get(models.Inquiry, conversation.inquiry_id)
    if inquiry is None or inquiry.seller_id != seller_id:
        raise LookupError("Inquiry not found")

    conversation.is_human_takeover = True
    inquiry.status = "pending_approval"
    approval = models.Approval(
        seller_id=seller_id,
        conversation_id=conversation.id,
        inquiry_id=inquiry.id,
        type="handoff",
        reason=reason,
        summary=summary,
        suggestion=suggestion,
        payload=payload or {},
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
            action_type="handoff_requested",
            target_type="approval",
            target_id=approval.id,
            is_auto=True,
            snapshot={"reason": reason, "summary": summary},
        )
    )
    session.flush()
    return approval


def patch_approval(
    session: Session,
    seller_id: int,
    approval_id: int,
    *,
    payload: dict[str, Any] | None = None,
    suggestion: str | None = None,
    summary: str | None = None,
) -> models.Approval:
    approval = _require_pending_approval(session, seller_id, approval_id)
    if payload is not None:
        merged_payload = dict(approval.payload or {})
        merged_payload.update(payload)
        approval.payload = merged_payload
    if suggestion is not None:
        approval.suggestion = suggestion
    if summary is not None:
        approval.summary = summary
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="approval_patched",
            target_type="approval",
            target_id=approval.id,
            is_auto=False,
            snapshot={"payload": approval.payload, "suggestion": approval.suggestion},
        )
    )
    session.flush()
    return approval


def approve_approval(session: Session, seller_id: int, approval_id: int) -> dict:
    approval = _require_pending_approval(session, seller_id, approval_id)
    result = execute_approval(session, approval)
    approval.status = "approved"
    approval.executed = True
    resolve_approval_notifications(session, seller_id, approval.id)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="approval_approved",
            target_type="approval",
            target_id=approval.id,
            is_auto=False,
            snapshot={"result": result},
        )
    )
    session.flush()
    return {"id": approval.id, "status": approval.status, "executed": approval.executed, "result": result}


def reject_approval(session: Session, seller_id: int, approval_id: int, *, reason: str | None = None) -> dict:
    approval = _require_pending_approval(session, seller_id, approval_id)
    payload = dict(approval.payload or {})
    if reason:
        payload["reject_reason"] = reason
    approval.payload = payload
    approval.status = "rejected"
    approval.executed = False
    resolve_approval_notifications(session, seller_id, approval.id)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="approval_rejected",
            target_type="approval",
            target_id=approval.id,
            is_auto=False,
            snapshot={"reason": reason},
        )
    )
    session.flush()
    return {"id": approval.id, "status": approval.status, "executed": approval.executed}


def _require_pending_approval(session: Session, seller_id: int, approval_id: int) -> models.Approval:
    approval = session.get(models.Approval, approval_id)
    if approval is None or approval.seller_id != seller_id:
        raise LookupError("Approval not found")
    if approval.status != "pending":
        raise ValueError("Approval is not pending")
    return approval
