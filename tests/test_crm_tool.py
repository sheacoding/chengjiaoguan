"""
/* ========================================================================== */
/* GEB L3: CRM 工具测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest、SQLite 会话夹具、agent_tools、schemas 与 channel_gateway
 * [OUTPUT]: 验证 get_customer 工具可按询盘或客户返回租户 scoped CRM 画像
 * [POS]: tests 的 CRM 工具证明文件，锁住 Agent 门面到客户画像服务的契约
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import pytest

from app import agent_tools, models
from app.schemas import ChannelContact, InboundMessage
from app.services.channel_gateway import ingest_inbound_message


def test_get_customer_tool_returns_profile_by_inquiry(db_session):
    inbound = InboundMessage(
        channel="site_form",
        channel_message_id="crm-001",
        from_=ChannelContact(
            name="Jane Buyer",
            company="ACME Trading",
            country="US",
            email="jane@acme-trading.com",
        ),
        content="Need 5000 LED desk lamps to US.",
    )
    inquiry, _, _, _ = ingest_inbound_message(db_session, 1, inbound)

    profile = agent_tools.get_customer(db_session, 1, inquiry_id=inquiry.id)

    assert profile["company"] == "ACME Trading"
    assert profile["email"] == "jane@acme-trading.com"
    assert profile["channels"]["email"] == "jane@acme-trading.com"


def test_customer_profile_is_tenant_scoped(db_session):
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add(customer)
    db_session.flush()

    with pytest.raises(LookupError):
        agent_tools.get_customer(db_session, 2, customer_id=customer.id)


def test_customer_channels_are_merged_across_inbound_messages(db_session):
    site_message = InboundMessage(
        channel="site_form",
        channel_message_id="crm-site",
        from_=ChannelContact(email="buyer@example.com"),
        content="Need lamps.",
    )
    whatsapp_message = InboundMessage(
        channel="whatsapp",
        channel_message_id="crm-wa",
        from_=ChannelContact(email="buyer@example.com", phone="15551234567"),
        content="Need 2000 LED desk lamps.",
    )

    first_inquiry, _, _, _ = ingest_inbound_message(db_session, 1, site_message)
    second_inquiry, _, _, _ = ingest_inbound_message(db_session, 1, whatsapp_message)

    assert first_inquiry.customer_id == second_inquiry.customer_id
    profile = agent_tools.get_customer(db_session, 1, customer_id=first_inquiry.customer_id)
    assert profile["channels"]["email"] == "buyer@example.com"
    assert profile["channels"]["phone"] == "15551234567"
    assert profile["channels"]["whatsapp"] == "15551234567"
