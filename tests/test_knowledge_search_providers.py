"""
/* ========================================================================== */
/* GEB L3: 知识检索 Provider 测试                                             */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 json、pytest monkeypatch、SQLite 会话夹具与 knowledge search provider boundary
 * [OUTPUT]: 验证 rule_based 知识检索、HTTP 重排、managed-index 查询 provider 与配置画像
 * [POS]: tests 的知识检索边界证明文件，锁住本地排序、远端重排与托管索引查询的隔离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json

from app import models
from app.services.knowledge_search_providers import (
    HttpKnowledgeSearchProvider,
    ManagedIndexKnowledgeSearchProvider,
    RuleBasedKnowledgeSearchProvider,
    get_knowledge_search_provider_config,
)


def test_rule_based_knowledge_search_provider_ranks_by_cosine(db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    lamp = models.KnowledgeChunk(
        seller_id=1,
        source_type="product",
        source_ref="lamp",
        content="LED desk lamp has CE certification and adjustable brightness.",
        embedding=[1.0, 0.0],
    )
    shipping = models.KnowledgeChunk(
        seller_id=1,
        source_type="faq",
        source_ref="shipping",
        content="Shipping to Germany usually takes 18 days by sea.",
        embedding=[0.2, 1.0],
    )
    db_session.add_all([lamp, shipping])
    db_session.flush()

    provider = RuleBasedKnowledgeSearchProvider()
    results = provider.search("CE certification lamp", [1.0, 0.0], [lamp, shipping], limit=2)

    assert results[0]["source_ref"] == "lamp"
    assert results[0]["score"] >= results[1]["score"]


def test_http_knowledge_search_provider_posts_query_and_parses_results(monkeypatch, db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    chunk = models.KnowledgeChunk(
        seller_id=1,
        source_type="product",
        source_ref="lamp",
        content="LED desk lamp",
        embedding=[1.0, 0.0],
    )

    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({"items": [{"chunk_id": 99, "score": 0.8, "source_ref": "remote"}]}).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.services.knowledge_search_providers.urlopen", fake_urlopen)

    provider = HttpKnowledgeSearchProvider(
        endpoint="https://vector.example/search",
        auth_token="token-123",
        timeout_seconds=2.5,
    )
    results = provider.search("lamp", [1.0, 0.0], [chunk], limit=3)

    request, timeout = requests[0]
    payload = json.loads(request.data.decode())
    assert timeout == 2.5
    assert request.full_url == "https://vector.example/search"
    assert request.get_header("Authorization") == "Bearer token-123"
    assert payload["query"] == "lamp"
    assert payload["limit"] == 3
    assert payload["chunks"][0]["source_ref"] == "lamp"
    assert results[0]["chunk_id"] == 99
    assert results[0]["score"] == 0.8


def test_managed_index_search_posts_scope_without_chunk_payload(monkeypatch, db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    chunk = models.KnowledgeChunk(
        seller_id=1,
        source_type="faq",
        source_ref="shipping",
        content="Shipping to Germany usually takes 18 days by sea.",
        embedding=[0.1, 0.9],
    )
    db_session.add(chunk)
    db_session.flush()
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({"matches": [{"id": chunk.id, "score": 0.93, "source_ref": "shipping"}]}).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.services.knowledge_search_providers.urlopen", fake_urlopen)

    provider = ManagedIndexKnowledgeSearchProvider(
        endpoint="https://vector.example/query",
        auth_token="token-123",
        timeout_seconds=4.0,
    )
    results = provider.search("shipping Germany", [0.1, 0.9], [chunk], limit=5)

    request, timeout = requests[0]
    payload = json.loads(request.data.decode())
    assert timeout == 4.0
    assert request.full_url == "https://vector.example/query"
    assert request.get_header("Authorization") == "Bearer token-123"
    assert payload["query"] == "shipping Germany"
    assert payload["filter"]["seller_id"] == 1
    assert payload["filter"]["chunk_ids"] == [chunk.id]
    assert "chunks" not in payload
    assert results[0]["chunk_id"] == chunk.id
    assert results[0]["score"] == 0.93


def test_get_knowledge_search_provider_config_reports_default_and_http(monkeypatch):
    monkeypatch.delenv("CLOSER_KNOWLEDGE_SEARCH_PROVIDER", raising=False)
    default_config = get_knowledge_search_provider_config()

    monkeypatch.setenv("CLOSER_KNOWLEDGE_SEARCH_PROVIDER", "http")
    monkeypatch.setenv("CLOSER_KNOWLEDGE_SEARCH_ENDPOINT", "https://vector.example/search")
    monkeypatch.setenv("CLOSER_KNOWLEDGE_SEARCH_AUTH_TOKEN", "token-123")
    http_config = get_knowledge_search_provider_config()

    assert default_config.status == "warning"
    assert default_config.details()["provider"] == "rule_based"
    assert http_config.status == "ok"
    assert http_config.details()["provider"] == "http"
    assert http_config.details()["auth_token_configured"] is True


def test_get_knowledge_search_provider_config_reports_managed_index():
    missing = get_knowledge_search_provider_config({"CLOSER_KNOWLEDGE_SEARCH_PROVIDER": "managed_index"})
    configured = get_knowledge_search_provider_config(
        {
            "CLOSER_KNOWLEDGE_SEARCH_PROVIDER": "managed",
            "CLOSER_KNOWLEDGE_SEARCH_ENDPOINT": "https://vector.example/query",
            "CLOSER_KNOWLEDGE_SEARCH_AUTH_TOKEN": "token-123",
        }
    )

    assert missing.status == "failed"
    assert "CLOSER_KNOWLEDGE_SEARCH_ENDPOINT" in missing.message
    assert configured.status == "ok"
    assert configured.details()["provider"] == "managed_index"
    assert configured.details()["endpoint"] == "https://vector.example/query"
