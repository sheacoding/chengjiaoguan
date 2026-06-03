"""
/* ========================================================================== */
/* GEB L3: 投递尝试路由                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、delivery_attempts 服务与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 delivery-attempts 列表、单条重试、due retry 调度入口
 * [POS]: routers 的出站投递运行监控边界，连接 delivery_attempt 状态机与运维/调度 API
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import delivery_attempt_item
from app.services.delivery_attempts import (
    list_delivery_attempts,
    retry_delivery_attempt,
    run_due_delivery_retries,
)


router = APIRouter(prefix="/api/v1")


@router.get("/delivery-attempts")
def get_delivery_attempts(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    attempts, total, page, page_size = list_delivery_attempts(
        session,
        seller_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [delivery_attempt_item(attempt) for attempt in attempts],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/delivery-attempts/retry-due")
def retry_due_delivery_attempts(
    limit: int = 50,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    results = run_due_delivery_retries(session, seller_id, limit=limit)
    session.commit()
    return {"items": results, "total": len(results)}


@router.post("/delivery-attempts/{attempt_id}/retry")
def retry_one_delivery_attempt(
    attempt_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = retry_delivery_attempt(session, seller_id, attempt_id)
    except LookupError as exc:
        raise api_error(404, "delivery_attempt_not_found", "Delivery attempt not found") from exc
    session.commit()
    return result
