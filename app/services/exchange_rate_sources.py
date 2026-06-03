"""
/* ========================================================================== */
/* GEB L3: 汇率来源边界                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os、Decimal、datetime、urllib JSON 边界与 models.PricingRule.logistics_template
 * [OUTPUT]: 对外提供 ExchangeRateSnapshot、ExchangeRateProvider、ExchangeRateProviderConfig、MappingExchangeRateProvider、HttpJsonExchangeRateProvider、get_configured_exchange_rate_provider、get_exchange_rate_provider_config、refresh_exchange_rate_cache、confirm_exchange_rate_cache
 * [POS]: services 的外部汇率源入口，把“获取汇率”“生产源配置”和“确认后使用汇率”分离，供报价配置流程刷新 exchange_rate_cache
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol
from urllib.request import Request, urlopen

from app import models


EXCHANGE_RATE_PROVIDER_ENV = "CLOSER_EXCHANGE_RATE_PROVIDER"
EXCHANGE_RATE_SOURCE_ENV = "CLOSER_EXCHANGE_RATE_SOURCE"
EXCHANGE_RATE_ENDPOINT_ENV = "CLOSER_EXCHANGE_RATE_ENDPOINT"
EXCHANGE_RATE_AUTH_TOKEN_ENV = "CLOSER_EXCHANGE_RATE_AUTH_TOKEN"
EXCHANGE_RATE_TIMEOUT_ENV = "CLOSER_EXCHANGE_RATE_TIMEOUT_SECONDS"
DISABLED_PROVIDER = "disabled"
HTTP_PROVIDER_ALIASES = {"http", "json", "remote"}
DISABLED_PROVIDER_ALIASES = {"", "disabled", "none", "off", "noop", "manual"}


@dataclass(frozen=True)
class ExchangeRateSnapshot:
    source: str
    base_currency: str
    rates: Mapping[str, Decimal]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: Mapping[str, Any] = field(default_factory=dict)


class ExchangeRateProvider(Protocol):
    source_name: str

    def fetch(self, base_currency: str, target_currencies: Sequence[str]) -> ExchangeRateSnapshot:
        raise NotImplementedError


@dataclass(frozen=True)
class ExchangeRateProviderConfig:
    provider: str
    source: str | None
    endpoint: str | None
    auth_token_configured: bool
    timeout_seconds: float | None
    status: str
    message: str

    def details(self) -> dict[str, str | float | bool | None]:
        return {
            "provider": self.provider,
            "source": self.source,
            "endpoint": self.endpoint,
            "auth_token_configured": self.auth_token_configured,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class MappingExchangeRateProvider:
    source_name: str
    rates: Mapping[str, Any]

    def fetch(self, base_currency: str, target_currencies: Sequence[str]) -> ExchangeRateSnapshot:
        base_currency = _currency(base_currency)
        targets = _target_currencies(base_currency, target_currencies)
        table = _mapping_table(self.rates, base_currency)
        return ExchangeRateSnapshot(
            source=self.source_name,
            base_currency=base_currency,
            rates={target: _lookup_required(table, base_currency, target) for target in targets},
            raw={"source": "mapping"},
        )


@dataclass(frozen=True)
class HttpJsonExchangeRateProvider:
    source_name: str
    endpoint: str
    timeout_seconds: float = 5.0
    auth_token: str | None = None

    def fetch(self, base_currency: str, target_currencies: Sequence[str]) -> ExchangeRateSnapshot:
        base_currency = _currency(base_currency)
        targets = _target_currencies(base_currency, target_currencies)
        url = self.endpoint.format(base=base_currency, symbols=",".join(targets))
        with urlopen(Request(url, headers=self._headers()), timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rates = payload.get("rates")
        if not isinstance(rates, Mapping):
            raise ValueError("Exchange rate response must contain a rates object")
        snapshot_base = _currency(payload.get("base") or base_currency)
        if snapshot_base != base_currency:
            raise ValueError(f"Exchange rate response base {snapshot_base} does not match {base_currency}")
        return ExchangeRateSnapshot(
            source=self.source_name,
            base_currency=base_currency,
            rates={target: _positive_rate(rates[target]) for target in targets if target in rates},
            raw=payload,
        )

    def _headers(self) -> dict[str, str]:
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}


def get_configured_exchange_rate_provider(
    env: Mapping[str, str] | None = None,
    *,
    source_name: str | None = None,
) -> ExchangeRateProvider:
    env = env or os.environ
    provider = _provider_name(env)
    if provider != "http":
        raise ValueError("Configured exchange rate provider is disabled")
    endpoint = _clean(env.get(EXCHANGE_RATE_ENDPOINT_ENV))
    if endpoint is None:
        raise ValueError(f"{EXCHANGE_RATE_ENDPOINT_ENV} is required for exchange rate provider")
    return HttpJsonExchangeRateProvider(
        source_name=source_name or _clean(env.get(EXCHANGE_RATE_SOURCE_ENV)) or "configured",
        endpoint=endpoint,
        timeout_seconds=_timeout(env),
        auth_token=_clean(env.get(EXCHANGE_RATE_AUTH_TOKEN_ENV)),
    )


def get_exchange_rate_provider_config(env: Mapping[str, str] | None = None) -> ExchangeRateProviderConfig:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == DISABLED_PROVIDER:
        return ExchangeRateProviderConfig(
            provider=provider,
            source=None,
            endpoint=None,
            auth_token_configured=False,
            timeout_seconds=None,
            status="warning",
            message="Global exchange rate provider is disabled; pricing rules must carry rates or endpoint config.",
        )
    if provider == "http":
        source = _clean(env.get(EXCHANGE_RATE_SOURCE_ENV)) or "configured"
        endpoint = _clean(env.get(EXCHANGE_RATE_ENDPOINT_ENV))
        timeout = _timeout(env)
        if endpoint is None:
            return ExchangeRateProviderConfig(
                provider=provider,
                source=source,
                endpoint=None,
                auth_token_configured=bool(_clean(env.get(EXCHANGE_RATE_AUTH_TOKEN_ENV))),
                timeout_seconds=timeout,
                status="failed",
                message=f"{EXCHANGE_RATE_ENDPOINT_ENV} is required for exchange rate provider.",
            )
        return ExchangeRateProviderConfig(
            provider=provider,
            source=source,
            endpoint=endpoint,
            auth_token_configured=bool(_clean(env.get(EXCHANGE_RATE_AUTH_TOKEN_ENV))),
            timeout_seconds=timeout,
            status="ok",
            message="Global exchange rate provider is configured.",
        )
    return ExchangeRateProviderConfig(
        provider=provider,
        source=_clean(env.get(EXCHANGE_RATE_SOURCE_ENV)),
        endpoint=None,
        auth_token_configured=bool(_clean(env.get(EXCHANGE_RATE_AUTH_TOKEN_ENV))),
        timeout_seconds=None,
        status="failed",
        message=f"Unsupported exchange rate provider: {provider}",
    )


def refresh_exchange_rate_cache(
    rule: models.PricingRule,
    provider: ExchangeRateProvider,
    source_currency: str,
    target_currencies: Sequence[str],
    *,
    today: date | None = None,
    ttl_days: int = 1,
) -> dict[str, Any]:
    if ttl_days <= 0:
        raise ValueError("ttl_days must be positive")

    source_currency = _currency(source_currency)
    targets = _target_currencies(source_currency, target_currencies)
    snapshot = provider.fetch(source_currency, targets)
    if _currency(snapshot.base_currency) != source_currency:
        raise ValueError("Exchange rate snapshot base currency mismatch")

    rates = {target: _positive_rate(snapshot.rates[target]) for target in targets if target in snapshot.rates}
    missing = [target for target in targets if target not in rates]
    if missing:
        raise ValueError(f"Exchange rate source missing targets: {', '.join(missing)}")

    fetched_at = snapshot.fetched_at.astimezone(timezone.utc).replace(microsecond=0)
    expires_on = (today or fetched_at.date()) + timedelta(days=ttl_days)
    cache = {
        "source": snapshot.source,
        "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_on.isoformat(),
        "confirmed": False,
        "rates": {source_currency: {target: str(rate) for target, rate in rates.items()}},
    }

    logistics = dict(rule.logistics_template or {})
    logistics["exchange_rate_cache"] = cache
    rule.logistics_template = logistics
    return cache


def confirm_exchange_rate_cache(rule: models.PricingRule) -> dict[str, Any]:
    logistics = dict(rule.logistics_template or {})
    cache = logistics.get("exchange_rate_cache")
    if not isinstance(cache, Mapping):
        raise ValueError("exchange_rate_cache is missing")
    confirmed_cache = dict(cache)
    confirmed_cache["confirmed"] = True
    logistics["exchange_rate_cache"] = confirmed_cache
    rule.logistics_template = logistics
    return confirmed_cache


def _mapping_table(rates: Mapping[str, Any], base_currency: str) -> Mapping[str, Any]:
    nested = rates.get(base_currency)
    if isinstance(nested, Mapping):
        return nested
    return rates


def _lookup_required(table: Mapping[str, Any], base_currency: str, target_currency: str) -> Decimal:
    direct = table.get(target_currency)
    if direct is not None:
        return _positive_rate(direct)
    flat = table.get(f"{base_currency}:{target_currency}")
    if flat is not None:
        return _positive_rate(flat)
    raise ValueError(f"Exchange rate source missing {base_currency}->{target_currency}")


def _target_currencies(base_currency: str, values: Sequence[str]) -> list[str]:
    targets = sorted({_currency(value) for value in values if _currency(value) != base_currency})
    if not targets:
        raise ValueError("At least one target currency is required")
    return targets


def _positive_rate(value: Any) -> Decimal:
    rate = Decimal(str(value))
    if rate <= 0:
        raise ValueError("Exchange rate must be positive")
    return rate


def _currency(value: str | None) -> str:
    return (value or "USD").upper()


def _provider_name(env: Mapping[str, str]) -> str:
    value = (_clean(env.get(EXCHANGE_RATE_PROVIDER_ENV)) or DISABLED_PROVIDER).lower()
    if value in DISABLED_PROVIDER_ALIASES:
        return DISABLED_PROVIDER
    if value in HTTP_PROVIDER_ALIASES:
        return "http"
    return value


def _timeout(env: Mapping[str, str]) -> float:
    value = _clean(env.get(EXCHANGE_RATE_TIMEOUT_ENV))
    timeout = float(value) if value else 5.0
    if timeout <= 0:
        raise ValueError("Exchange rate provider timeout must be positive")
    return timeout


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
