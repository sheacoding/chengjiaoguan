"""
/* ========================================================================== */
/* GEB L3: 询盘路由                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、SQLAlchemy 查询、InquiryPatch 与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/inquiries 列表、详情、补丁接口
 * [POS]: routers 的询盘资源边界，负责筛选、价值排序、人工修正和审计写入
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import inquiry_detail, inquiry_list_item, require_inquiry
from app.schemas import InquiryPatch


router = APIRouter(prefix="/api/v1")


@router.get("/inquiries")
def list_inquiries(
    status: str | None = None,
    grade: str | None = None,
    channel: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    query = select(models.Inquiry).where(models.Inquiry.seller_id == seller_id)
    count_query = select(func.count()).select_from(models.Inquiry).where(models.Inquiry.seller_id == seller_id)
    for condition in _inquiry_filters(status, grade, channel, q):
        query = query.where(condition)
        count_query = count_query.where(condition)
    priority = case(
        (models.Inquiry.grade == "A", 0),
        (models.Inquiry.grade == "B", 1),
        (models.Inquiry.grade == "C", 2),
        else_=3,
    )
    query = query.order_by(priority.asc(), models.Inquiry.received_at.desc().nullslast(), models.Inquiry.id.desc())
    total = session.scalar(count_query) or 0
    inquiries = session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [inquiry_list_item(session, inquiry) for inquiry in inquiries],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/inquiries/{inquiry_id}")
def get_inquiry_detail(
    inquiry_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    inquiry = require_inquiry(session, seller_id, inquiry_id)
    return inquiry_detail(session, inquiry)


@router.patch("/inquiries/{inquiry_id}")
def patch_inquiry(
    inquiry_id: int,
    patch: InquiryPatch,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    inquiry = require_inquiry(session, seller_id, inquiry_id)
    if patch.grade is not None:
        if patch.grade not in {"A", "B", "C"}:
            raise api_error(422, "invalid_grade", "grade must be A, B, or C")
        inquiry.grade = patch.grade
    if patch.status is not None:
        inquiry.status = patch.status
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="inquiry_patched",
            target_type="inquiry",
            target_id=inquiry.id,
            is_auto=False,
            snapshot=patch.model_dump(exclude_none=True),
        )
    )
    session.commit()
    return inquiry_detail(session, inquiry)


def _inquiry_filters(status: str | None, grade: str | None, channel: str | None, q: str | None):
    filters = []
    if status:
        filters.append(models.Inquiry.status == status)
    if grade:
        filters.append(models.Inquiry.grade == grade)
    if channel:
        filters.append(models.Inquiry.source_channel == channel)
    if q:
        like = f"%{q}%"
        filters.append(or_(models.Inquiry.raw_content.ilike(like), models.Inquiry.source_channel.ilike(like)))
    return filters
