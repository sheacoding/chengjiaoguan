"""
/* ========================================================================== */
/* GEB L3: 出站消息工具测试                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest、Decimal、SQLite 会话夹具、app.agent_tools 与 app.models
 * [OUTPUT]: 验证 send_message 安全发送、email/WhatsApp payload-only 客户端状态、delivery_attempt 记录、失败重试候选、护栏审批与租户隔离
 * [POS]: tests 的出站消息工具证明文件，锁住 Agent 工具到 channel_delivery 的安全发送路径
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from decimal import Decimal

import pytest

from app import agent_tools, models
from app.services.delivery_attempts import list_retryable_delivery_attempts
from app.services.seller_settings import AI_DISCLOSURE_TEXT


def _seed_conversation(db_session, *, takeover: bool = False, channel: str = "email", phone: str | None = None):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(seller_id=1, email="buyer@example.com", phone=phone, status="active")
    db_session.add_all([seller, customer])
    db_session.flush()
    inquiry = models.Inquiry(seller_id=1, customer_id=customer.id, raw_content="Need 500 lamps", status="new")
    db_session.add(inquiry)
    db_session.flush()
    conversation = models.Conversation(
        seller_id=1,
        customer_id=customer.id,
        inquiry_id=inquiry.id,
        channel=channel,
        language="en",
        is_human_takeover=takeover,
    )
    db_session.add(conversation)
    db_session.flush()
    return inquiry, conversation


def test_send_message_creates_ai_message_when_safe(db_session):
    _, conversation = _seed_conversation(db_session)

    result = agent_tools.send_message(
        db_session,
        1,
        conversation.id,
        "Thanks for your inquiry. We will confirm the exact lead time shortly.",
    )

    assert result["status"] == "sent"
    assert result["delivery"]["status"] == "queued"
    assert result["delivery"]["channel"] == "email"
    assert result["delivery"]["client"]["client"] == "payload_only"
    assert result["delivery"]["payload"]["to"] == "buyer@example.com"
    message = db_session.get(models.Message, result["message_id"])
    attempt = db_session.get(models.DeliveryAttempt, result["delivery"]["delivery_attempt_id"])
    assert message.sender_role == "ai"
    assert message.content.startswith("Thanks for your inquiry")
    assert message.content.endswith(AI_DISCLOSURE_TEXT)
    assert message.channel_message_id == f"closer:email:out:{message.id}"
    assert attempt.message_id == message.id
    assert attempt.status == "queued"
    assert attempt.client == "payload_only"


def test_send_message_builds_whatsapp_delivery_payload(db_session):
    _, conversation = _seed_conversation(db_session, channel="whatsapp", phone="+15550001111")

    result = agent_tools.send_message(db_session, 1, conversation.id, "Thanks, we can help.")

    assert result["status"] == "sent"
    assert result["delivery"]["status"] == "queued"
    assert result["delivery"]["channel"] == "whatsapp"
    assert result["delivery"]["client"]["client"] == "payload_only"
    assert result["delivery"]["payload"]["to"] == "+15550001111"
    assert result["delivery"]["payload"]["text"]["body"].startswith("Thanks, we can help.")
    assert result["delivery"]["payload"]["text"]["body"].endswith(AI_DISCLOSURE_TEXT)


def test_send_message_live_delivery_failure_records_retryable_attempt(db_session, monkeypatch):
    monkeypatch.setenv("CLOSER_DELIVERY_MODE", "live")
    _, conversation = _seed_conversation(db_session)

    result = agent_tools.send_message(db_session, 1, conversation.id, "Thanks for your inquiry.")

    attempt = db_session.get(models.DeliveryAttempt, result["delivery"]["delivery_attempt_id"])
    retryable = list_retryable_delivery_attempts(db_session, 1, now=attempt.next_retry_at)
    assert result["delivery"]["status"] == "failed"
    assert "host credential is required" in result["delivery"]["client"]["error"]
    assert attempt.status == "failed"
    assert attempt.next_retry_at is not None
    assert retryable == [attempt]


def test_send_message_below_floor_creates_pending_approval(db_session):
    inquiry, conversation = _seed_conversation(db_session)
    db_session.add(
        models.PricingRule(
            seller_id=1,
            product_id=None,
            floor_price=Decimal("3.00"),
            currency="USD",
        )
    )

    result = agent_tools.send_message(db_session, 1, conversation.id, "We can offer USD 2.80 per unit.")

    assert result["status"] == "pending_approval"
    assert result["reason"] == "below_floor_price"
    approval = db_session.get(models.Approval, result["approval_id"])
    assert approval.type == "message_send"
    assert approval.payload["content"].startswith("We can offer")
    assert db_session.get(models.Conversation, conversation.id).is_human_takeover is True
    assert db_session.get(models.Inquiry, inquiry.id).status == "pending_approval"
    assert db_session.query(models.Message).count() == 0


def test_send_message_sensitive_commitment_creates_pending_approval(db_session):
    _, conversation = _seed_conversation(db_session)

    result = agent_tools.send_message(
        db_session,
        1,
        conversation.id,
        "We guarantee delivery and can sign the contract today.",
    )

    assert result["status"] == "pending_approval"
    assert result["reason"] == "sensitive_commitment"


def test_send_message_is_tenant_scoped(db_session):
    _, conversation = _seed_conversation(db_session)

    with pytest.raises(LookupError):
        agent_tools.send_message(db_session, 2, conversation.id, "Hello")
