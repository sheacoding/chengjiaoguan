"""
/* ========================================================================== */
/* GEB L3: Dashboard 指标服务                                                 */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 datetime UTC、SQLAlchemy Session/select/func 与 app.models
 * [OUTPUT]: 对外提供 dashboard_metrics
 * [POS]: services/catalog_domain 的看板聚合边界，计算配置页、首页、运维和报价可信度指标
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import UTC, datetime, time

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models


def dashboard_metrics(session: Session, seller_id: int) -> dict[str, Any]:
    now = datetime.now(UTC)
    today_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    total = _count(session, select(models.Inquiry).where(models.Inquiry.seller_id == seller_id).subquery())
    today = _count(
        session,
        select(models.Inquiry)
        .where(models.Inquiry.seller_id == seller_id)
        .where(models.Inquiry.created_at >= today_start)
        .subquery(),
    )
    pending = _model_count(session, models.Approval, seller_id, status="pending")
    won = _model_count(session, models.Inquiry, seller_id, status="won")
    handoffs = _model_count(session, models.Approval, seller_id)
    return {
        "today_inquiries": int(today),
        "pending_handoffs": int(pending),
        "auto_handle_rate": round((total - handoffs) / total, 4) if total else 0.0,
        "conversion": round(won / total, 4) if total else 0.0,
        "total_inquiries": int(total),
        "inquiries_by_grade": _value_counts(session, models.Inquiry, seller_id, models.Inquiry.grade, values=["A", "B", "C"]),
        "inquiries_by_status": _value_counts(
            session,
            models.Inquiry,
            seller_id,
            models.Inquiry.status,
            values=["new", "qualified", "quoted", "won", "lost"],
        ),
        "conversation": {
            "open": _model_count(session, models.Conversation, seller_id, status="open"),
            "human_takeover": _bool_count(session, models.Conversation, seller_id, models.Conversation.is_human_takeover),
        },
        "approval": {
            "pending": int(pending),
            "approved": _model_count(session, models.Approval, seller_id, status="approved"),
            "rejected": _model_count(session, models.Approval, seller_id, status="rejected"),
        },
        "quotation": {
            "draft": _model_count(session, models.Quotation, seller_id, status="draft"),
            "sent": _model_count(session, models.Quotation, seller_id, status="sent"),
            "accepted": _model_count(session, models.Quotation, seller_id, status="accepted"),
            "hits_floor": _bool_count(session, models.Quotation, seller_id, models.Quotation.hits_floor),
            "total_amount": _sum_amount(session, seller_id),
        },
        "delivery": {
            "queued": _model_count(session, models.DeliveryAttempt, seller_id, status="queued"),
            "sent": _model_count(session, models.DeliveryAttempt, seller_id, status="sent"),
            "failed": _model_count(session, models.DeliveryAttempt, seller_id, status="failed"),
            "retry_due": _retry_due_count(session, seller_id, now),
        },
        "followup": {
            "active": _model_count(session, models.FollowupTask, seller_id, status="active"),
            "due": _due_followup_count(session, seller_id, now),
            "paused": _model_count(session, models.FollowupTask, seller_id, status="paused"),
        },
        "exchange_rate_cache": _exchange_cache_metrics(session, seller_id, now.date()),
    }


def _count(session: Session, subquery) -> int:
    return int(session.scalar(select(func.count()).select_from(subquery)) or 0)


def _model_count(session: Session, model, seller_id: int, *, status: str | None = None) -> int:
    statement = select(func.count()).select_from(model).where(model.seller_id == seller_id)
    if status is not None:
        statement = statement.where(model.status == status)
    return int(session.scalar(statement) or 0)


def _bool_count(session: Session, model, seller_id: int, field) -> int:
    return int(
        session.scalar(select(func.count()).select_from(model).where(model.seller_id == seller_id).where(field.is_(True)))
        or 0
    )


def _value_counts(session: Session, model, seller_id: int, field, *, values: list[str]) -> dict[str, int]:
    counts = {value: 0 for value in values}
    rows = session.execute(
        select(field, func.count()).select_from(model).where(model.seller_id == seller_id).group_by(field)
    ).all()
    for value, count in rows:
        if value in counts:
            counts[value] = int(count)
    return counts


def _sum_amount(session: Session, seller_id: int) -> float:
    value = session.scalar(
        select(func.coalesce(func.sum(models.Quotation.total_amount), 0)).where(models.Quotation.seller_id == seller_id)
    )
    return float(value or 0)


def _retry_due_count(session: Session, seller_id: int, now: datetime) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(models.DeliveryAttempt)
            .where(models.DeliveryAttempt.seller_id == seller_id)
            .where(models.DeliveryAttempt.status == "failed")
            .where(models.DeliveryAttempt.next_retry_at <= now)
        )
        or 0
    )


def _due_followup_count(session: Session, seller_id: int, now: datetime) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(models.FollowupTask)
            .where(models.FollowupTask.seller_id == seller_id)
            .where(models.FollowupTask.status == "active")
            .where(models.FollowupTask.next_run_at <= now)
        )
        or 0
    )


def _exchange_cache_metrics(session: Session, seller_id: int, today) -> dict[str, int]:
    rules = session.scalars(
        select(models.PricingRule)
        .where(models.PricingRule.seller_id == seller_id)
        .where(models.PricingRule.deleted_at.is_(None))
    ).all()
    metrics = {"configured": 0, "unconfirmed": 0, "expired": 0, "missing_expires_at": 0}
    for rule in rules:
        cache = (rule.logistics_template or {}).get("exchange_rate_cache")
        if not isinstance(cache, dict):
            continue
        metrics["configured"] += 1
        if cache.get("confirmed") is not True:
            metrics["unconfirmed"] += 1
        expires_at = cache.get("expires_at")
        if not expires_at:
            metrics["missing_expires_at"] += 1
            continue
        if datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")).date() < today:
            metrics["expired"] += 1
    return metrics
