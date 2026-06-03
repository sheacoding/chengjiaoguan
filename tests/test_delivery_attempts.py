"""
/* ========================================================================== */
/* GEB L3: 投递重试测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest monkeypatch、SQLite 会话夹具、app.agent_tools、app.models 与 delivery_attempts 服务
 * [OUTPUT]: 验证 failed delivery_attempt 可被 due retry worker 重试，成功清除 next_retry_at，失败重新排期
 * [POS]: tests 的投递状态机证明文件，锁住出站失败从候选查询到重试执行的闭环
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import agent_tools, models
from app.services.delivery_attempts import run_due_delivery_retries


def _seed_email_conversation(db_session):
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
    return conversation


def test_due_delivery_retry_updates_failed_attempt_to_queued(db_session, monkeypatch):
    monkeypatch.setenv("CLOSER_DELIVERY_MODE", "live")
    conversation = _seed_email_conversation(db_session)
    sent = agent_tools.send_message(db_session, 1, conversation.id, "Thanks for your inquiry.")
    attempt = db_session.get(models.DeliveryAttempt, sent["delivery"]["delivery_attempt_id"])

    monkeypatch.delenv("CLOSER_DELIVERY_MODE", raising=False)
    results = run_due_delivery_retries(db_session, 1, now=attempt.next_retry_at)

    assert len(results) == 1
    assert results[0]["status"] == "queued"
    assert results[0]["attempt_count"] == 2
    assert attempt.status == "queued"
    assert attempt.next_retry_at is None
    assert attempt.client == "payload_only"


def test_due_delivery_retry_keeps_failed_attempt_retryable(db_session, monkeypatch):
    monkeypatch.setenv("CLOSER_DELIVERY_MODE", "live")
    conversation = _seed_email_conversation(db_session)
    sent = agent_tools.send_message(db_session, 1, conversation.id, "Thanks for your inquiry.")
    attempt = db_session.get(models.DeliveryAttempt, sent["delivery"]["delivery_attempt_id"])
    first_retry_at = attempt.next_retry_at

    results = run_due_delivery_retries(db_session, 1, now=first_retry_at)

    assert results[0]["status"] == "failed"
    assert results[0]["attempt_count"] == 2
    assert "host credential is required" in results[0]["error"]
    assert attempt.status == "failed"
    assert attempt.next_retry_at is not None
    assert attempt.next_retry_at != first_retry_at
