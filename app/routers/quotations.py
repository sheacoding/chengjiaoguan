"""
/* ========================================================================== */
/* GEB L3: 报价路由                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends/Response、QuotationPatch、quotations 服务与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 quotations 详情、修改、发送与底价发送审批接口
 * [POS]: routers 的报价资源边界，处理报价人工编辑、发送与地板价审批移交
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import quotation_detail
from app.schemas import QuotationPatch
from app.services.quotations import get_quotation, patch_quotation, request_quotation_send_approval, send_quotation


router = APIRouter(prefix="/api/v1")


@router.get("/quotations/{quotation_id}")
def get_quotation_detail(
    quotation_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        quotation = get_quotation(session, seller_id, quotation_id)
    except LookupError as exc:
        raise api_error(404, "quotation_not_found", "Quotation not found") from exc
    return quotation_detail(quotation)


@router.patch("/quotations/{quotation_id}")
def update_quotation(
    quotation_id: int,
    payload: QuotationPatch,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        quotation = patch_quotation(
            session,
            seller_id,
            quotation_id,
            terms=payload.terms,
            valid_until=payload.valid_until,
            status=payload.status,
            total_amount=payload.total_amount,
            hits_floor=payload.hits_floor,
            items=[item.model_dump() for item in payload.items] if payload.items is not None else None,
        )
    except LookupError as exc:
        raise api_error(404, "quotation_not_found", "Quotation not found") from exc
    session.commit()
    return quotation_detail(quotation)


@router.post("/quotations/{quotation_id}/send")
def send_quotation_endpoint(
    quotation_id: int,
    response: Response,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = send_quotation(session, seller_id, quotation_id)
    except LookupError as exc:
        raise api_error(404, "quotation_not_found", str(exc)) from exc
    except PermissionError as exc:
        try:
            result = request_quotation_send_approval(session, seller_id, quotation_id)
        except LookupError as lookup_exc:
            raise api_error(404, "quotation_not_found", str(lookup_exc)) from lookup_exc
        session.commit()
        response.status_code = 202
        return result
    session.commit()
    return result
