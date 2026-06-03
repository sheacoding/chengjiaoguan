"""
/* ========================================================================== */
/* GEB L3: 知识检索 Provider 边界                                             */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os/json/Decimal/urllib、SQLAlchemy KnowledgeChunk 记录与知识检索上下文
 * [OUTPUT]: 对外提供 KnowledgeSearchProvider、RuleBasedKnowledgeSearchProvider、HttpKnowledgeSearchProvider、ManagedIndexKnowledgeSearchProvider、KnowledgeSearchProviderConfig、get_knowledge_search_provider、get_knowledge_search_provider_config
 * [POS]: services 的知识检索决策边界，把本地余弦排序、远端重排与托管向量索引查询分离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from urllib.request import Request, urlopen

from app import models


KNOWLEDGE_SEARCH_PROVIDER_ENV = "CLOSER_KNOWLEDGE_SEARCH_PROVIDER"
KNOWLEDGE_SEARCH_ENDPOINT_ENV = "CLOSER_KNOWLEDGE_SEARCH_ENDPOINT"
KNOWLEDGE_SEARCH_AUTH_TOKEN_ENV = "CLOSER_KNOWLEDGE_SEARCH_AUTH_TOKEN"
KNOWLEDGE_SEARCH_TIMEOUT_ENV = "CLOSER_KNOWLEDGE_SEARCH_TIMEOUT_SECONDS"
RULE_BASED_PROVIDER = "rule_based"
HTTP_PROVIDER_ALIASES = {"http", "remote", "vector", "semantic"}
MANAGED_INDEX_PROVIDER = "managed_index"
MANAGED_INDEX_PROVIDER_ALIASES = {"managed", "hosted", "remote_index", "managed_index"}


class KnowledgeSearchProvider(Protocol):
    name: str

    def search(
        self,
        query: str,
        query_vector: Sequence[float],
        chunks: Sequence[models.KnowledgeChunk],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


@dataclass(frozen=True)
class KnowledgeSearchProviderConfig:
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
class RuleBasedKnowledgeSearchProvider:
    name: str = RULE_BASED_PROVIDER

    def search(
        self,
        query: str,
        query_vector: Sequence[float],
        chunks: Sequence[models.KnowledgeChunk],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        scored = []
        for chunk in chunks:
            score = _cosine(query_vector, chunk.embedding or [])
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (item[0], item[1].id), reverse=True)
        return [
            {
                "chunk_id": chunk.id,
                "source_type": chunk.source_type,
                "source_ref": chunk.source_ref,
                "content": chunk.content,
                "score": round(score, 6),
            }
            for score, chunk in scored[:limit]
        ]


@dataclass(frozen=True)
class HttpKnowledgeSearchProvider:
    endpoint: str
    auth_token: str | None = None
    timeout_seconds: float = 10.0
    name: str = "http"

    def search(
        self,
        query: str,
        query_vector: Sequence[float],
        chunks: Sequence[models.KnowledgeChunk],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        request = Request(
            self.endpoint,
            data=json.dumps(
                {
                    "query": query,
                    "query_vector": [float(value) for value in query_vector],
                    "limit": limit,
                    "chunks": [_chunk_snapshot(chunk) for chunk in chunks],
                }
            ).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        items = _response_items(payload)
        return [_normalize_item(item) for item in items[:limit]]

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers


@dataclass(frozen=True)
class ManagedIndexKnowledgeSearchProvider:
    endpoint: str
    auth_token: str | None = None
    timeout_seconds: float = 10.0
    name: str = MANAGED_INDEX_PROVIDER

    def search(
        self,
        query: str,
        query_vector: Sequence[float],
        chunks: Sequence[models.KnowledgeChunk],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        scoped_chunks = list(chunks)
        if not scoped_chunks:
            return []
        request = Request(
            self.endpoint,
            data=json.dumps(
                {
                    "query": query,
                    "query_vector": [float(value) for value in query_vector],
                    "limit": limit,
                    "filter": _managed_index_filter(scoped_chunks),
                }
            ).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        items = _response_items(payload)
        return [_normalize_item(item) for item in items[:limit]]

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers


def get_knowledge_search_provider(env: Mapping[str, str] | None = None) -> KnowledgeSearchProvider:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == RULE_BASED_PROVIDER:
        return RuleBasedKnowledgeSearchProvider()
    if provider == "http":
        endpoint = _clean(env.get(KNOWLEDGE_SEARCH_ENDPOINT_ENV))
        if endpoint is None:
            raise ValueError(f"{KNOWLEDGE_SEARCH_ENDPOINT_ENV} is required for knowledge search provider")
        return HttpKnowledgeSearchProvider(
            endpoint=endpoint,
            auth_token=_clean(env.get(KNOWLEDGE_SEARCH_AUTH_TOKEN_ENV)),
            timeout_seconds=_timeout(env),
        )
    if provider == MANAGED_INDEX_PROVIDER:
        endpoint = _clean(env.get(KNOWLEDGE_SEARCH_ENDPOINT_ENV))
        if endpoint is None:
            raise ValueError(f"{KNOWLEDGE_SEARCH_ENDPOINT_ENV} is required for managed knowledge index search")
        return ManagedIndexKnowledgeSearchProvider(
            endpoint=endpoint,
            auth_token=_clean(env.get(KNOWLEDGE_SEARCH_AUTH_TOKEN_ENV)),
            timeout_seconds=_timeout(env),
        )
    raise ValueError(f"Unsupported knowledge search provider: {provider}")


def get_knowledge_search_provider_config(env: Mapping[str, str] | None = None) -> KnowledgeSearchProviderConfig:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == RULE_BASED_PROVIDER:
        return KnowledgeSearchProviderConfig(
            provider=provider,
            endpoint=None,
            auth_token_configured=False,
            timeout_seconds=None,
            status="warning",
            message="Rule-based knowledge search is active; configure a production vector index provider.",
        )
    if provider == "http":
        endpoint = _clean(env.get(KNOWLEDGE_SEARCH_ENDPOINT_ENV))
        timeout = _timeout(env)
        if endpoint is None:
            return KnowledgeSearchProviderConfig(
                provider=provider,
                endpoint=None,
                auth_token_configured=bool(_clean(env.get(KNOWLEDGE_SEARCH_AUTH_TOKEN_ENV))),
                timeout_seconds=timeout,
                status="failed",
                message=f"{KNOWLEDGE_SEARCH_ENDPOINT_ENV} is required for knowledge search provider.",
            )
        return KnowledgeSearchProviderConfig(
            provider=provider,
            endpoint=endpoint,
            auth_token_configured=bool(_clean(env.get(KNOWLEDGE_SEARCH_AUTH_TOKEN_ENV))),
            timeout_seconds=timeout,
            status="ok",
            message="Knowledge search provider is configured.",
        )
    if provider == MANAGED_INDEX_PROVIDER:
        endpoint = _clean(env.get(KNOWLEDGE_SEARCH_ENDPOINT_ENV))
        timeout = _timeout(env)
        if endpoint is None:
            return KnowledgeSearchProviderConfig(
                provider=provider,
                endpoint=None,
                auth_token_configured=bool(_clean(env.get(KNOWLEDGE_SEARCH_AUTH_TOKEN_ENV))),
                timeout_seconds=timeout,
                status="failed",
                message=f"{KNOWLEDGE_SEARCH_ENDPOINT_ENV} is required for managed knowledge index search.",
            )
        return KnowledgeSearchProviderConfig(
            provider=provider,
            endpoint=endpoint,
            auth_token_configured=bool(_clean(env.get(KNOWLEDGE_SEARCH_AUTH_TOKEN_ENV))),
            timeout_seconds=timeout,
            status="ok",
            message="Managed knowledge index search is configured.",
        )
    return KnowledgeSearchProviderConfig(
        provider=provider,
        endpoint=None,
        auth_token_configured=bool(_clean(env.get(KNOWLEDGE_SEARCH_AUTH_TOKEN_ENV))),
        timeout_seconds=None,
        status="failed",
        message=f"Unsupported knowledge search provider: {provider}",
    )


def _chunk_snapshot(chunk: models.KnowledgeChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.id,
        "source_type": chunk.source_type,
        "source_ref": chunk.source_ref,
        "content": chunk.content,
        "embedding": [float(value) for value in (chunk.embedding or [])],
    }


def _managed_index_filter(chunks: Sequence[models.KnowledgeChunk]) -> dict[str, Any]:
    seller_ids = sorted({chunk.seller_id for chunk in chunks})
    return {
        "seller_id": seller_ids[0] if len(seller_ids) == 1 else None,
        "seller_ids": seller_ids,
        "source_types": sorted({chunk.source_type for chunk in chunks}),
        "chunk_ids": [chunk.id for chunk in chunks],
    }


def _response_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        items = payload.get("items") or payload.get("results") or payload.get("matches")
        if isinstance(items, list):
            return items
    raise ValueError("Knowledge search response must contain a list of results")


def _normalize_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError("Knowledge search result must be an object")
    return {
        "chunk_id": int(item.get("chunk_id") or item.get("id")),
        "source_type": item.get("source_type"),
        "source_ref": item.get("source_ref"),
        "content": item.get("content"),
        "score": round(_decimal(item.get("score")), 6),
    }


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    return sum(float(left[index]) * float(right[index]) for index in range(length))


def _provider_name(env: Mapping[str, str]) -> str:
    value = (_clean(env.get(KNOWLEDGE_SEARCH_PROVIDER_ENV)) or RULE_BASED_PROVIDER).lower()
    if value in HTTP_PROVIDER_ALIASES:
        return "http"
    if value in MANAGED_INDEX_PROVIDER_ALIASES:
        return MANAGED_INDEX_PROVIDER
    return value


def _timeout(env: Mapping[str, str]) -> float:
    value = _clean(env.get(KNOWLEDGE_SEARCH_TIMEOUT_ENV))
    timeout = float(value) if value else 10.0
    if timeout <= 0:
        raise ValueError("Knowledge search timeout must be positive")
    return timeout


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _decimal(value: Any) -> float:
    return float(Decimal(str(value or 0)))
