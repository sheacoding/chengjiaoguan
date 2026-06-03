"""
/* ========================================================================== */
/* GEB L3: 知识向量 Provider 边界                                             */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os/json/hashlib/math/re/urllib 与 embedding provider 环境变量
 * [OUTPUT]: 对外提供 EMBEDDING_DIMENSIONS、EmbeddingProvider、EmbeddingProviderConfig、DeterministicHashEmbeddingProvider、OpenAICompatibleEmbeddingProvider、embed_texts、get_embedding_provider、get_embedding_provider_config
 * [POS]: services 的 RAG 向量生成边界，把测试用确定性哈希向量与生产 OpenAI-compatible embedding 隔离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen


EMBEDDING_DIMENSIONS = 1536
EMBEDDING_PROVIDER_ENV = "CLOSER_EMBEDDING_PROVIDER"
EMBEDDING_MODEL_ENV = "CLOSER_EMBEDDING_MODEL"
EMBEDDING_ENDPOINT_ENV = "CLOSER_EMBEDDING_ENDPOINT"
EMBEDDING_API_KEY_ENV = "CLOSER_EMBEDDING_API_KEY_ENV"
EMBEDDING_DIMENSIONS_ENV = "CLOSER_EMBEDDING_DIMENSIONS"
EMBEDDING_TIMEOUT_ENV = "CLOSER_EMBEDDING_TIMEOUT_SECONDS"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_ENDPOINT = "https://api.openai.com/v1/embeddings"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


@dataclass(frozen=True)
class EmbeddingProviderConfig:
    provider: str
    model: str | None
    endpoint: str | None
    api_key_env: str | None
    dimensions: int | None
    status: str
    message: str

    def details(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "api_key_env": self.api_key_env,
            "dimensions": self.dimensions,
        }


@dataclass(frozen=True)
class DeterministicHashEmbeddingProvider:
    dimensions: int = EMBEDDING_DIMENSIONS
    name: str = "deterministic_hash"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_vector(text, self.dimensions) for text in texts]


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider:
    endpoint: str
    api_key: str
    model: str = DEFAULT_EMBEDDING_MODEL
    dimensions: int = EMBEDDING_DIMENSIONS
    timeout_seconds: float = 10.0
    name: str = "openai_compatible"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = [str(text) for text in texts]
        if not values:
            return []

        request = Request(
            self.endpoint,
            data=json.dumps(self._payload(values)).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _vectors_from_response(payload, self.dimensions)

    def _payload(self, texts: list[str]) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        return payload


def embed_texts(
    texts: Sequence[str],
    *,
    provider: EmbeddingProvider | None = None,
) -> list[list[float]]:
    selected = provider or get_embedding_provider()
    vectors = selected.embed(texts)
    if len(vectors) != len(texts):
        raise ValueError("Embedding provider returned the wrong number of vectors")
    return vectors


def get_embedding_provider(env: Mapping[str, str] | None = None) -> EmbeddingProvider:
    env = env or os.environ
    provider = _provider_name(env)
    dimensions = _dimensions(env)
    if provider in ("deterministic", "hash", "local"):
        return DeterministicHashEmbeddingProvider(dimensions=dimensions)
    if provider in ("openai", "openai_compatible"):
        api_key_env = _api_key_env(env)
        api_key = _clean(env.get(api_key_env))
        if api_key is None:
            raise ValueError(f"{api_key_env} is required for {provider} embedding provider")
        return OpenAICompatibleEmbeddingProvider(
            endpoint=_clean(env.get(EMBEDDING_ENDPOINT_ENV)) or DEFAULT_EMBEDDING_ENDPOINT,
            api_key=api_key,
            model=_clean(env.get(EMBEDDING_MODEL_ENV)) or DEFAULT_EMBEDDING_MODEL,
            dimensions=dimensions,
            timeout_seconds=_timeout(env),
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")


def get_embedding_provider_config(env: Mapping[str, str] | None = None) -> EmbeddingProviderConfig:
    env = env or os.environ
    try:
        provider = _provider_name(env)
        dimensions = _dimensions(env)
    except ValueError as exc:
        return EmbeddingProviderConfig(
            provider=_clean((env or {}).get(EMBEDDING_PROVIDER_ENV)) or "deterministic",
            model=None,
            endpoint=None,
            api_key_env=None,
            dimensions=None,
            status="failed",
            message=str(exc),
        )

    if provider in ("deterministic", "hash", "local"):
        return EmbeddingProviderConfig(
            provider=provider,
            model=None,
            endpoint=None,
            api_key_env=None,
            dimensions=dimensions,
            status="warning",
            message="Deterministic hash embeddings are active; configure a production embedding provider.",
        )

    if provider in ("openai", "openai_compatible"):
        api_key_env = _api_key_env(env)
        model = _clean(env.get(EMBEDDING_MODEL_ENV)) or DEFAULT_EMBEDDING_MODEL
        endpoint = _clean(env.get(EMBEDDING_ENDPOINT_ENV)) or DEFAULT_EMBEDDING_ENDPOINT
        if _clean(env.get(api_key_env)) is None:
            return EmbeddingProviderConfig(
                provider=provider,
                model=model,
                endpoint=endpoint,
                api_key_env=api_key_env,
                dimensions=dimensions,
                status="failed",
                message=f"{api_key_env} is required for {provider} embedding provider.",
            )
        return EmbeddingProviderConfig(
            provider=provider,
            model=model,
            endpoint=endpoint,
            api_key_env=api_key_env,
            dimensions=dimensions,
            status="ok",
            message="Embedding provider is configured.",
        )

    return EmbeddingProviderConfig(
        provider=provider,
        model=None,
        endpoint=None,
        api_key_env=None,
        dimensions=dimensions,
        status="failed",
        message=f"Unsupported embedding provider: {provider}",
    )


def _hash_vector(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        index = int.from_bytes(digest, "big") % dimensions
        vector[index] += 1.0
    return _unit_vector(vector, dimensions)


def _vectors_from_response(payload: Any, dimensions: int) -> list[list[float]]:
    if not isinstance(payload, Mapping):
        raise ValueError("Embedding response must be a JSON object")
    data = payload.get("data")
    if not _is_sequence(data):
        raise ValueError("Embedding response must contain a data array")

    vectors = []
    ordered = sorted(
        enumerate(data),
        key=lambda item: item[1].get("index", item[0]) if isinstance(item[1], Mapping) else item[0],
    )
    for _, item in ordered:
        if not isinstance(item, Mapping) or not _is_sequence(item.get("embedding")):
            raise ValueError("Embedding response item must contain an embedding array")
        vectors.append(_unit_vector(item["embedding"], dimensions))
    return vectors


def _unit_vector(values: Sequence[Any], dimensions: int) -> list[float]:
    vector = [float(value) for value in values]
    if len(vector) != dimensions:
        raise ValueError(f"Embedding dimension mismatch: expected {dimensions}, got {len(vector)}")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def _provider_name(env: Mapping[str, str]) -> str:
    return (_clean(env.get(EMBEDDING_PROVIDER_ENV)) or "deterministic").lower()


def _api_key_env(env: Mapping[str, str]) -> str:
    return _clean(env.get(EMBEDDING_API_KEY_ENV)) or OPENAI_API_KEY_ENV


def _dimensions(env: Mapping[str, str]) -> int:
    value = _clean(env.get(EMBEDDING_DIMENSIONS_ENV))
    dimensions = int(value) if value else EMBEDDING_DIMENSIONS
    if dimensions <= 0:
        raise ValueError("Embedding dimensions must be positive")
    return dimensions


def _timeout(env: Mapping[str, str]) -> float:
    value = _clean(env.get(EMBEDDING_TIMEOUT_ENV))
    timeout = float(value) if value else 10.0
    if timeout <= 0:
        raise ValueError("Embedding timeout must be positive")
    return timeout


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
