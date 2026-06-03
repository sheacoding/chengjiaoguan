"""
/* ========================================================================== */
/* GEB L3: 跟进任务服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models、utcnow 与 outbound.send_message
 * [OUTPUT]: 对外提供 create_followup 与 run_due_followups
 * [POS]: services 的未回复询盘推进器，调度 follow-up 并在护栏触发时暂停
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow
from app.services.outbound import send_message


DEFAULT_FOLLOWUP_MESSAGE = (
    "Just following up on your inquiry. Do you need any clarification on the quote or specifications?"
)


def create_followup(
    session: Session,
    seller_id: int,
    *,
    inquiry_id: int,
    conversation_id: int | None = None,
    delay_hours: int = 24,
    message: str | None = None,
    max_attempts: int = 3,
) -> dict:
    inquiry = session.get(models.Inquiry, inquiry_id)
    if inquiry is None or inquiry.seller_id != seller_id:
        raise LookupError("Inquiry not found")
    conversation = _resolve_conversation(session, seller_id, inquiry_id, conversation_id)
    delay_hours = max(delay_hours, 1)
    max_attempts = max(max_attempts, 1)
    task = models.FollowupTask(
        seller_id=seller_id,
        inquiry_id=inquiry.id,
        conversation_id=conversation.id,
        schedule={
            "delay_hours": delay_hours,
            "attempt": 0,
            "max_attempts": max_attempts,
            "message": message or DEFAULT_FOLLOWUP_MESSAGE,
        },
        next_run_at=utcnow() + timedelta(hours=delay_hours),
        status="active",
    )
    session.add(task)
    session.flush()
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="ai",
            action_type="followup_created",
            target_type="followup_task",
            target_id=task.id,
            is_auto=True,
            snapshot={"inquiry_id": inquiry.id, "conversation_id": conversation.id},
        )
    )
    return _task_result(task)


def run_due_followups(
    session: Session,
    *,
    seller_id: int | None = None,
    now: datetime | None = None,
    limit: int = 50,
) -> list[dict]:
    now = now or utcnow()
    statement = (
        select(models.FollowupTask)
        .where(models.FollowupTask.status == "active")
        .where(models.FollowupTask.next_run_at <= now)
        .order_by(models.FollowupTask.next_run_at.asc(), models.FollowupTask.id.asc())
        .limit(min(max(limit, 1), 200))
    )
    if seller_id is not None:
        statement = statement.where(models.FollowupTask.seller_id == seller_id)

    results = []
    for task in session.scalars(statement).all():
        results.append(_run_task(session, task, now))
    session.flush()
    return results


def _run_task(session: Session, task: models.FollowupTask, now: datetime) -> dict:
    conversation = session.get(models.Conversation, task.conversation_id)
    if conversation is None or conversation.status != "open":
        task.status = "stopped"
        task.stop_reason = "conversation_closed"
        return _task_result(task)
    if conversation.is_human_takeover:
        task.status = "paused"
        task.stop_reason = "human_takeover_active"
        return _task_result(task)
    if _customer_replied_after(session, task.conversation_id, _last_activity_at(task)):
        task.status = "stopped"
        task.stop_reason = "customer_replied"
        return _task_result(task)

    schedule = dict(task.schedule or {})
    result = send_message(
        session,
        task.seller_id,
        conversation_id=task.conversation_id,
        content=schedule.get("message") or DEFAULT_FOLLOWUP_MESSAGE,
        language=conversation.language,
    )
    if result["status"] == "pending_approval":
        task.status = "paused"
        task.stop_reason = result["reason"]
        return _task_result(task) | {"send_result": result}

    attempt = int(schedule.get("attempt", 0)) + 1
    max_attempts = int(schedule.get("max_attempts", 3))
    schedule["attempt"] = attempt
    schedule["last_sent_at"] = now.isoformat()
    task.schedule = schedule
    if attempt >= max_attempts:
        task.status = "completed"
        task.stop_reason = "max_attempts_reached"
        task.next_run_at = None
    else:
        task.next_run_at = now + timedelta(hours=int(schedule.get("delay_hours", 24)))
    return _task_result(task) | {"send_result": result}


def _resolve_conversation(
    session: Session,
    seller_id: int,
    inquiry_id: int,
    conversation_id: int | None,
) -> models.Conversation:
    if conversation_id is not None:
        conversation = session.get(models.Conversation, conversation_id)
        if conversation is None or conversation.seller_id != seller_id or conversation.inquiry_id != inquiry_id:
            raise LookupError("Conversation not found")
        return conversation
    conversation = session.scalar(
        select(models.Conversation).where(
            models.Conversation.seller_id == seller_id,
            models.Conversation.inquiry_id == inquiry_id,
        )
    )
    if conversation is None:
        raise LookupError("Conversation not found")
    return conversation


def _customer_replied_after(session: Session, conversation_id: int, since: datetime) -> bool:
    return (
        session.scalar(
            select(models.Message.id)
            .where(models.Message.conversation_id == conversation_id)
            .where(models.Message.sender_role == "customer")
            .where(models.Message.sent_at >= since)
            .limit(1)
        )
        is not None
    )


def _last_activity_at(task: models.FollowupTask) -> datetime:
    schedule = task.schedule or {}
    if schedule.get("last_sent_at"):
        return datetime.fromisoformat(schedule["last_sent_at"])
    return task.created_at


def _task_result(task: models.FollowupTask) -> dict:
    return {
        "followup_id": task.id,
        "inquiry_id": task.inquiry_id,
        "conversation_id": task.conversation_id,
        "status": task.status,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
        "stop_reason": task.stop_reason,
        "schedule": task.schedule or {},
    }
