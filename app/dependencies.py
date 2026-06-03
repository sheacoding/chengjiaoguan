"""
/* ========================================================================== */
/* GEB L3: HTTP 依赖                                                          */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI Header/HTTPException、数据库 Session、auth_keys 服务解析 Bearer API key、Bearer seller token 与 MVP 租户头
 * [OUTPUT]: 对外提供 get_seller_id 与 parse_seller_token
 * [POS]: app 的请求上下文入口，被 main.py 的 /api/v1 路由消费；正式 API key 与本地 shortcut 在此收束
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import os

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.auth_keys import TOKEN_PREFIX, authenticate_api_key


DEV_AUTH_ENV = "CLOSER_ALLOW_DEV_AUTH"


def get_seller_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_seller_id: int | None = Header(default=None, alias="X-Seller-Id"),
    session: Session = Depends(get_session),
) -> int:
    if authorization:
        return parse_authorization(authorization, session)
    if _dev_auth_enabled():
        return x_seller_id or 1
    raise _auth_error()


def parse_authorization(authorization: str, session: Session) -> int:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _auth_error()
    if token.startswith(TOKEN_PREFIX):
        try:
            seller_id = authenticate_api_key(session, token)
        except LookupError as exc:
            raise _auth_error() from exc
        session.commit()
        return seller_id
    if not _dev_auth_enabled():
        raise _auth_error()
    return parse_seller_token(authorization)


def parse_seller_token(authorization: str) -> int:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _auth_error()
    prefix, _, seller_id = token.partition(":")
    if prefix != "seller" or not seller_id.isdigit() or int(seller_id) < 1:
        raise _auth_error()
    return int(seller_id)


def _auth_error() -> HTTPException:
    message = (
        "Authorization must be Bearer seller:<id> or Bearer cak_<token>"
        if _dev_auth_enabled()
        else "Authorization must be Bearer cak_<token>"
    )
    return HTTPException(
        status_code=401,
        detail={"code": "invalid_token", "message": message},
    )


def _dev_auth_enabled() -> bool:
    return _truthy(os.getenv(DEV_AUTH_ENV))


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}
