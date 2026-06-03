"""
/* ========================================================================== */
/* GEB L3: 生产就绪诊断测试                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest monkeypatch/tmp_path、SQLite 会话夹具、FastAPI TestClient、app.models 与 readiness 服务
 * [OUTPUT]: 验证 readiness 可报告 API key、agent、embedding、渠道、汇率等生产配置 ready/degraded/unready，并通过 /ops/readiness 暴露租户 scoped 画像
 * [POS]: tests 的运维画像证明文件，锁住生产配置缺口在运行前可见
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import date, timedelta

from app import models
from app.services.credentials import seal_credentials
from app.services.readiness import get_readiness


def _seed_seller(db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    db_session.add(seller)
    db_session.flush()
    return seller


def test_readiness_reports_ready_for_live_configuration(db_session, monkeypatch, tmp_path):
    _seed_seller(db_session)
    monkeypatch.setenv("CLOSER_AGENT_MODEL", "openai:gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CLOSER_GRAPH_DECISION_PROVIDER", "openai")
    monkeypatch.setenv("CLOSER_GRAPH_DECISION_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("CLOSER_GRAPH_DECISION_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("CLOSER_KNOWLEDGE_SEARCH_PROVIDER", "http")
    monkeypatch.setenv("CLOSER_KNOWLEDGE_SEARCH_ENDPOINT", "https://vector.example/search")
    monkeypatch.setenv("CLOSER_KNOWLEDGE_SEARCH_AUTH_TOKEN", "token-456")
    monkeypatch.setenv("CLOSER_KNOWLEDGE_INDEX_PROVIDER", "http")
    monkeypatch.setenv("CLOSER_KNOWLEDGE_INDEX_ENDPOINT", "https://vector.example/upsert")
    monkeypatch.setenv("CLOSER_KNOWLEDGE_INDEX_AUTH_TOKEN", "token-789")
    monkeypatch.setenv("CLOSER_OPS_MONITOR_PROVIDER", "http")
    monkeypatch.setenv("CLOSER_OPS_MONITOR_ENDPOINT", "https://monitor.example/events")
    monkeypatch.setenv("CLOSER_OPS_MONITOR_AUTH_TOKEN", "monitor-token")
    monkeypatch.setenv("CLOSER_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("CLOSER_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("CLOSER_EXCHANGE_RATE_PROVIDER", "http")
    monkeypatch.setenv("CLOSER_EXCHANGE_RATE_SOURCE", "ecb")
    monkeypatch.setenv("CLOSER_EXCHANGE_RATE_ENDPOINT", "https://rates.example/{base}?symbols={symbols}")
    monkeypatch.setenv("CLOSER_EXCHANGE_RATE_AUTH_TOKEN", "rate-token")
    monkeypatch.setenv("CLOSER_DELIVERY_MODE", "live")
    monkeypatch.setenv("CLOSER_CREDENTIALS_SECRET", "production-secret")
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_BACKEND", "http")
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_ENDPOINT", "https://storage.example/files/{key}")
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_AUTH_TOKEN", "token-123")
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_DIR", str(tmp_path))
    db_session.add_all(
        [
            models.SellerApiKey(
                seller_id=1,
                name="Production API key",
                token_prefix="cak_prod_ready",
                token_hash="ready-hash",
                status="active",
            ),
            models.ChannelAccount(
                seller_id=1,
                channel_type="email",
                name="Sales inbox",
                credentials=seal_credentials({
                    "host": "mail.example.com",
                    "username": "sales",
                    "password": "secret",
                    "poll_enabled": True,
                }),
                status="connected",
            ),
            models.ChannelAccount(
                seller_id=1,
                channel_type="whatsapp",
                name="WhatsApp",
                credentials=seal_credentials({"access_token": "token", "phone_number_id": "phone-id"}),
                status="connected",
            ),
            models.PricingRule(
                seller_id=1,
                floor_price=10,
                currency="USD",
                exchange_source="ecb",
                logistics_template={"exchange_rate_provider": {"endpoint": "https://rates.example/{base}"}},
            ),
        ]
    )

    result = get_readiness(db_session, 1)

    assert result["status"] == "ready"
    assert result["summary"]["failed"] == 0
    assert result["summary"]["warning"] == 0
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["api_keys"]["status"] == "ok"
    assert checks["graph_decision"]["status"] == "ok"
    assert checks["knowledge_search"]["status"] == "ok"
    assert checks["graph_decision"]["details"]["provider"] == "openai"
    assert checks["graph_decision"]["details"]["model"] == "gpt-4o-mini"
    assert checks["graph_decision"]["details"]["api_key_configured"] is True
    assert checks["knowledge_index"]["status"] == "ok"
    assert checks["knowledge_index"]["details"]["endpoint"] == "https://vector.example/upsert"
    assert checks["exchange_rate_provider"]["status"] == "ok"
    assert checks["exchange_rate_provider"]["details"]["endpoint"] == "https://rates.example/{base}?symbols={symbols}"
    assert checks["monitoring_sink"]["status"] == "ok"
    assert checks["monitoring_sink"]["details"]["endpoint"] == "https://monitor.example/events"
    assert checks["document_storage"]["status"] == "ok"
    assert checks["document_storage"]["details"]["backend"] == "http"


def test_readiness_warns_when_channel_credentials_need_rotation(db_session, monkeypatch):
    _seed_seller(db_session)
    monkeypatch.setenv("CLOSER_CREDENTIALS_SECRET", "old-secret")
    db_session.add(
        models.ChannelAccount(
            seller_id=1,
            channel_type="email",
            name="Sales inbox",
            credentials=seal_credentials({"host": "mail.example.com", "username": "sales", "password": "secret"}),
            status="connected",
        )
    )
    db_session.flush()
    monkeypatch.setenv("CLOSER_CREDENTIALS_SECRET", "new-secret")
    monkeypatch.setenv("CLOSER_CREDENTIALS_PREVIOUS_SECRETS", "old-secret")

    result = get_readiness(db_session, 1)
    checks = {check["name"]: check for check in result["checks"]}

    assert checks["channels"]["status"] == "warning"
    assert checks["channels"]["details"]["channels"][0]["credentials_key_status"] == "legacy"
    assert checks["channels"]["details"]["channels"][0]["message"] == "Credential seal rotation is pending"


def test_readiness_surfaces_default_and_missing_production_config(db_session, monkeypatch):
    _seed_seller(db_session)
    monkeypatch.delenv("CLOSER_AGENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLOSER_GRAPH_DECISION_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_GRAPH_DECISION_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_GRAPH_DECISION_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOSER_GRAPH_DECISION_MODEL", raising=False)
    monkeypatch.delenv("CLOSER_GRAPH_DECISION_BASE_URL", raising=False)
    monkeypatch.delenv("CLOSER_GRAPH_DECISION_API_KEY_ENV", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_SEARCH_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_INDEX_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_INDEX_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_INDEX_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOSER_OPS_MONITOR_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_OPS_MONITOR_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_OPS_MONITOR_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOSER_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("CLOSER_EXCHANGE_RATE_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_EXCHANGE_RATE_SOURCE", raising=False)
    monkeypatch.delenv("CLOSER_EXCHANGE_RATE_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_EXCHANGE_RATE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOSER_DELIVERY_MODE", raising=False)
    monkeypatch.delenv("CLOSER_CREDENTIALS_SECRET", raising=False)
    monkeypatch.delenv("CLOSER_DOCUMENT_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("CLOSER_DOCUMENT_STORAGE_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_DOCUMENT_STORAGE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOSER_DOCUMENT_STORAGE_DIR", raising=False)
    db_session.add_all(
        [
            models.ChannelAccount(
                seller_id=1,
                channel_type="email",
                name="Sales inbox",
                credentials={"poll_enabled": True},
                status="connected",
            ),
            models.PricingRule(
                seller_id=1,
                floor_price=10,
                currency="EUR",
                exchange_source="ecb",
                logistics_template={},
            ),
        ]
    )

    result = get_readiness(db_session, 1)
    checks = {check["name"]: check for check in result["checks"]}

    assert result["status"] == "unready"
    assert checks["api_keys"]["status"] == "warning"
    assert checks["agent_model"]["status"] == "warning"
    assert checks["graph_decision"]["status"] == "warning"
    assert checks["knowledge_search"]["status"] == "warning"
    assert checks["knowledge_index"]["status"] == "warning"
    assert checks["embedding_provider"]["status"] == "warning"
    assert checks["exchange_rate_provider"]["status"] == "warning"
    assert checks["monitoring_sink"]["status"] == "warning"
    assert checks["credentials_secret"]["status"] == "warning"
    assert checks["delivery_mode"]["status"] == "warning"
    assert checks["document_storage"]["status"] == "warning"
    assert checks["document_storage"]["details"]["backend"] == "local"
    assert checks["channels"]["status"] == "failed"
    assert checks["exchange_rates"]["status"] == "warning"


def test_readiness_warns_on_expired_cache_and_failed_delivery(db_session, monkeypatch):
    monkeypatch.delenv("CLOSER_AGENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _seed_seller(db_session)
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add(customer)
    db_session.flush()
    inquiry = models.Inquiry(seller_id=1, customer_id=customer.id, raw_content="Need lamps", status="new")
    db_session.add(inquiry)
    db_session.flush()
    conversation = models.Conversation(seller_id=1, customer_id=customer.id, inquiry_id=inquiry.id, channel="email")
    message = models.Message(conversation_id=1, sender_role="ai", content="Hello")
    db_session.add_all([conversation, message])
    db_session.flush()
    db_session.add_all(
        [
            models.PricingRule(
                seller_id=1,
                floor_price=10,
                currency="EUR",
                exchange_source="ecb",
                logistics_template={
                    "exchange_rate_cache": {
                        "confirmed": True,
                        "expires_at": (date.today() - timedelta(days=1)).isoformat(),
                        "rates": {"USD": {"EUR": "0.9"}},
                    }
                },
            ),
            models.DeliveryAttempt(
                seller_id=1,
                message_id=message.id,
                channel="email",
                external_id="closer:email:out:1",
                status="failed",
                payload={},
                response={},
            ),
        ]
    )

    result = get_readiness(db_session, 1)
    checks = {check["name"]: check for check in result["checks"]}

    assert result["status"] == "degraded"
    assert checks["exchange_rates"]["status"] == "warning"
    assert checks["failed_delivery_attempts"]["status"] == "warning"


def test_readiness_endpoint_is_tenant_scoped(client, db_session):
    _seed_seller(db_session)

    response = client.get("/api/v1/ops/readiness", headers={"Authorization": "Bearer seller:2"})

    assert response.status_code == 200
    assert response.json()["status"] == "unready"
    assert response.json()["seller_id"] == 2
    assert response.json()["checks"][0]["name"] == "seller"
