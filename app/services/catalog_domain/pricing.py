"""
/* ========================================================================== */
/* GEB L3: 价格规则服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session/select、app.models、ensure_seller、exchange_rate_sources 与 catalog_domain.common.require_product_scope
 * [OUTPUT]: 对外提供 list_pricing_rules、create_pricing_rule、get_pricing_rule、list_pricing_rule_versions、update_pricing_rule、refresh_pricing_rule_exchange_rate_cache、confirm_pricing_rule_exchange_rate_cache、run_due_pricing_rule_exchange_rate_refreshes
 * [POS]: services/catalog_domain 的报价规则配置真源，管理 pricing_rule 生命周期、版本快照、可信汇率缓存刷新与调度
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from copy import deepcopy
from collections.abc import Mapping
from typing import Any
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.services.catalog_domain.common import require_product_scope
from app.services.channel_gateway import ensure_seller
from app.services.exchange_rate_sources import (
    HttpJsonExchangeRateProvider,
    MappingExchangeRateProvider,
    confirm_exchange_rate_cache,
    get_configured_exchange_rate_provider,
    refresh_exchange_rate_cache,
)


def list_pricing_rules(session: Session, seller_id: int) -> list[models.PricingRule]:
    return session.scalars(
        select(models.PricingRule)
        .where(models.PricingRule.seller_id == seller_id)
        .where(models.PricingRule.deleted_at.is_(None))
        .order_by(models.PricingRule.id.desc())
    ).all()


def create_pricing_rule(session: Session, seller_id: int, data: dict[str, Any]) -> models.PricingRule:
    ensure_seller(session, seller_id)
    data = _validate_pricing_rule_data(data)
    require_product_scope(session, seller_id, data.get("product_id"))
    rule = models.PricingRule(
        seller_id=seller_id,
        product_id=data.get("product_id"),
        margin_rate=data.get("margin_rate"),
        logistics_template=data.get("logistics_template") or {},
        exchange_source=data.get("exchange_source"),
        tiered_prices=data.get("tiered_prices") or [],
        valid_days=data.get("valid_days"),
        floor_price=data["floor_price"],
        currency=data.get("currency") or "USD",
    )
    session.add(rule)
    session.flush()
    version = _record_pricing_rule_version(session, seller_id, rule, "human", "pricing_rule_created")
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="pricing_rule_created",
            target_type="pricing_rule",
            target_id=rule.id,
            is_auto=False,
            snapshot={"product_id": rule.product_id, "floor_price": str(rule.floor_price), "version": version.version},
        )
    )
    return rule


def get_pricing_rule(session: Session, seller_id: int, rule_id: int) -> models.PricingRule:
    rule = session.get(models.PricingRule, rule_id)
    if rule is None or rule.seller_id != seller_id or rule.deleted_at is not None:
        raise LookupError("Pricing rule not found")
    return rule


def list_pricing_rule_versions(session: Session, seller_id: int, rule_id: int) -> list[models.PricingRuleVersion]:
    get_pricing_rule(session, seller_id, rule_id)
    return session.scalars(
        select(models.PricingRuleVersion)
        .where(models.PricingRuleVersion.seller_id == seller_id)
        .where(models.PricingRuleVersion.pricing_rule_id == rule_id)
        .order_by(models.PricingRuleVersion.version.desc())
    ).all()


def update_pricing_rule(session: Session, seller_id: int, rule_id: int, data: dict[str, Any]) -> models.PricingRule:
    rule = get_pricing_rule(session, seller_id, rule_id)
    data = _validate_pricing_rule_data(data, existing=rule)
    if "product_id" in data:
        require_product_scope(session, seller_id, data["product_id"])
        rule.product_id = data["product_id"]
    for field in [
        "margin_rate",
        "logistics_template",
        "exchange_source",
        "tiered_prices",
        "valid_days",
        "floor_price",
        "currency",
    ]:
        if field in data and data[field] is not None:
            setattr(rule, field, data[field])
    session.flush()
    version = _record_pricing_rule_version(session, seller_id, rule, "human", "pricing_rule_updated")
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="pricing_rule_updated",
            target_type="pricing_rule",
            target_id=rule.id,
            is_auto=False,
            snapshot={"floor_price": str(rule.floor_price), "currency": rule.currency, "version": version.version},
        )
    )
    session.flush()
    return rule


def refresh_pricing_rule_exchange_rate_cache(
    session: Session,
    seller_id: int,
    rule_id: int,
    data: dict[str, Any],
) -> models.PricingRule:
    rule = get_pricing_rule(session, seller_id, rule_id)
    source_currency = _currency(data.get("source_currency") or rule.currency)
    target_currencies = data.get("target_currencies") or []
    provider = _provider_for_exchange_refresh(rule, data)
    cache = refresh_exchange_rate_cache(
        rule,
        provider,
        source_currency,
        target_currencies,
        ttl_days=int(data.get("ttl_days") or 1),
    )
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="exchange_rate_cache_refreshed",
            target_type="pricing_rule",
            target_id=rule.id,
            is_auto=False,
            snapshot={
                "source": cache.get("source"),
                "source_currency": source_currency,
                "target_currencies": target_currencies,
                "confirmed": cache.get("confirmed"),
            },
        )
    )
    session.flush()
    return rule


def confirm_pricing_rule_exchange_rate_cache(session: Session, seller_id: int, rule_id: int) -> models.PricingRule:
    rule = get_pricing_rule(session, seller_id, rule_id)
    cache = confirm_exchange_rate_cache(rule)
    _validate_exchange_rate_cache(cache)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="exchange_rate_cache_confirmed",
            target_type="pricing_rule",
            target_id=rule.id,
            is_auto=False,
            snapshot={"source": cache.get("source"), "expires_at": cache.get("expires_at")},
        )
    )
    session.flush()
    return rule


def run_due_pricing_rule_exchange_rate_refreshes(
    session: Session,
    seller_id: int,
    *,
    limit: int = 20,
    today=None,
) -> list[dict[str, Any]]:
    rules = session.scalars(
        select(models.PricingRule)
        .where(models.PricingRule.seller_id == seller_id)
        .where(models.PricingRule.deleted_at.is_(None))
        .order_by(models.PricingRule.id.asc())
        .limit(min(max(limit, 1), 100))
    ).all()
    results = []
    for rule in rules:
        try:
            outcome = _refresh_due_rule(session, seller_id, rule, today=today)
        except Exception as exc:
            outcome = {"pricing_rule_id": rule.id, "status": "failed", "error": str(exc)}
        if outcome is not None:
            results.append(outcome)
    return results


def _validate_pricing_rule_data(data: dict[str, Any], existing: models.PricingRule | None = None) -> dict[str, Any]:
    normalized = dict(data)
    floor_price = normalized.get("floor_price", existing.floor_price if existing is not None else None)
    if floor_price is not None:
        _require_positive_decimal(floor_price, "floor_price")
    margin_rate = normalized.get("margin_rate", existing.margin_rate if existing is not None else None)
    if margin_rate is not None:
        _require_non_negative_decimal(margin_rate, "margin_rate")
    if "tiered_prices" in normalized or existing is None:
        normalized["tiered_prices"] = _validate_tiered_prices(normalized.get("tiered_prices") or [])
    if "logistics_template" in normalized or existing is None:
        normalized["logistics_template"] = _validate_logistics_template(normalized.get("logistics_template") or {})
    return normalized


def _validate_tiered_prices(tiers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    seen_quantities: set[int] = set()
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiered_prices[{index}] must be an object")
        if "min_qty" not in tier or "price" not in tier:
            raise ValueError(f"tiered_prices[{index}] requires min_qty and price")
        min_qty = int(_require_positive_decimal(tier["min_qty"], f"tiered_prices[{index}].min_qty"))
        if min_qty in seen_quantities:
            raise ValueError(f"tiered_prices[{index}].min_qty must be unique")
        seen_quantities.add(min_qty)
        price = _require_positive_decimal(tier["price"], f"tiered_prices[{index}].price")
        normalized.append({**tier, "min_qty": min_qty, "price": str(price)})
    return sorted(normalized, key=lambda tier: int(tier["min_qty"]))


def _validate_logistics_template(template: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(template, dict):
        raise ValueError("logistics_template must be an object")
    if template.get("unit_cost") is not None:
        _require_non_negative_decimal(template["unit_cost"], "logistics_template.unit_cost")
    for destination, value in (template.get("destination_unit_costs") or {}).items():
        _require_non_negative_decimal(value, f"logistics_template.destination_unit_costs.{destination}")
    for source, targets in (template.get("exchange_rates") or {}).items():
        if isinstance(targets, dict):
            for target, rate in targets.items():
                _require_positive_decimal(rate, f"logistics_template.exchange_rates.{source}.{target}")
        else:
            _require_positive_decimal(targets, f"logistics_template.exchange_rates.{source}")
    _validate_exchange_rate_cache(template.get("exchange_rate_cache"))
    return template


def _validate_exchange_rate_cache(cache: Any) -> None:
    if cache is None:
        return
    if not isinstance(cache, Mapping):
        raise ValueError("logistics_template.exchange_rate_cache must be an object")
    if "confirmed" in cache and not isinstance(cache["confirmed"], bool):
        raise ValueError("logistics_template.exchange_rate_cache.confirmed must be boolean")
    if not cache.get("expires_at"):
        raise ValueError("logistics_template.exchange_rate_cache.expires_at is required")
    rates = cache.get("rates")
    if not isinstance(rates, Mapping):
        raise ValueError("logistics_template.exchange_rate_cache.rates must be an object")
    for source, targets in rates.items():
        if isinstance(targets, Mapping):
            for target, rate in targets.items():
                _require_positive_decimal(rate, f"logistics_template.exchange_rate_cache.rates.{source}.{target}")
        else:
            _require_positive_decimal(targets, f"logistics_template.exchange_rate_cache.rates.{source}")


def _record_pricing_rule_version(
    session: Session,
    seller_id: int,
    rule: models.PricingRule,
    actor: str,
    action_type: str,
) -> models.PricingRuleVersion:
    current = session.scalar(
        select(func.max(models.PricingRuleVersion.version)).where(
            models.PricingRuleVersion.seller_id == seller_id,
            models.PricingRuleVersion.pricing_rule_id == rule.id,
        )
    )
    version = models.PricingRuleVersion(
        seller_id=seller_id,
        pricing_rule_id=rule.id,
        version=int(current or 0) + 1,
        actor=actor,
        action_type=action_type,
        snapshot=_pricing_rule_snapshot(rule),
    )
    session.add(version)
    session.flush()
    return version


def _pricing_rule_snapshot(rule: models.PricingRule) -> dict[str, Any]:
    return {
        "pricing_rule_id": rule.id,
        "product_id": rule.product_id,
        "margin_rate": _decimal_snapshot(rule.margin_rate),
        "logistics_template": deepcopy(rule.logistics_template or {}),
        "exchange_source": rule.exchange_source,
        "tiered_prices": deepcopy(rule.tiered_prices or []),
        "valid_days": rule.valid_days,
        "floor_price": _decimal_snapshot(rule.floor_price),
        "currency": rule.currency,
    }


def _decimal_snapshot(value: Any) -> str | None:
    return None if value is None else str(value)


def _provider_for_exchange_refresh(rule: models.PricingRule, data: dict[str, Any]):
    source_name = data.get("source") or rule.exchange_source
    rates = data.get("rates")
    if rates is not None:
        return MappingExchangeRateProvider(source_name or "manual", rates)

    provider_config = (rule.logistics_template or {}).get("exchange_rate_provider") or {}
    endpoint = data.get("endpoint") or provider_config.get("endpoint")
    if endpoint:
        return HttpJsonExchangeRateProvider(
            source_name or "manual",
            endpoint,
            timeout_seconds=float(data.get("timeout_seconds") or provider_config.get("timeout_seconds") or 5.0),
            auth_token=data.get("auth_token") or provider_config.get("auth_token"),
        )
    return get_configured_exchange_rate_provider(source_name=source_name)


def _refresh_due_rule(
    session: Session,
    seller_id: int,
    rule: models.PricingRule,
    *,
    today=None,
) -> dict[str, Any] | None:
    logistics = rule.logistics_template if isinstance(rule.logistics_template, Mapping) else {}
    provider_config = logistics.get("exchange_rate_provider")
    if not isinstance(provider_config, Mapping):
        return None
    if provider_config.get("auto_refresh") is False:
        return None
    target_currencies = provider_config.get("target_currencies") or []
    if not isinstance(target_currencies, list) or not target_currencies:
        return {
            "pricing_rule_id": rule.id,
            "status": "skipped",
            "reason": "missing_target_currencies",
        }
    cache = logistics.get("exchange_rate_cache") if isinstance(logistics, Mapping) else None
    if not _needs_refresh(cache, today=today):
        return None
    data = {
        "source": provider_config.get("source") or rule.exchange_source or "scheduled",
        "source_currency": provider_config.get("source_currency") or rule.currency,
        "target_currencies": list(target_currencies),
        "ttl_days": int(provider_config.get("ttl_days") or 1),
    }
    if "rates" in provider_config:
        data["rates"] = provider_config["rates"]
    if "endpoint" in provider_config:
        data["endpoint"] = provider_config["endpoint"]
    refresh_pricing_rule_exchange_rate_cache(session, seller_id, rule.id, data)
    return {
        "pricing_rule_id": rule.id,
        "status": "refreshed",
        "source_currency": data["source_currency"],
        "target_currencies": list(target_currencies),
    }


def _needs_refresh(cache: Any, *, today=None) -> bool:
    if cache is None:
        return True
    if not isinstance(cache, Mapping):
        return True
    expires_at = cache.get("expires_at")
    if not expires_at:
        return True
    try:
        expiry = _parse_date(expires_at)
    except ValueError:
        return True
    return expiry < (today or _today())


def _require_positive_decimal(value: Any, field: str) -> Decimal:
    decimal = _decimal(value, field)
    if decimal <= 0:
        raise ValueError(f"{field} must be positive")
    return decimal


def _require_non_negative_decimal(value: Any, field: str) -> Decimal:
    decimal = _decimal(value, field)
    if decimal < 0:
        raise ValueError(f"{field} must be non-negative")
    return decimal


def _decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def _currency(value: str | None) -> str:
    return (value or "USD").upper()


def _parse_date(value: Any):
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _today():
    from datetime import date

    return date.today()
