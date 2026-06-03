"""
/* ========================================================================== */
/* GEB L3: 投递尝试 API 测试                                                  */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI TestClient、pytest monkeypatch、SQLite 会话夹具、app.agent_tools 与 app.models
 * [OUTPUT]: 验证 delivery-attempts 列表、单条手动 retry、due retry 调度入口与租户隔离
 * [POS]: tests 的出站投递运维 API 证明文件，锁住 delivery_attempt 状态机对 HTTP 层的暴露契约
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import agent_tools, models
from app.database import utcnow


def _seed_failed_attempt(db_session, monkeypatch):
    monkeypatch.setenv("CLOSER_DELIVERY_MODE", "live")
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add_all([seller, customer])
    db_session.flush()
    inquiry = models.Inquiry(seller_id=1, customer_id=customer.id, raw_content="Need 500 lamps", status="new")
    db_session.add(inquiry)
    db_session.flush()
    conversation = models.Conversation(
        seller_id=1,
        customer_id=customer.id,
        inquiry_id=inquiry.id,
        channel="email",
        language="en",
    )
    db_session.add(conversation)
    db_session.flush()
    sent = agent_tools.send_message(db_session, 1, conversation.id, "Thanks for your inquiry.")
    attempt = db_session.get(models.DeliveryAttempt, sent["delivery"]["delivery_attempt_id"])
    db_session.commit()
    return attempt


def test_delivery_attempts_list_and_manual_retry(client, db_session, monkeypatch):
    attempt = _seed_failed_attempt(db_session, monkeypatch)
    monkeypatch.delenv("CLOSER_DELIVERY_MODE", raising=False)

    listed = client.get("/api/v1/delivery-attempts", params={"status": "failed"})
    retried = client.post(f"/api/v1/delivery-attempts/{attempt.id}/retry")

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == attempt.id
    assert listed.json()["items"][0]["status"] == "failed"
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempt_count"] == 2
    assert db_session.get(models.DeliveryAttempt, attempt.id).status == "queued"


def test_delivery_attempts_retry_due_endpoint(client, db_session, monkeypatch):
    attempt = _seed_failed_attempt(db_session, monkeypatch)
    attempt.next_retry_at = utcnow()
    db_session.commit()
    monkeypatch.delenv("CLOSER_DELIVERY_MODE", raising=False)

    retried = client.post("/api/v1/delivery-attempts/retry-due")

    assert retried.status_code == 200
    assert retried.json()["total"] == 1
    assert retried.json()["items"][0]["delivery_attempt_id"] == attempt.id
    assert retried.json()["items"][0]["status"] == "queued"


def test_delivery_attempt_retry_is_tenant_scoped(client, db_session, monkeypatch):
    attempt = _seed_failed_attempt(db_session, monkeypatch)

    response = client.post(
        f"/api/v1/delivery-attempts/{attempt.id}/retry",
        headers={"Authorization": "Bearer seller:2"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "delivery_attempt_not_found"
