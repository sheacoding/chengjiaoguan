"""
/* ========================================================================== */
/* GEB L3: 运维告警聚合                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 datetime、SQLAlchemy Session/select、app.models 与 pricing_rule.exchange_rate_cache
 * [OUTPUT]: 对外提供 list_ops_alerts，把失败投递、待审批、到期/暂停跟进、汇率缓存风险折叠成只读告警列表
 * [POS]: services 的运行监控薄层，只读取既有状态并生成可观测信号，不拥有业务状态机
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow


def list_ops_alerts(
    session: Session,
    seller_id: int,
    *,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utcnow()
    alerts = (
        _failed_delivery_alerts(session, seller_id)
        + _pending_approval_alerts(session, seller_id)
        + _followup_alerts(session, seller_id, now)
        + _exchange_cache_alerts(session, seller_id, now.date())
    )
    alerts = sorted(alerts, key=lambda item: (_severity_rank(item["severity"]), item["created_at"]), reverse=True)
    alerts = alerts[: min(max(limit, 1), 200)]
    counts = _counts(alerts)
    return {
        "status": _status(counts),
        "items": alerts,
        "total": len(alerts),
        "counts": counts,
    }


def _failed_delivery_alerts(session: Session, seller_id: int) -> list[dict[str, Any]]:
    attempts = session.scalars(
        select(models.DeliveryAttempt)
        .where(models.DeliveryAttempt.seller_id == seller_id)
        .where(models.DeliveryAttempt.status == "failed")
        .order_by(models.DeliveryAttempt.updated_at.desc(), models.DeliveryAttempt.id.desc())
        .limit(50)
    ).all()
    return [
        _alert(
            "critical",
            "failed_delivery_attempt",
            f"{attempt.channel} delivery failed",
            "delivery_attempt",
            attempt.id,
            attempt.updated_at,
            {
                "message_id": attempt.message_id,
                "channel": attempt.channel,
                "error": attempt.error,
                "next_retry_at": attempt.next_retry_at.isoformat() if attempt.next_retry_at else None,
            },
        )
        for attempt in attempts
    ]


def _pending_approval_alerts(session: Session, seller_id: int) -> list[dict[str, Any]]:
    approvals = session.scalars(
        select(models.Approval)
        .where(models.Approval.seller_id == seller_id)
        .where(models.Approval.status == "pending")
        .order_by(models.Approval.created_at.asc(), models.Approval.id.asc())
        .limit(50)
    ).all()
    return [
        _alert(
            "warning",
            "pending_approval",
            f"{approval.type} approval is waiting for human review",
            "approval",
            approval.id,
            approval.created_at,
            {
                "conversation_id": approval.conversation_id,
                "inquiry_id": approval.inquiry_id,
                "reason": approval.reason,
            },
        )
        for approval in approvals
    ]


def _followup_alerts(session: Session, seller_id: int, now: datetime) -> list[dict[str, Any]]:
    due = session.scalars(
        select(models.FollowupTask)
        .where(models.FollowupTask.seller_id == seller_id)
        .where(models.FollowupTask.status == "active")
        .where(models.FollowupTask.next_run_at <= now)
        .order_by(models.FollowupTask.next_run_at.asc(), models.FollowupTask.id.asc())
        .limit(50)
    ).all()
    paused = session.scalars(
        select(models.FollowupTask)
        .where(models.FollowupTask.seller_id == seller_id)
        .where(models.FollowupTask.status == "paused")
        .order_by(models.FollowupTask.updated_at.desc(), models.FollowupTask.id.desc())
        .limit(50)
    ).all()
    return [_due_followup_alert(task) for task in due] + [_paused_followup_alert(task) for task in paused]


def _exchange_cache_alerts(session: Session, seller_id: int, today: date) -> list[dict[str, Any]]:
    rules = session.scalars(
        select(models.PricingRule)
        .where(models.PricingRule.seller_id == seller_id)
        .where(models.PricingRule.deleted_at.is_(None))
        .order_by(models.PricingRule.id.asc())
        .limit(100)
    ).all()
    alerts = []
    for rule in rules:
        cache = (rule.logistics_template or {}).get("exchange_rate_cache")
        if not isinstance(cache, dict):
            continue
        status = _exchange_cache_status(cache, today)
        if status is None:
            continue
        severity, message = status
        alerts.append(
            _alert(
                severity,
                "exchange_rate_cache_attention",
                message,
                "pricing_rule",
                rule.id,
                rule.updated_at,
                {"exchange_source": rule.exchange_source, "currency": rule.currency},
            )
        )
    return alerts


def _due_followup_alert(task: models.FollowupTask) -> dict[str, Any]:
    return _alert(
        "warning",
        "due_followup",
        "Follow-up task is due and waiting for the worker",
        "followup_task",
        task.id,
        task.next_run_at or task.updated_at,
        {
            "inquiry_id": task.inquiry_id,
            "conversation_id": task.conversation_id,
            "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
        },
    )


def _paused_followup_alert(task: models.FollowupTask) -> dict[str, Any]:
    return _alert(
        "warning",
        "paused_followup",
        "Follow-up task is paused",
        "followup_task",
        task.id,
        task.updated_at,
        {
            "inquiry_id": task.inquiry_id,
            "conversation_id": task.conversation_id,
            "stop_reason": task.stop_reason,
        },
    )


def _exchange_cache_status(cache: dict[str, Any], today: date) -> tuple[str, str] | None:
    if cache.get("confirmed") is not True:
        return "warning", "Exchange rate cache is not manually confirmed"
    expires_at = _expiry_date(cache.get("expires_at"))
    if expires_at is None:
        return "critical", "Exchange rate cache is missing expires_at"
    if expires_at < today:
        return "warning", "Exchange rate cache has expired"
    return None


def _alert(
    severity: str,
    code: str,
    message: str,
    target_type: str,
    target_id: int,
    created_at,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "target_type": target_type,
        "target_id": target_id,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        "details": details,
    }


def _expiry_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _counts(alerts: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "critical": sum(1 for alert in alerts if alert["severity"] == "critical"),
        "warning": sum(1 for alert in alerts if alert["severity"] == "warning"),
    }


def _status(counts: dict[str, int]) -> str:
    if counts["critical"]:
        return "critical"
    if counts["warning"]:
        return "attention"
    return "ok"


def _severity_rank(severity: str) -> int:
    return {"critical": 2, "warning": 1}.get(severity, 0)
