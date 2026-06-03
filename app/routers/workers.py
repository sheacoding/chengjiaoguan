"""
/* ========================================================================== */
/* GEB L3: 运维任务路由                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、租户依赖、SQLAlchemy Session、workers、ops_scheduler、readiness 与 ops_alerts 服务
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/workers/run-due、/api/v1/ops/scheduler/run、/api/v1/ops/readiness 与 /api/v1/ops/alerts
 * [POS]: routers 的运维边界，让外部 cron/queue 触发 due jobs/调度组合入口，并让部署层读取生产配置画像与运行告警
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.services.ops_alerts import list_ops_alerts
from app.services.readiness import get_readiness
from app.services.ops_scheduler import run_scheduled_operations
from app.services.workers import run_due_jobs


router = APIRouter(prefix="/api/v1")


@router.post("/workers/run-due")
def run_due_workers(
    followup_limit: int = 50,
    delivery_retry_limit: int = 50,
    email_channel_limit: int = 20,
    email_message_limit: int = 20,
    pricing_exchange_rate_limit: int = 20,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    result = run_due_jobs(
        session,
        seller_id,
        followup_limit=followup_limit,
        delivery_retry_limit=delivery_retry_limit,
        email_channel_limit=email_channel_limit,
        email_message_limit=email_message_limit,
        pricing_exchange_rate_limit=pricing_exchange_rate_limit,
    )
    session.commit()
    return result


@router.post("/ops/scheduler/run")
def run_ops_scheduler(
    followup_limit: int = 50,
    delivery_retry_limit: int = 50,
    email_channel_limit: int = 20,
    email_message_limit: int = 20,
    pricing_exchange_rate_limit: int = 20,
    alert_limit: int = 100,
    emit_monitoring: bool = True,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    result = run_scheduled_operations(
        session,
        seller_id,
        followup_limit=followup_limit,
        delivery_retry_limit=delivery_retry_limit,
        email_channel_limit=email_channel_limit,
        email_message_limit=email_message_limit,
        pricing_exchange_rate_limit=pricing_exchange_rate_limit,
        alert_limit=alert_limit,
        emit_monitoring=emit_monitoring,
    )
    session.commit()
    return result


@router.get("/ops/readiness")
def get_ops_readiness(
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    return get_readiness(session, seller_id)


@router.get("/ops/alerts")
def get_ops_alerts(
    limit: int = 100,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    return list_ops_alerts(session, seller_id, limit=limit)
