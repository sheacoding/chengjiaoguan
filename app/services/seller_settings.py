"""
/* ========================================================================== */
/* GEB L3: 卖家设置服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session 与 app.models.Seller
 * [OUTPUT]: 对外提供 get_seller_settings、update_seller_settings、apply_ai_disclosure
 * [POS]: services 的租户设置真源，管理 AI 身份披露与可扩展 seller.settings
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.services.catalog_domain.common import blank_to_none


AI_DISCLOSURE_TEXT = "Note: This reply was prepared with AI assistance."


def get_seller_settings(session: Session, seller_id: int) -> models.Seller:
    seller = session.get(models.Seller, seller_id)
    if seller is None or seller.deleted_at is not None:
        raise LookupError("Seller not found")
    return seller


def update_seller_settings(session: Session, seller_id: int, data: dict[str, Any]) -> models.Seller:
    seller = get_seller_settings(session, seller_id)
    if "name" in data:
        seller.name = _required_text(data["name"], "name")
    if "phone" in data:
        seller.phone = blank_to_none(data["phone"])
    if "plan" in data:
        seller.plan = _required_text(data["plan"], "plan")
    if "ai_disclosure" in data:
        seller.ai_disclosure = bool(data["ai_disclosure"])
    if "settings" in data:
        seller.settings = dict(seller.settings or {}) | dict(data["settings"] or {})
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="seller_settings_updated",
            target_type="seller",
            target_id=seller.id,
            is_auto=False,
            snapshot={key: data[key] for key in data if key != "settings"},
        )
    )
    session.flush()
    return seller


def apply_ai_disclosure(session: Session, seller_id: int, content: str) -> str:
    seller = session.get(models.Seller, seller_id)
    if seller is None or seller.ai_disclosure is False:
        return content
    if AI_DISCLOSURE_TEXT in content:
        return content
    return f"{content.rstrip()}\n\n{AI_DISCLOSURE_TEXT}"


def seller_settings_item(seller: models.Seller) -> dict[str, Any]:
    return {
        "id": seller.id,
        "name": seller.name,
        "email": seller.email,
        "phone": seller.phone,
        "plan": seller.plan,
        "ai_disclosure": seller.ai_disclosure,
        "settings": seller.settings or {},
    }


def _required_text(value: Any, field: str) -> str:
    normalized = blank_to_none(value)
    if normalized is None:
        raise ValueError(f"{field} is required")
    return str(normalized)
