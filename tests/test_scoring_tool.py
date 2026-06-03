"""
/* ========================================================================== */
/* GEB L3: 询盘打分测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLite 会话夹具、agent_tools、models、schemas 与 channel_gateway
 * [OUTPUT]: 验证 score_inquiry 输出 A/B/C grade、score 与 explainable signals
 * [POS]: tests 的 scoring 工具证明文件，锁住询盘优先级判断规则
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import agent_tools, models
from app.services.channel_gateway import ingest_inbound_message
from app.schemas import ChannelContact, InboundMessage


def _ingest(db_session, content, email="buyer@acme-trading.com", company="ACME Trading"):
    inbound = InboundMessage(
        channel="site_form",
        channel_message_id=f"msg-{abs(hash(content))}",
        from_=ChannelContact(email=email, company=company, country="US"),
        content=content,
        language="en",
    )
    inquiry, _, _, _ = ingest_inbound_message(db_session, 1, inbound)
    db_session.flush()
    return inquiry


def test_score_inquiry_marks_specific_corporate_request_as_a(db_session):
    inquiry = _ingest(db_session, "We need 5000 LED desk lamps shipped to US. Please quote FOB.")

    result = agent_tools.score_inquiry(db_session, 1, inquiry.id)
    db_session.commit()

    assert result["grade"] == "A"
    assert result["score"] >= 75
    assert {"real_company", "verified_domain", "specific_quantity", "specific_product"}.issubset(result["signals"])
    assert db_session.get(models.Inquiry, inquiry.id).grade == "A"


def test_score_inquiry_marks_vague_short_message_as_c(db_session):
    inquiry = _ingest(db_session, "price?", email="buyer@gmail.com", company=None)

    result = agent_tools.score_inquiry(db_session, 1, inquiry.id)

    assert result["grade"] == "C"
    assert "too_short" in result["signals"]


def test_score_inquiry_marks_competitor_probe_as_c(db_session):
    inquiry = _ingest(
        db_session,
        "Please send price list only for market research. We are checking competitor benchmark price.",
    )

    result = agent_tools.score_inquiry(db_session, 1, inquiry.id)

    assert result["grade"] == "C"
    assert "possible_competitor" in result["signals"]


def test_get_inquiry_tool_returns_parsed_fields(db_session):
    inquiry = _ingest(db_session, "Need 1000 LED desk lamps to US.")

    result = agent_tools.get_inquiry(db_session, 1, inquiry.id)

    assert result["id"] == inquiry.id
    assert result["parsed"]["quantity"] == 1000
    assert result["language"] == "en"
