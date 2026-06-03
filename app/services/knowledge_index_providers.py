"""
/* ========================================================================== */
/* GEB L3: 知识索引 Provider 边界                                             */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os/json/urllib、KnowledgeChunk 记录与知识索引同步配置
 * [OUTPUT]: 对外提供 KnowledgeIndexProvider、DisabledKnowledgeIndexProvider、HttpKnowledgeIndexProvider、KnowledgeIndexProviderConfig、sync_knowledge_index、get_knowledge_index_provider、get_knowledge_index_provider_config
 * [POS]: services 的 RAG 索引同步边界，把本地知识入库与托管语义索引 upsert 隔离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen

from app import models


KNOWLEDGE_INDEX_PROVIDER_ENV = "CLOSER_KNOWLEDGE_INDEX_PROVIDER"
KNOWLEDGE_INDEX_ENDPOINT_ENV = "CLOSER_KNOWLEDGE_INDEX_ENDPOINT"
KNOWLEDGE_INDEX_AUTH_TOKEN_ENV = "CLOSER_KNOWLEDGE_INDEX_AUTH_TOKEN"
KNOWLEDGE_INDEX_TIMEOUT_ENV = "CLOSER_KNOWLEDGE_INDEX_TIMEOUT_SECONDS"
DISABLED_PROVIDER = "disabled"
HTTP_PROVIDER_ALIASES = {"http", "managed", "remote", "remote_index", "vector"}
DISABLED_PROVIDER_ALIASES = {"", "disabled", "none", "off", "noop", "local"}


class KnowledgeIndexProvider(Protocol):
    name: str

    def upsert(self, chunks: Sequence[models.KnowledgeChunk]) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True)
class KnowledgeIndexProviderConfig:
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
class DisabledKnowledgeIndexProvider:
    name: str = DISABLED_PROVIDER

    def upsert(self, chunks: Sequence[models.KnowledgeChunk]) -> dict[str, Any]:
        return {"status": "skipped", "provider": self.name, "indexed": 0}


@dataclass(frozen=True)
class HttpKnowledgeIndexProvider:
    endpoint: str
    auth_token: str | None = None
    timeout_seconds: float = 10.0
    name: str = "http"

    def upsert(self, chunks: Sequence[models.KnowledgeChunk]) -> dict[str, Any]:
        records = list(chunks)
        if not records:
            return {"status": "skipped", "provider": self.name, "indexed": 0}
        request = Request(
            self.endpoint,
            data=json.dumps(
                {
                    "operation": "upsert",
                    "seller_id": _single_seller_id(records),
                    "items": [_chunk_payload(chunk) for chunk in records],
                }
            ).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _upsert_result(payload, len(records), self.name)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers


def sync_knowledge_index(
    chunks: Sequence[models.KnowledgeChunk],
    *,
    provider: KnowledgeIndexProvider | None = None,
) -> dict[str, Any]:
    selected = provider or get_knowledge_index_provider()
    return selected.upsert(chunks)


def get_knowledge_index_provider(env: Mapping[str, str] | None = None) -> KnowledgeIndexProvider:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == DISABLED_PROVIDER:
        return DisabledKnowledgeIndexProvider()
    if provider == "http":
        endpoint = _clean(env.get(KNOWLEDGE_INDEX_ENDPOINT_ENV))
        if endpoint is None:
            raise ValueError(f"{KNOWLEDGE_INDEX_ENDPOINT_ENV} is required for knowledge index provider")
        return HttpKnowledgeIndexProvider(
            endpoint=endpoint,
            auth_token=_clean(env.get(KNOWLEDGE_INDEX_AUTH_TOKEN_ENV)),
            timeout_seconds=_timeout(env),
        )
    raise ValueError(f"Unsupported knowledge index provider: {provider}")


def get_knowledge_index_provider_config(env: Mapping[str, str] | None = None) -> KnowledgeIndexProviderConfig:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == DISABLED_PROVIDER:
        return KnowledgeIndexProviderConfig(
            provider=provider,
            endpoint=None,
            auth_token_configured=False,
            timeout_seconds=None,
            status="warning",
            message="Managed knowledge index sync is disabled; local knowledge chunks are the only index.",
        )
    if provider == "http":
        endpoint = _clean(env.get(KNOWLEDGE_INDEX_ENDPOINT_ENV))
        timeout = _timeout(env)
        if endpoint is None:
            return KnowledgeIndexProviderConfig(
                provider=provider,
                endpoint=None,
                auth_token_configured=bool(_clean(env.get(KNOWLEDGE_INDEX_AUTH_TOKEN_ENV))),
                timeout_seconds=timeout,
                status="failed",
                message=f"{KNOWLEDGE_INDEX_ENDPOINT_ENV} is required for knowledge index provider.",
            )
        return KnowledgeIndexProviderConfig(
            provider=provider,
            endpoint=endpoint,
            auth_token_configured=bool(_clean(env.get(KNOWLEDGE_INDEX_AUTH_TOKEN_ENV))),
            timeout_seconds=timeout,
            status="ok",
            message="Managed knowledge index sync is configured.",
        )
    return KnowledgeIndexProviderConfig(
        provider=provider,
        endpoint=None,
        auth_token_configured=bool(_clean(env.get(KNOWLEDGE_INDEX_AUTH_TOKEN_ENV))),
        timeout_seconds=None,
        status="failed",
        message=f"Unsupported knowledge index provider: {provider}",
    )


def _chunk_payload(chunk: models.KnowledgeChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.id,
        "seller_id": chunk.seller_id,
        "source_type": chunk.source_type,
        "source_ref": chunk.source_ref,
        "content": chunk.content,
        "embedding": [float(value) for value in (chunk.embedding or [])],
        "created_at": _isoformat(chunk.created_at),
        "updated_at": _isoformat(chunk.updated_at),
    }


def _upsert_result(payload: Any, expected: int, provider: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Knowledge index response must be a JSON object")
    status = _clean(payload.get("status")) or "ok"
    indexed = int(payload.get("indexed") or payload.get("count") or expected)
    return {"status": status, "provider": provider, "indexed": indexed}


def _single_seller_id(chunks: Sequence[models.KnowledgeChunk]) -> int:
    seller_ids = {chunk.seller_id for chunk in chunks}
    if len(seller_ids) != 1:
        raise ValueError("Knowledge index upsert requires chunks from one seller")
    return seller_ids.pop()


def _provider_name(env: Mapping[str, str]) -> str:
    value = (_clean(env.get(KNOWLEDGE_INDEX_PROVIDER_ENV)) or DISABLED_PROVIDER).lower()
    if value in DISABLED_PROVIDER_ALIASES:
        return DISABLED_PROVIDER
    if value in HTTP_PROVIDER_ALIASES:
        return "http"
    return value


def _timeout(env: Mapping[str, str]) -> float:
    value = _clean(env.get(KNOWLEDGE_INDEX_TIMEOUT_ENV))
    timeout = float(value) if value else 10.0
    if timeout <= 0:
        raise ValueError("Knowledge index timeout must be positive")
    return timeout


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _isoformat(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None
