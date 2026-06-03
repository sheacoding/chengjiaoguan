"""
/* ========================================================================== */
/* GEB L3: Email 适配器测试                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 app.models、channel_gateway 与 EmailAdapter/OutboundEmail
 * [OUTPUT]: 验证原始邮件解析、SMTP 文本组合与 email 入站幂等落库
 * [POS]: tests 的 email adapter 证明文件，锁住邮件边界的确定性解析和组合
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import models
from app.services.channel_gateway import ingest_inbound_message
from app.services.email_adapter import EmailAdapter, OutboundEmail


def test_email_adapter_normalizes_raw_email():
    raw = """From: Jane Buyer <jane@example.com>
To: sales@example-exporter.com
Subject: Quote request
Message-ID: <msg-001@example.com>
Date: Tue, 02 Jun 2026 03:12:00 +0000

Hello, we need 5000 LED desk lamps for the US market.
"""

    message = EmailAdapter().normalize_raw_email(raw)

    assert message.channel == "email"
    assert message.channel_message_id == "msg-001@example.com"
    assert message.from_.name == "Jane Buyer"
    assert message.from_.email == "jane@example.com"
    assert "5000 LED desk lamps" in message.content
    assert message.received_at is not None


def test_email_adapter_composes_smtp_message():
    outbound = OutboundEmail(
        from_email="sales@example-exporter.com",
        to_email="jane@example.com",
        subject="Re: Quote request",
        body="Thanks for your inquiry. We will send a quote shortly.",
        message_id="closer-001@example-exporter.com",
    )

    message = EmailAdapter().compose_smtp_message(outbound)

    assert message["From"] == "sales@example-exporter.com"
    assert message["To"] == "jane@example.com"
    assert message["Subject"] == "Re: Quote request"
    assert message["Message-ID"] == "<closer-001@example-exporter.com>"
    assert "send a quote" in message.get_content()


def test_normalized_email_can_be_ingested(db_session):
    raw = """From: Buyer <buyer@example.com>
To: sales@example-exporter.com
Subject: Need lamps
Message-ID: <email-ingest-001@example.com>

Need 1200 LED desk lamps to US.
"""
    inbound = EmailAdapter().normalize_raw_email(raw)

    inquiry, conversation, message, duplicate = ingest_inbound_message(db_session, 1, inbound)
    db_session.commit()

    assert duplicate is False
    assert inquiry.source_channel == "email"
    assert inquiry.parsed["quantity"] == 1200
    assert conversation.channel == "email"
    assert message.channel_message_id == "email-ingest-001@example.com"
    assert db_session.get(models.Customer, inquiry.customer_id).email == "buyer@example.com"
