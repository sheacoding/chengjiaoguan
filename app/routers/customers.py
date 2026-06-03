"""
/* ========================================================================== */
/* GEB L3: 客户档案路由                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、CustomerPatch、crm 与 data_privacy 服务、common 序列化
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/customers 列表、详情、档案修改与客户数据擦除接口
 * [POS]: routers 的 CRM 资源边界，给前端客户页和会话右侧档案抽屉提供租户隔离数据
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import customer_item
from app.schemas import CustomerPatch
from app.services.crm import get_customer, get_customer_activity, list_customers as list_customers_service, update_customer_profile
from app.services.data_privacy import erase_customer_data


router = APIRouter(prefix="/api/v1")


@router.get("/customers")
def list_customers(
    status: str | None = None,
    grade: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    customers, total, page, page_size = list_customers_service(
        session,
        seller_id,
        status=status,
        grade=grade,
        q=q,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [customer_item(customer) for customer in customers],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/customers/{customer_id}")
def get_customer_detail(
    customer_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        customer = get_customer(session, seller_id, customer_id)
        activity = get_customer_activity(session, seller_id, customer_id)
    except LookupError as exc:
        raise api_error(404, "customer_not_found", "Customer not found") from exc
    return customer_item(customer) | activity


@router.patch("/customers/{customer_id}")
def patch_customer(
    customer_id: int,
    patch: CustomerPatch,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        customer = update_customer_profile(session, seller_id, customer_id, patch.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise api_error(404, "customer_not_found", "Customer not found") from exc
    session.commit()
    return customer_item(customer)


@router.delete("/customers/{customer_id}")
def delete_customer(
    customer_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = erase_customer_data(session, seller_id, customer_id)
    except LookupError as exc:
        raise api_error(404, "customer_not_found", "Customer not found") from exc
    session.commit()
    return result
