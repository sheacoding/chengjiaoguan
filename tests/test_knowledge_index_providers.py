"""
/* ========================================================================== */
/* GEB L3: 知识索引 Provider 测试                                             */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 json、pytest monkeypatch、SQLite 会话夹具、knowledge 服务与 knowledge index provider boundary
 * [OUTPUT]: 验证 disabled/http 知识索引 provider、入库 upsert 同步与配置画像
 * [POS]: tests 的 RAG 索引同步证明文件，锁住本地知识入库与托管语义索引 upsert 的隔离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json

from app import models
from app.services.knowledge import ingest_knowledge
from app.services.knowledge_index_providers import (
    DisabledKnowledgeIndexProvider,
    HttpKnowledgeIndexProvider,
    get_knowledge_index_provider_config,
)


def test_disabled_knowledge_index_provider_skips_upsert():
    provider = DisabledKnowledgeIndexProvider()

    assert provider.upsert([]) == {"status": "skipped", "provider": "disabled", "indexed": 0}


def test_http_knowledge_index_provider_posts_chunks(monkeypatch, db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    chunk = models.KnowledgeChunk(
        seller_id=1,
        source_type="faq",
        source_ref="payment",
        content="Payment requires a 30% deposit.",
        embedding=[1.0, 0.0],
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
            return json.dumps({"status": "ok", "indexed": 1}).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.services.knowledge_index_providers.urlopen", fake_urlopen)

    provider = HttpKnowledgeIndexProvider(
        endpoint="https://vector.example/upsert",
        auth_token="token-123",
        timeout_seconds=3.5,
    )
    result = provider.upsert([chunk])

    request, timeout = requests[0]
    payload = json.loads(request.data.decode())
    assert timeout == 3.5
    assert request.full_url == "https://vector.example/upsert"
    assert request.get_header("Authorization") == "Bearer token-123"
    assert payload["operation"] == "upsert"
    assert payload["seller_id"] == 1
    assert payload["items"][0]["chunk_id"] == chunk.id
    assert payload["items"][0]["source_ref"] == "payment"
    assert payload["items"][0]["embedding"] == [1.0, 0.0]
    assert result == {"status": "ok", "provider": "http", "indexed": 1}


def test_ingest_knowledge_syncs_configured_index_provider(db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    synced = []

    class RecordingIndexProvider:
        name = "recording"

        def upsert(self, chunks):
            synced.extend(chunks)
            return {"status": "ok", "provider": self.name, "indexed": len(chunks)}

    chunks = ingest_knowledge(
        db_session,
        1,
        source_type="faq",
        source_ref="payment",
        content="Payment requires a 30% deposit.",
        index_provider=RecordingIndexProvider(),
    )

    audit = db_session.query(models.AuditLog).filter_by(action_type="knowledge_ingested").one()
    assert synced == chunks
    assert audit.snapshot["index_sync"] == {"status": "ok", "provider": "recording", "indexed": 1}


def test_get_knowledge_index_provider_config_reports_default_and_http():
    default_config = get_knowledge_index_provider_config({})
    missing_endpoint = get_knowledge_index_provider_config({"CLOSER_KNOWLEDGE_INDEX_PROVIDER": "http"})
    configured = get_knowledge_index_provider_config(
        {
            "CLOSER_KNOWLEDGE_INDEX_PROVIDER": "managed",
            "CLOSER_KNOWLEDGE_INDEX_ENDPOINT": "https://vector.example/upsert",
            "CLOSER_KNOWLEDGE_INDEX_AUTH_TOKEN": "token-123",
        }
    )

    assert default_config.status == "warning"
    assert default_config.details()["provider"] == "disabled"
    assert missing_endpoint.status == "failed"
    assert "CLOSER_KNOWLEDGE_INDEX_ENDPOINT" in missing_endpoint.message
    assert configured.status == "ok"
    assert configured.details()["provider"] == "http"
    assert configured.details()["auth_token_configured"] is True
