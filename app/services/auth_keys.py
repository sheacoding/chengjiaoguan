"""
/* ========================================================================== */
/* GEB L3: API Key 鉴权服务                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 hashlib/secrets、SQLAlchemy Session/select、utcnow 与 app.models 的 Seller/SellerApiKey
 * [OUTPUT]: 对外提供 create_api_key、list_api_keys、revoke_api_key、authenticate_api_key
 * [POS]: services 的正式认证边界，用哈希存储和撤销语义替代裸 seller token 直通生产
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow


TOKEN_PREFIX = "cak_"
TOKEN_PREFIX_LENGTH = 16


def create_api_key(
    session: Session,
    seller_id: int,
    *,
    name: str,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    seller = session.get(models.Seller, seller_id)
    if seller is None or seller.deleted_at is not None:
        raise LookupError("Seller not found")
    token = _new_token()
    api_key = models.SellerApiKey(
        seller_id=seller_id,
        name=name.strip() or "API key",
        token_prefix=token[:TOKEN_PREFIX_LENGTH],
        token_hash=_token_hash(token),
        scopes=scopes or [],
        status="active",
    )
    session.add(api_key)
    session.flush()
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="api_key_created",
            target_type="seller_api_key",
            target_id=api_key.id,
            is_auto=False,
            snapshot={"name": api_key.name, "token_prefix": api_key.token_prefix, "scopes": api_key.scopes},
        )
    )
    session.flush()
    return {"api_key": api_key, "token": token}


def list_api_keys(session: Session, seller_id: int) -> list[models.SellerApiKey]:
    return session.scalars(
        select(models.SellerApiKey)
        .where(models.SellerApiKey.seller_id == seller_id)
        .order_by(models.SellerApiKey.created_at.desc(), models.SellerApiKey.id.desc())
    ).all()


def revoke_api_key(session: Session, seller_id: int, api_key_id: int) -> models.SellerApiKey:
    api_key = session.get(models.SellerApiKey, api_key_id)
    if api_key is None or api_key.seller_id != seller_id:
        raise LookupError("API key not found")
    api_key.status = "revoked"
    api_key.revoked_at = utcnow()
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="api_key_revoked",
            target_type="seller_api_key",
            target_id=api_key.id,
            is_auto=False,
            snapshot={"name": api_key.name, "token_prefix": api_key.token_prefix},
        )
    )
    session.flush()
    return api_key


def authenticate_api_key(session: Session, token: str) -> int:
    if not token.startswith(TOKEN_PREFIX):
        raise LookupError("API key not found")
    api_key = session.scalar(
        select(models.SellerApiKey).where(
            models.SellerApiKey.token_hash == _token_hash(token),
            models.SellerApiKey.status == "active",
        )
    )
    if api_key is None:
        raise LookupError("API key not found")
    seller = session.get(models.Seller, api_key.seller_id)
    if seller is None or seller.deleted_at is not None:
        raise LookupError("Seller not found")
    api_key.last_used_at = utcnow()
    session.flush()
    return api_key.seller_id


def _new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
