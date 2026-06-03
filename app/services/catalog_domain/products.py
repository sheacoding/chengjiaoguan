"""
/* ========================================================================== */
/* GEB L3: 产品库服务                                                         */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session/select/func、app.models、utcnow、ensure_seller 与 catalog_domain.common
 * [OUTPUT]: 对外提供 list_products、create_product、get_product、update_product、delete_product
 * [POS]: services/catalog_domain 的产品真源，管理 product CRUD、软删除与审计日志
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow
from app.services.catalog_domain.common import blank_to_none, page as clamp_page
from app.services.channel_gateway import ensure_seller


def list_products(
    session: Session,
    seller_id: int,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[models.Product], int, int, int]:
    page, page_size = clamp_page(page, page_size)
    query = select(models.Product).where(models.Product.seller_id == seller_id).where(models.Product.deleted_at.is_(None))
    count_query = select(func.count()).select_from(models.Product).where(models.Product.seller_id == seller_id).where(models.Product.deleted_at.is_(None))
    if status:
        query = query.where(models.Product.status == status)
        count_query = count_query.where(models.Product.status == status)
    total = session.scalar(count_query) or 0
    items = session.scalars(query.order_by(models.Product.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return items, total, page, page_size


def create_product(session: Session, seller_id: int, data: dict[str, Any]) -> models.Product:
    ensure_seller(session, seller_id)
    product = models.Product(
        seller_id=seller_id,
        name=str(data["name"]).strip(),
        sku=blank_to_none(data.get("sku")),
        specs=data.get("specs") or {},
        cost=data.get("cost"),
        currency=data.get("currency") or "USD",
        moq=data.get("moq"),
        images=data.get("images") or [],
        description=blank_to_none(data.get("description")),
        status=data.get("status") or "active",
    )
    session.add(product)
    session.flush()
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="product_created",
            target_type="product",
            target_id=product.id,
            is_auto=False,
            snapshot={"name": product.name, "sku": product.sku},
        )
    )
    return product


def get_product(session: Session, seller_id: int, product_id: int) -> models.Product:
    product = session.get(models.Product, product_id)
    if product is None or product.seller_id != seller_id or product.deleted_at is not None:
        raise LookupError("Product not found")
    return product


def update_product(session: Session, seller_id: int, product_id: int, data: dict[str, Any]) -> models.Product:
    product = get_product(session, seller_id, product_id)
    for field in ["name", "sku", "specs", "cost", "currency", "moq", "images", "description", "status"]:
        if field in data:
            value = data[field]
            if field in {"name", "sku", "description"}:
                value = blank_to_none(value)
            setattr(product, field, value)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="product_updated",
            target_type="product",
            target_id=product.id,
            is_auto=False,
            snapshot={"name": product.name, "sku": product.sku, "status": product.status},
        )
    )
    session.flush()
    return product


def delete_product(session: Session, seller_id: int, product_id: int) -> models.Product:
    product = get_product(session, seller_id, product_id)
    product.deleted_at = utcnow()
    product.status = "deleted"
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="product_deleted",
            target_type="product",
            target_id=product.id,
            is_auto=False,
            snapshot={"name": product.name, "sku": product.sku},
        )
    )
    session.flush()
    return product
