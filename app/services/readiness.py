"""
/* ========================================================================== */
/* GEB L3: 生产就绪诊断                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os、datetime、SQLAlchemy Session/select/func、app.models、agent.model_config、graph policy、knowledge search/index、embedding_providers、exchange_rate_sources、object_storage、ops_monitoring 与 credentials
 * [OUTPUT]: 对外提供 get_readiness，返回租户 scoped 的 seller、API key、agent model、graph decision、knowledge search/index、embedding provider、exchange provider、monitoring sink、credentials、delivery、email polling、storage、exchange 与 failed delivery 状态
 * [POS]: services 的只读运维画像，提前暴露生产配置缺口，不触真实外部网络
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.agent.graph_domain.policy import get_graph_decision_provider_config
from app.agent.model_config import get_agent_model_config
from app.services.credentials import CredentialsError, credentials_key_status, reveal_credentials
from app.services.embedding_providers import get_embedding_provider_config
from app.services.exchange_rate_sources import get_exchange_rate_provider_config
from app.services.knowledge_index_providers import get_knowledge_index_provider_config
from app.services.knowledge_search_providers import get_knowledge_search_provider_config
from app.services.object_storage import get_document_storage_config
from app.services.ops_monitoring import get_monitoring_sink_config


REQUIRED_EMAIL_KEYS = ("host", "username", "password")
REQUIRED_WHATSAPP_KEYS = ("access_token", "phone_number_id")


def get_readiness(session: Session, seller_id: int) -> dict[str, Any]:
    checks = [
        _seller_check(session, seller_id),
        _api_keys_check(session, seller_id),
        _agent_model_check(),
        _graph_decision_check(),
        _knowledge_search_check(),
        _knowledge_index_check(),
        _embedding_provider_check(),
        _exchange_rate_provider_check(),
        _monitoring_sink_check(),
        _credentials_secret_check(_delivery_mode()),
        _delivery_mode_check(),
        _object_storage_check(),
        _channels_check(session, seller_id),
        _exchange_rates_check(session, seller_id),
        _failed_delivery_attempts_check(session, seller_id),
    ]
    summary = _summary(checks)
    return {
        "status": _overall_status(summary),
        "seller_id": seller_id,
        "summary": summary,
        "checks": checks,
    }


def _seller_check(session: Session, seller_id: int) -> dict[str, Any]:
    seller = session.get(models.Seller, seller_id)
    if seller is None:
        return _check("seller", "failed", "Seller is missing", {"seller_id": seller_id})
    return _check("seller", "ok", "Seller exists", {"seller_id": seller.id, "plan": seller.plan})


def _api_keys_check(session: Session, seller_id: int) -> dict[str, Any]:
    active = session.scalar(
        select(func.count())
        .select_from(models.SellerApiKey)
        .where(models.SellerApiKey.seller_id == seller_id)
        .where(models.SellerApiKey.status == "active")
    ) or 0
    if active:
        return _check("api_keys", "ok", "Active API key is configured", {"active": active})
    return _check("api_keys", "warning", "No active API key is configured", {"active": 0})


def _agent_model_check() -> dict[str, Any]:
    config = get_agent_model_config()
    return _check("agent_model", config.status, config.message, config.details())


def _graph_decision_check() -> dict[str, Any]:
    config = get_graph_decision_provider_config()
    return _check("graph_decision", config.status, config.message, config.details())


def _knowledge_search_check() -> dict[str, Any]:
    config = get_knowledge_search_provider_config()
    return _check("knowledge_search", config.status, config.message, config.details())


def _knowledge_index_check() -> dict[str, Any]:
    config = get_knowledge_index_provider_config()
    return _check("knowledge_index", config.status, config.message, config.details())


def _embedding_provider_check() -> dict[str, Any]:
    config = get_embedding_provider_config()
    return _check("embedding_provider", config.status, config.message, config.details())


def _exchange_rate_provider_check() -> dict[str, Any]:
    config = get_exchange_rate_provider_config()
    return _check("exchange_rate_provider", config.status, config.message, config.details())


def _monitoring_sink_check() -> dict[str, Any]:
    config = get_monitoring_sink_config()
    return _check("monitoring_sink", config.status, config.message, config.details())


def _credentials_secret_check(delivery_mode: str) -> dict[str, Any]:
    configured = bool(os.getenv("CLOSER_CREDENTIALS_SECRET"))
    if configured:
        return _check("credentials_secret", "ok", "Credential seal secret is configured")
    status = "failed" if delivery_mode == "live" else "warning"
    return _check("credentials_secret", status, "Using local development credential seal secret")


def _delivery_mode_check() -> dict[str, Any]:
    mode = _delivery_mode()
    if mode == "live":
        return _check("delivery_mode", "ok", "Live delivery mode is enabled", {"mode": mode})
    return _check("delivery_mode", "warning", "Delivery is running in payload-only mode", {"mode": mode})


def _object_storage_check() -> dict[str, Any]:
    config = get_document_storage_config()
    return _check("document_storage", config.status, config.message, config.details())


def _channels_check(session: Session, seller_id: int) -> dict[str, Any]:
    channels = session.scalars(
        select(models.ChannelAccount)
        .where(models.ChannelAccount.seller_id == seller_id)
        .where(models.ChannelAccount.status == "connected")
        .order_by(models.ChannelAccount.id.asc())
    ).all()
    if not channels:
        return _check("channels", "warning", "No connected channels are configured", {"channels": []})

    details = [_channel_detail(channel) for channel in channels]
    if any(item["status"] == "failed" for item in details):
        return _check("channels", "failed", "One or more connected channels are missing required credentials", {"channels": details})
    if any(item["status"] == "warning" for item in details):
        return _check("channels", "warning", "One or more connected channels are only partially configured", {"channels": details})
    return _check("channels", "ok", "Connected channels are configured", {"channels": details})


def _channel_detail(channel: models.ChannelAccount) -> dict[str, Any]:
    try:
        credentials = reveal_credentials(channel.credentials)
    except CredentialsError as exc:
        return {
            "id": channel.id,
            "channel_type": channel.channel_type,
            "status": "failed",
            "message": str(exc),
        }

    if channel.channel_type == "email":
        return _with_credential_key_status(
            channel,
            _credential_detail(channel, credentials, REQUIRED_EMAIL_KEYS, poll_enabled=_polling_enabled(credentials)),
        )
    if channel.channel_type == "whatsapp":
        return _with_credential_key_status(channel, _credential_detail(channel, credentials, REQUIRED_WHATSAPP_KEYS))
    return _with_credential_key_status(
        channel,
        {
            "id": channel.id,
            "channel_type": channel.channel_type,
            "status": "ok",
            "message": "No external credential requirement",
        },
    )


def _credential_detail(
    channel: models.ChannelAccount,
    credentials: dict[str, Any],
    required_keys: tuple[str, ...],
    *,
    poll_enabled: bool = False,
) -> dict[str, Any]:
    missing = [key for key in required_keys if credentials.get(key) in (None, "")]
    live = _delivery_mode() == "live"
    if missing and (live or poll_enabled):
        status = "failed"
        message = "Required credentials are missing"
    elif missing:
        status = "warning"
        message = "Credentials are incomplete for live operation"
    else:
        status = "ok"
        message = "Credentials include required keys"
    return {
        "id": channel.id,
        "channel_type": channel.channel_type,
        "status": status,
        "message": message,
        "missing": missing,
        "poll_enabled": poll_enabled,
    }


def _with_credential_key_status(channel: models.ChannelAccount, detail: dict[str, Any]) -> dict[str, Any]:
    key_status = credentials_key_status(channel.credentials)
    detail["credentials_key_status"] = key_status
    if key_status == "legacy" and detail["status"] == "ok":
        detail["status"] = "warning"
        detail["message"] = "Credential seal rotation is pending"
    if key_status == "plaintext" and detail["status"] == "ok":
        detail["status"] = "warning"
        detail["message"] = "Credentials are not sealed"
    return detail


def _exchange_rates_check(session: Session, seller_id: int) -> dict[str, Any]:
    rules = session.scalars(
        select(models.PricingRule)
        .where(models.PricingRule.seller_id == seller_id)
        .where(models.PricingRule.deleted_at.is_(None))
        .order_by(models.PricingRule.id.asc())
    ).all()
    if not rules:
        return _check("exchange_rates", "warning", "No pricing rules are configured", {"rules": []})

    details = [_pricing_rule_exchange_detail(rule) for rule in rules]
    if any(item["status"] == "failed" for item in details):
        return _check("exchange_rates", "failed", "One or more exchange rate caches are invalid", {"rules": details})
    if any(item["status"] == "warning" for item in details):
        return _check("exchange_rates", "warning", "One or more pricing rules need exchange source attention", {"rules": details})
    return _check("exchange_rates", "ok", "Pricing rules have usable exchange configuration", {"rules": details})


def _pricing_rule_exchange_detail(rule: models.PricingRule) -> dict[str, Any]:
    logistics = rule.logistics_template if isinstance(rule.logistics_template, dict) else {}
    static_rates = logistics.get("exchange_rates")
    provider = logistics.get("exchange_rate_provider")
    cache = logistics.get("exchange_rate_cache")
    if isinstance(cache, dict):
        cache_status = _exchange_cache_status(cache)
        return {
            "pricing_rule_id": rule.id,
            "status": cache_status["status"],
            "message": cache_status["message"],
            "exchange_source": rule.exchange_source,
        }
    if static_rates:
        return _pricing_rule_detail(rule, "ok", "Static exchange rates are configured")
    if isinstance(provider, dict) and (provider.get("endpoint") or get_exchange_rate_provider_config().status == "ok"):
        return _pricing_rule_detail(rule, "ok", "Exchange rate provider is configured")
    if rule.exchange_source:
        return _pricing_rule_detail(rule, "warning", "Exchange source is named but no provider, cache, or static rates are configured")
    return _pricing_rule_detail(rule, "ok", "No external exchange source required")


def _exchange_cache_status(cache: dict[str, Any]) -> dict[str, str]:
    if cache.get("confirmed") is not True:
        return {"status": "warning", "message": "Exchange rate cache is not manually confirmed"}
    expires_at = _expiry_date(cache.get("expires_at"))
    if expires_at is None:
        return {"status": "failed", "message": "Exchange rate cache is missing expires_at"}
    if expires_at < date.today():
        return {"status": "warning", "message": "Exchange rate cache has expired"}
    return {"status": "ok", "message": "Confirmed exchange rate cache is usable"}


def _pricing_rule_detail(rule: models.PricingRule, status: str, message: str) -> dict[str, Any]:
    return {
        "pricing_rule_id": rule.id,
        "status": status,
        "message": message,
        "exchange_source": rule.exchange_source,
    }


def _failed_delivery_attempts_check(session: Session, seller_id: int) -> dict[str, Any]:
    failed = session.scalar(
        select(func.count())
        .select_from(models.DeliveryAttempt)
        .where(models.DeliveryAttempt.seller_id == seller_id)
        .where(models.DeliveryAttempt.status == "failed")
    ) or 0
    if failed:
        return _check("failed_delivery_attempts", "warning", "Failed delivery attempts need attention", {"failed": failed})
    return _check("failed_delivery_attempts", "ok", "No failed delivery attempts", {"failed": 0})


def _polling_enabled(credentials: dict[str, Any]) -> bool:
    return bool(credentials.get("poll_enabled") or credentials.get("polling_enabled"))


def _delivery_mode() -> str:
    return os.getenv("CLOSER_DELIVERY_MODE") or "payload_only"


def _expiry_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _check(name: str, status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message, "details": details or {}}


def _summary(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "ok": sum(1 for check in checks if check["status"] == "ok"),
        "warning": sum(1 for check in checks if check["status"] == "warning"),
        "failed": sum(1 for check in checks if check["status"] == "failed"),
    }


def _overall_status(summary: dict[str, int]) -> str:
    if summary["failed"]:
        return "unready"
    if summary["warning"]:
        return "degraded"
    return "ready"
