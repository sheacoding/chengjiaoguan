"""
/* ========================================================================== */
/* GEB L3: 通知路由                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、NotificationPatch、notifications 服务与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/notifications 列表与通知状态修改接口
 * [POS]: routers 的通知资源边界，让前端工作台读取未读提醒并标记 read/archived
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import notification_item
from app.schemas import NotificationPatch
from app.services.notifications import list_notifications, update_notification_status


router = APIRouter(prefix="/api/v1")


@router.get("/notifications")
def get_notifications(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    notifications, total, page, page_size = list_notifications(
        session,
        seller_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [notification_item(notification) for notification in notifications],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/notifications/{notification_id}")
def patch_notification(
    notification_id: int,
    patch: NotificationPatch,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        notification = update_notification_status(session, seller_id, notification_id, patch.status)
    except LookupError as exc:
        raise api_error(404, "notification_not_found", "Notification not found") from exc
    except ValueError as exc:
        raise api_error(422, "invalid_notification", str(exc)) from exc
    session.commit()
    return notification_item(notification)
