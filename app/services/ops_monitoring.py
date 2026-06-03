"""
/* ========================================================================== */
/* GEB L3: 运维监控 Sink 边界                                                 */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os/json/urllib 与运维事件 payload
 * [OUTPUT]: 对外提供 MonitoringSink、DisabledMonitoringSink、HttpMonitoringSink、MonitoringSinkConfig、emit_ops_event、get_monitoring_sink、get_monitoring_sink_config
 * [POS]: services 的外部监控边界，把 scheduler/readiness/alerts 事件上报从业务任务执行中分离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen


MONITOR_PROVIDER_ENV = "CLOSER_OPS_MONITOR_PROVIDER"
MONITOR_ENDPOINT_ENV = "CLOSER_OPS_MONITOR_ENDPOINT"
MONITOR_AUTH_TOKEN_ENV = "CLOSER_OPS_MONITOR_AUTH_TOKEN"
MONITOR_TIMEOUT_ENV = "CLOSER_OPS_MONITOR_TIMEOUT_SECONDS"
DISABLED_PROVIDER = "disabled"
HTTP_PROVIDER_ALIASES = {"http", "webhook", "remote"}
DISABLED_PROVIDER_ALIASES = {"", "disabled", "none", "off", "noop"}


class MonitoringSink(Protocol):
    name: str

    def emit(self, event: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True)
class MonitoringSinkConfig:
    provider: str
    endpoint: str | None
    auth_token_configured: bool
    timeout_seconds: float | None
    status: str
    message: str

    def details(self) -> dict[str, str | float | bool | None]:
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "auth_token_configured": self.auth_token_configured,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class DisabledMonitoringSink:
    name: str = DISABLED_PROVIDER

    def emit(self, event: Mapping[str, Any]) -> dict[str, Any]:
        return {"status": "skipped", "provider": self.name, "event_type": event.get("event_type")}


@dataclass(frozen=True)
class HttpMonitoringSink:
    endpoint: str
    auth_token: str | None = None
    timeout_seconds: float = 10.0
    name: str = "http"

    def emit(self, event: Mapping[str, Any]) -> dict[str, Any]:
        request = Request(
            self.endpoint,
            data=json.dumps(dict(event)).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body) if body.strip() else {}
        return _monitor_result(payload, self.name, event.get("event_type"))

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers


def emit_ops_event(
    event: Mapping[str, Any],
    *,
    sink: MonitoringSink | None = None,
) -> dict[str, Any]:
    selected = sink or get_monitoring_sink()
    return selected.emit(event)


def get_monitoring_sink(env: Mapping[str, str] | None = None) -> MonitoringSink:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == DISABLED_PROVIDER:
        return DisabledMonitoringSink()
    if provider == "http":
        endpoint = _clean(env.get(MONITOR_ENDPOINT_ENV))
        if endpoint is None:
            raise ValueError(f"{MONITOR_ENDPOINT_ENV} is required for ops monitoring sink")
        return HttpMonitoringSink(
            endpoint=endpoint,
            auth_token=_clean(env.get(MONITOR_AUTH_TOKEN_ENV)),
            timeout_seconds=_timeout(env),
        )
    raise ValueError(f"Unsupported ops monitoring sink: {provider}")


def get_monitoring_sink_config(env: Mapping[str, str] | None = None) -> MonitoringSinkConfig:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == DISABLED_PROVIDER:
        return MonitoringSinkConfig(
            provider=provider,
            endpoint=None,
            auth_token_configured=False,
            timeout_seconds=None,
            status="warning",
            message="Ops monitoring sink is disabled; scheduler runs will not be pushed externally.",
        )
    if provider == "http":
        endpoint = _clean(env.get(MONITOR_ENDPOINT_ENV))
        timeout = _timeout(env)
        if endpoint is None:
            return MonitoringSinkConfig(
                provider=provider,
                endpoint=None,
                auth_token_configured=bool(_clean(env.get(MONITOR_AUTH_TOKEN_ENV))),
                timeout_seconds=timeout,
                status="failed",
                message=f"{MONITOR_ENDPOINT_ENV} is required for ops monitoring sink.",
            )
        return MonitoringSinkConfig(
            provider=provider,
            endpoint=endpoint,
            auth_token_configured=bool(_clean(env.get(MONITOR_AUTH_TOKEN_ENV))),
            timeout_seconds=timeout,
            status="ok",
            message="Ops monitoring sink is configured.",
        )
    return MonitoringSinkConfig(
        provider=provider,
        endpoint=None,
        auth_token_configured=bool(_clean(env.get(MONITOR_AUTH_TOKEN_ENV))),
        timeout_seconds=None,
        status="failed",
        message=f"Unsupported ops monitoring sink: {provider}",
    )


def _monitor_result(payload: Any, provider: str, event_type: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Ops monitoring response must be a JSON object")
    return {
        "status": _clean(payload.get("status")) or "ok",
        "provider": provider,
        "event_type": event_type,
        "external_id": _clean(payload.get("id") or payload.get("external_id")),
    }


def _provider_name(env: Mapping[str, str]) -> str:
    value = (_clean(env.get(MONITOR_PROVIDER_ENV)) or DISABLED_PROVIDER).lower()
    if value in DISABLED_PROVIDER_ALIASES:
        return DISABLED_PROVIDER
    if value in HTTP_PROVIDER_ALIASES:
        return "http"
    return value


def _timeout(env: Mapping[str, str]) -> float:
    value = _clean(env.get(MONITOR_TIMEOUT_ENV))
    timeout = float(value) if value else 10.0
    if timeout <= 0:
        raise ValueError("Ops monitoring timeout must be positive")
    return timeout


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
