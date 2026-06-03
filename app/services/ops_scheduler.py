"""
/* ========================================================================== */
/* GEB L3: 运维调度组合边界                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、workers、readiness、ops_alerts 与 ops_monitoring
 * [OUTPUT]: 对外提供 run_scheduled_operations，把 due jobs、生产就绪画像、运行告警与监控上报收束成单次调度结果
 * [POS]: services 的外部 cron/queue 适配薄层，给部署调度器一个稳定且可观测的入口
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.ops_alerts import list_ops_alerts
from app.services.ops_monitoring import MonitoringSink, emit_ops_event
from app.services.readiness import get_readiness
from app.services.workers import run_due_jobs


def run_scheduled_operations(
    session: Session,
    seller_id: int,
    *,
    followup_limit: int = 50,
    delivery_retry_limit: int = 50,
    email_channel_limit: int = 20,
    email_message_limit: int = 20,
    pricing_exchange_rate_limit: int = 20,
    alert_limit: int = 100,
    emit_monitoring: bool = True,
    monitoring_sink: MonitoringSink | None = None,
) -> dict[str, Any]:
    jobs = run_due_jobs(
        session,
        seller_id,
        followup_limit=followup_limit,
        delivery_retry_limit=delivery_retry_limit,
        email_channel_limit=email_channel_limit,
        email_message_limit=email_message_limit,
        pricing_exchange_rate_limit=pricing_exchange_rate_limit,
    )
    readiness = get_readiness(session, seller_id)
    alerts = list_ops_alerts(session, seller_id, limit=alert_limit)
    status = _status(jobs, readiness, alerts)
    event = _event(seller_id, status, jobs, readiness, alerts)
    monitoring = _emit_monitoring(event, monitoring_sink) if emit_monitoring else {"status": "skipped", "provider": "disabled"}
    return {
        "status": status,
        "seller_id": seller_id,
        "jobs": jobs,
        "readiness": _readiness_summary(readiness),
        "alerts": _alerts_summary(alerts),
        "monitoring": monitoring,
    }


def _emit_monitoring(event: dict[str, Any], sink: MonitoringSink | None) -> dict[str, Any]:
    try:
        return emit_ops_event(event, sink=sink)
    except Exception as exc:
        return {
            "status": "failed",
            "provider": sink.name if sink is not None else "configured",
            "event_type": event["event_type"],
            "error": str(exc),
        }


def _event(
    seller_id: int,
    status: str,
    jobs: dict[str, Any],
    readiness: dict[str, Any],
    alerts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": "ops_scheduler_run",
        "seller_id": seller_id,
        "status": status,
        "jobs": _job_summary(jobs),
        "readiness": _readiness_summary(readiness),
        "alerts": _alerts_summary(alerts),
    }


def _status(jobs: dict[str, Any], readiness: dict[str, Any], alerts: dict[str, Any]) -> str:
    if readiness.get("status") == "unready" or alerts.get("status") == "critical" or _has_failed_job(jobs):
        return "critical"
    if readiness.get("status") == "degraded" or alerts.get("status") == "attention":
        return "attention"
    return "ok"


def _has_failed_job(jobs: dict[str, Any]) -> bool:
    for bucket in ["followups", "delivery_retries", "pricing_exchange_rate_refreshes", "email_polls"]:
        items = (jobs.get(bucket) or {}).get("items") or []
        if any(item.get("status") == "failed" for item in items if isinstance(item, dict)):
            return True
    return False


def _job_summary(jobs: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_jobs": jobs.get("total_jobs", 0),
        "followups": _bucket_total(jobs, "followups"),
        "delivery_retries": _bucket_total(jobs, "delivery_retries"),
        "pricing_exchange_rate_refreshes": _bucket_total(jobs, "pricing_exchange_rate_refreshes"),
        "email_polls": _bucket_total(jobs, "email_polls"),
    }


def _bucket_total(jobs: dict[str, Any], key: str) -> int:
    return int((jobs.get(key) or {}).get("total") or 0)


def _readiness_summary(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": readiness.get("status"),
        "summary": readiness.get("summary") or {},
    }


def _alerts_summary(alerts: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": alerts.get("status"),
        "total": alerts.get("total", 0),
        "counts": alerts.get("counts") or {},
    }
