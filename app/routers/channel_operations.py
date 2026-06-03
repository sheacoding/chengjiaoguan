"""
/* ========================================================================== */
/* GEB L3: 渠道运维路由                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、email_polling、channel_receipts 服务与租户依赖
 * [OUTPUT]: 对外提供 router，暴露 email channel 的 poll-email 入站轮询接口与渠道 delivery receipt 同步接口
 * [POS]: routers 的渠道运维边界，连接渠道配置、入站轮询任务与出站回执同步
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.services.channel_receipts import sync_channel_receipts
from app.services.email_polling import poll_email_channel


router = APIRouter(prefix="/api/v1")


@router.post("/channels/{channel_account_id}/poll-email")
def poll_email_channel_endpoint(
    channel_account_id: int,
    limit: int = 20,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = poll_email_channel(session, seller_id, channel_account_id, limit=limit)
    except LookupError as exc:
        raise api_error(404, "channel_not_found", "Email channel account not found") from exc
    except ValueError as exc:
        raise api_error(422, "email_poll_failed", str(exc)) from exc
    session.commit()
    return result


@router.post("/channels/{channel_account_id}/sync-receipts")
def sync_channel_receipts_endpoint(
    channel_account_id: int,
    payload: dict,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = sync_channel_receipts(session, seller_id, channel_account_id, payload)
    except LookupError as exc:
        raise api_error(404, "channel_not_found", "Channel account not found") from exc
    except ValueError as exc:
        raise api_error(422, "invalid_delivery_receipt", str(exc)) from exc
    session.commit()
    return result
