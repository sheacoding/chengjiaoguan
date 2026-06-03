"""
/* ========================================================================== */
/* GEB L3: 鉴权路由                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、ApiKeyCreate、auth_keys 服务与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/auth/api-keys 列表/创建与 revoke 接口
 * [POS]: routers 的正式认证资源边界，让卖家可签发、轮换、撤销 API key
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import api_key_item
from app.schemas import ApiKeyCreate
from app.services.auth_keys import create_api_key, list_api_keys, revoke_api_key


router = APIRouter(prefix="/api/v1")


@router.get("/auth/api-keys")
def get_api_keys(
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    keys = list_api_keys(session, seller_id)
    return {"items": [api_key_item(key) for key in keys], "total": len(keys)}


@router.post("/auth/api-keys", status_code=201)
def create_api_key_endpoint(
    payload: ApiKeyCreate,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = create_api_key(session, seller_id, name=payload.name, scopes=payload.scopes)
    except LookupError as exc:
        raise api_error(404, "seller_not_found", "Seller not found") from exc
    session.commit()
    return api_key_item(result["api_key"]) | {"token": result["token"]}


@router.post("/auth/api-keys/{api_key_id}/revoke")
def revoke_api_key_endpoint(
    api_key_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        api_key = revoke_api_key(session, seller_id, api_key_id)
    except LookupError as exc:
        raise api_error(404, "api_key_not_found", "API key not found") from exc
    session.commit()
    return api_key_item(api_key)
