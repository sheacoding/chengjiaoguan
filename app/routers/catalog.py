"""
/* ========================================================================== */
/* GEB L3: 配置路由                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends/File、catalog 服务、配置 schemas 与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 products、products/import 错误报告、pricing-rules、pricing-rule versions、汇率缓存刷新确认、channels、渠道凭据轮换、dashboard/metrics API
 * [POS]: routers 的配置资源边界，连接前端产品库、报价规则、渠道设置与看板
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import channel_item, pricing_rule_item, pricing_rule_version_item, product_item
from app.schemas import (
    ChannelAccountCreate,
    ExchangeRateCacheRefresh,
    PricingRuleCreate,
    PricingRulePatch,
    ProductCreate,
    ProductPatch,
)
from app.services.catalog import (
    confirm_pricing_rule_exchange_rate_cache,
    create_channel,
    create_pricing_rule,
    create_product,
    dashboard_metrics,
    delete_product,
    get_product,
    get_pricing_rule,
    import_products_with_report,
    list_channels,
    list_pricing_rule_versions,
    list_pricing_rules,
    list_products as list_products_service,
    refresh_pricing_rule_exchange_rate_cache,
    rotate_channel_credentials,
    update_product,
    update_pricing_rule,
)
from app.services.credentials import CredentialsError


router = APIRouter(prefix="/api/v1")


@router.get("/products")
def list_products(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    products, total, page, page_size = list_products_service(
        session,
        seller_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [product_item(product) for product in products],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/products", status_code=201)
def create_product_endpoint(
    payload: ProductCreate,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    product = create_product(session, seller_id, payload.model_dump())
    session.commit()
    return product_item(product)


@router.get("/products/{product_id}")
def get_product_endpoint(
    product_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        product = get_product(session, seller_id, product_id)
    except LookupError as exc:
        raise api_error(404, "product_not_found", "Product not found") from exc
    return product_item(product)


@router.patch("/products/{product_id}")
def update_product_endpoint(
    product_id: int,
    payload: ProductPatch,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        product = update_product(session, seller_id, product_id, payload.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise api_error(404, "product_not_found", "Product not found") from exc
    session.commit()
    return product_item(product)


@router.delete("/products/{product_id}")
def delete_product_endpoint(
    product_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        product = delete_product(session, seller_id, product_id)
    except LookupError as exc:
        raise api_error(404, "product_not_found", "Product not found") from exc
    session.commit()
    return {"id": product.id, "status": product.status, "deleted": True}


@router.post("/products/import", status_code=201)
async def import_products_endpoint(
    file: UploadFile = File(...),
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = import_products_with_report(session, seller_id, file.filename or "products.csv", await file.read())
    except ValueError as exc:
        raise api_error(422, "invalid_product_import", str(exc)) from exc
    session.commit()
    return {
        "items": [product_item(product) for product in result.products],
        "total": len(result.products),
        "errors": result.error_items(),
    }


@router.get("/pricing-rules")
def list_pricing_rules_endpoint(
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    rules = list_pricing_rules(session, seller_id)
    return {"items": [pricing_rule_item(rule) for rule in rules], "total": len(rules)}


@router.post("/pricing-rules", status_code=201)
def create_pricing_rule_endpoint(
    payload: PricingRuleCreate,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rule = create_pricing_rule(session, seller_id, payload.model_dump())
    except LookupError as exc:
        raise api_error(404, "product_not_found", "Product not found") from exc
    except ValueError as exc:
        raise api_error(422, "invalid_pricing_rule", str(exc)) from exc
    session.commit()
    return pricing_rule_item(rule)


@router.get("/pricing-rules/{rule_id}")
def get_pricing_rule_endpoint(
    rule_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rule = get_pricing_rule(session, seller_id, rule_id)
    except LookupError as exc:
        raise api_error(404, "pricing_rule_not_found", "Pricing rule not found") from exc
    return pricing_rule_item(rule)


@router.get("/pricing-rules/{rule_id}/versions")
def list_pricing_rule_versions_endpoint(
    rule_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        versions = list_pricing_rule_versions(session, seller_id, rule_id)
    except LookupError as exc:
        raise api_error(404, "pricing_rule_not_found", "Pricing rule not found") from exc
    return {"items": [pricing_rule_version_item(version) for version in versions], "total": len(versions)}


@router.put("/pricing-rules/{rule_id}")
def update_pricing_rule_endpoint(
    rule_id: int,
    payload: PricingRulePatch,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rule = update_pricing_rule(session, seller_id, rule_id, payload.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise api_error(404, "pricing_rule_not_found", str(exc)) from exc
    except ValueError as exc:
        raise api_error(422, "invalid_pricing_rule", str(exc)) from exc
    session.commit()
    return pricing_rule_item(rule)


@router.post("/pricing-rules/{rule_id}/refresh-exchange-rate-cache")
def refresh_exchange_rate_cache_endpoint(
    rule_id: int,
    payload: ExchangeRateCacheRefresh,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rule = refresh_pricing_rule_exchange_rate_cache(session, seller_id, rule_id, payload.model_dump(exclude_none=True))
    except LookupError as exc:
        raise api_error(404, "pricing_rule_not_found", "Pricing rule not found") from exc
    except ValueError as exc:
        raise api_error(422, "invalid_exchange_rate_cache", str(exc)) from exc
    session.commit()
    return pricing_rule_item(rule)


@router.post("/pricing-rules/{rule_id}/confirm-exchange-rate-cache")
def confirm_exchange_rate_cache_endpoint(
    rule_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rule = confirm_pricing_rule_exchange_rate_cache(session, seller_id, rule_id)
    except LookupError as exc:
        raise api_error(404, "pricing_rule_not_found", "Pricing rule not found") from exc
    except ValueError as exc:
        raise api_error(422, "invalid_exchange_rate_cache", str(exc)) from exc
    session.commit()
    return pricing_rule_item(rule)


@router.get("/channels")
def list_channels_endpoint(
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    channels = list_channels(session, seller_id)
    try:
        return {"items": [channel_item(channel) for channel in channels], "total": len(channels)}
    except CredentialsError as exc:
        raise api_error(503, "credentials_secret_required", str(exc)) from exc


@router.post("/channels", status_code=201)
def create_channel_endpoint(
    payload: ChannelAccountCreate,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        channel = create_channel(session, seller_id, payload.model_dump())
    except CredentialsError as exc:
        raise api_error(503, "credentials_secret_required", str(exc)) from exc
    session.commit()
    return channel_item(channel)


@router.post("/channels/{channel_account_id}/rotate-credentials")
def rotate_channel_credentials_endpoint(
    channel_account_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        channel, rotated = rotate_channel_credentials(session, seller_id, channel_account_id)
    except LookupError as exc:
        raise api_error(404, "channel_not_found", "Channel not found") from exc
    except CredentialsError as exc:
        raise api_error(503, "credentials_secret_required", str(exc)) from exc
    session.commit()
    return channel_item(channel) | {"rotated": rotated}


@router.get("/dashboard/metrics")
def get_dashboard_metrics(
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    return dashboard_metrics(session, seller_id)
