"""
/* ========================================================================== */
/* GEB L3: 汇率解析服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 datetime.date、Decimal、Mapping 与 pricing_rule.logistics_template 的 exchange_rates/exchange_rate_cache
 * [OUTPUT]: 对外提供 resolve_exchange_rate，解析静态汇率表或已确认且未过期的汇率缓存
 * [POS]: services 的报价汇率边界，让 quote_engine 不直接理解缓存、过期与人工确认结构
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app import models


def resolve_exchange_rate(
    source_currency: str,
    target_currency: str,
    rule: models.PricingRule,
    *,
    today: date | None = None,
) -> Decimal:
    source_currency = _currency(source_currency)
    target_currency = _currency(target_currency)
    if source_currency == target_currency:
        return Decimal("1")

    logistics = rule.logistics_template if isinstance(rule.logistics_template, Mapping) else {}
    cached = _cache_table(logistics, today or date.today())
    if cached is not None:
        rate = _table_rate(cached, source_currency, target_currency)
        if rate is not None:
            return rate

    static = logistics.get("exchange_rates")
    if isinstance(static, Mapping):
        rate = _table_rate(static, source_currency, target_currency)
        if rate is not None:
            return rate

    raise ValueError(f"Missing exchange rate {source_currency}->{target_currency}")


def _cache_table(logistics: Mapping[str, Any], today: date) -> Mapping[str, Any] | None:
    cache = logistics.get("exchange_rate_cache")
    if cache is None:
        return None
    if not isinstance(cache, Mapping):
        raise ValueError("exchange_rate_cache must be an object")
    if cache.get("confirmed") is not True:
        raise ValueError("Exchange rate cache must be manually confirmed")
    expires_at = _expiry_date(cache.get("expires_at"))
    if expires_at is None:
        raise ValueError("exchange_rate_cache.expires_at is required")
    if expires_at < today:
        raise ValueError("Exchange rate cache has expired")
    rates = cache.get("rates")
    if not isinstance(rates, Mapping):
        raise ValueError("exchange_rate_cache.rates must be an object")
    return rates


def _table_rate(table: Mapping[str, Any], source_currency: str, target_currency: str) -> Decimal | None:
    direct = _lookup_rate(table, source_currency, target_currency)
    if direct is not None:
        return direct
    inverse = _lookup_rate(table, target_currency, source_currency)
    if inverse is not None:
        return Decimal("1") / inverse
    return None


def _lookup_rate(table: Mapping[str, Any], source_currency: str, target_currency: str) -> Decimal | None:
    nested = table.get(source_currency)
    if isinstance(nested, Mapping) and target_currency in nested:
        return _positive_rate(nested[target_currency])
    flat = table.get(f"{source_currency}:{target_currency}")
    if flat is not None:
        return _positive_rate(flat)
    return None


def _expiry_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _positive_rate(value: Any) -> Decimal:
    rate = Decimal(str(value))
    if rate <= 0:
        raise ValueError("Exchange rate must be positive")
    return rate


def _currency(value: str | None) -> str:
    return (value or "USD").upper()
