"""
/* ========================================================================== */
/* GEB L3: 卖家设置路由                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、SellerSettingsPatch、租户依赖与 seller_settings 服务
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/settings 读取与修改接口
 * [POS]: routers 的租户设置边界，为设置页提供 AI 身份披露与 seller.settings 配置面
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.schemas import SellerSettingsPatch
from app.services.seller_settings import get_seller_settings, seller_settings_item, update_seller_settings


router = APIRouter(prefix="/api/v1")


@router.get("/settings")
def get_settings(
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        seller = get_seller_settings(session, seller_id)
    except LookupError as exc:
        raise api_error(404, "seller_not_found", "Seller not found") from exc
    return seller_settings_item(seller)


@router.patch("/settings")
def patch_settings(
    patch: SellerSettingsPatch,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        seller = update_seller_settings(session, seller_id, patch.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise api_error(404, "seller_not_found", "Seller not found") from exc
    except ValueError as exc:
        raise api_error(422, "invalid_settings", str(exc)) from exc
    session.commit()
    return seller_settings_item(seller)
