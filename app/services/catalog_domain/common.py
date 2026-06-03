"""
/* ========================================================================== */
/* GEB L3: 配置域共享 helper                                                  */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models 与任意标量输入
 * [OUTPUT]: 对外提供 page、require_product_scope、blank_to_none
 * [POS]: services/catalog_domain 的低层 helper，被产品、价格、导入服务复用
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from typing import Any

from sqlalchemy.orm import Session

from app import models


def page(page_number: int, page_size: int) -> tuple[int, int]:
    return max(page_number, 1), min(max(page_size, 1), 100)


def require_product_scope(session: Session, seller_id: int, product_id: int | None) -> None:
    if product_id is None:
        return
    product = session.get(models.Product, product_id)
    if product is None or product.seller_id != seller_id or product.deleted_at is not None:
        raise LookupError("Product not found")


def blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value
