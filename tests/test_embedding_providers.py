"""
/* ========================================================================== */
/* GEB L3: 知识向量 Provider 测试                                             */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 json、pytest monkeypatch 与 app.services.embedding_providers
 * [OUTPUT]: 验证确定性哈希 provider、OpenAI-compatible HTTP provider、环境选择与配置画像
 * [POS]: tests 的 RAG provider 边界证明文件，锁住生产 embedding 配置与确定性测试隔离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json

import pytest

from app.services import embedding_providers as providers


def test_deterministic_hash_embedding_provider_is_stable_and_normalized():
    provider = providers.DeterministicHashEmbeddingProvider(dimensions=8)

    first = provider.embed(["MOQ payment certification"])[0]
    second = provider.embed(["MOQ payment certification"])[0]

    assert first == second
    assert len(first) == 8
    assert pytest.approx(sum(value * value for value in first), rel=1e-6) == 1.0


def test_openai_compatible_embedding_provider_builds_request_and_normalizes(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": [
                        {"index": 1, "embedding": [0, 6, 8]},
                        {"index": 0, "embedding": [3, 4, 0]},
                    ]
                }
            ).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(providers, "urlopen", fake_urlopen)

    provider = providers.OpenAICompatibleEmbeddingProvider(
        endpoint="https://embeddings.example/v1/embeddings",
        api_key="test-key",
        model="embed-small",
        dimensions=3,
        timeout_seconds=2.5,
    )
    result = provider.embed(["first", "second"])

    request, timeout = requests[0]
    assert timeout == 2.5
    assert request.full_url == "https://embeddings.example/v1/embeddings"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert json.loads(request.data.decode()) == {"model": "embed-small", "input": ["first", "second"], "dimensions": 3}
    assert result[0] == [0.6, 0.8, 0.0]
    assert result[1] == [0.0, 0.6, 0.8]


def test_get_embedding_provider_defaults_to_deterministic_hash():
    provider = providers.get_embedding_provider({})

    assert isinstance(provider, providers.DeterministicHashEmbeddingProvider)
    assert provider.dimensions == 1536


def test_get_embedding_provider_requires_key_for_openai():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        providers.get_embedding_provider({"CLOSER_EMBEDDING_PROVIDER": "openai"})


def test_get_embedding_provider_config_reports_production_provider():
    config = providers.get_embedding_provider_config(
        {
            "CLOSER_EMBEDDING_PROVIDER": "openai",
            "CLOSER_EMBEDDING_MODEL": "text-embedding-3-small",
            "OPENAI_API_KEY": "secret",
        }
    )

    assert config.status == "ok"
    assert config.details()["provider"] == "openai"
    assert config.details()["api_key_env"] == "OPENAI_API_KEY"


def test_get_embedding_provider_config_warns_on_deterministic_default():
    config = providers.get_embedding_provider_config({})

    assert config.status == "warning"
    assert config.details()["provider"] == "deterministic"
