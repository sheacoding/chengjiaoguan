"""
/* ========================================================================== */
/* GEB L3: Email IMAP 轮询测试                                                */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest monkeypatch、SQLite 会话夹具、FastAPI TestClient、app.models 与 email_polling 静态 inbox
 * [OUTPUT]: 验证 email channel 轮询入站落库、幂等重复、acknowledge 与 HTTP poll-email 入口
 * [POS]: tests 的 email 入站轮询证明文件，锁住 IMAP 边界到 channel_gateway 的闭环
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import models
from app.services.email_polling import RawEmailMessage, StaticEmailInboxClient, poll_email_channel


def _raw_email(message_id: str, body: str = "Need 1200 LED desk lamps to US.") -> str:
    return f"""From: Buyer <buyer@example.com>
To: sales@example-exporter.com
Subject: Need lamps
Message-ID: <{message_id}>

{body}
"""


def _seed_email_channel(db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    channel = models.ChannelAccount(
        seller_id=1,
        channel_type="email",
        name="Sales inbox",
        credentials={"host": "imap.example.com", "username": "sales", "password": "secret"},
        status="connected",
    )
    db_session.add_all([seller, channel])
    db_session.flush()
    return channel


def test_poll_email_channel_ingests_unseen_messages_and_acknowledges(db_session):
    channel = _seed_email_channel(db_session)
    inbox = StaticEmailInboxClient([RawEmailMessage(uid="101", raw=_raw_email("email-poll-001@example.com"))])

    result = poll_email_channel(db_session, 1, channel.id, client=inbox)

    assert result["fetched"] == 1
    assert result["ingested"] == 1
    assert result["duplicates"] == 0
    assert inbox.acknowledged == ["101"]
    inquiry = db_session.get(models.Inquiry, result["items"][0]["inquiry_id"])
    message = db_session.get(models.Message, result["items"][0]["message_id"])
    assert inquiry.source_channel == "email"
    assert inquiry.parsed["quantity"] == 1200
    assert message.channel_message_id == "email-poll-001@example.com"


def test_poll_email_channel_is_idempotent_for_existing_message(db_session):
    channel = _seed_email_channel(db_session)
    inbox = StaticEmailInboxClient([RawEmailMessage(uid="101", raw=_raw_email("email-poll-001@example.com"))])

    first = poll_email_channel(db_session, 1, channel.id, client=inbox)
    second = poll_email_channel(db_session, 1, channel.id, client=inbox)

    assert first["ingested"] == 1
    assert second["ingested"] == 0
    assert second["duplicates"] == 1
    assert db_session.query(models.Message).count() == 1


def test_poll_email_channel_endpoint(client, db_session, monkeypatch):
    channel = _seed_email_channel(db_session)

    def fake_poll(session, seller_id, channel_account_id, *, limit=20):
        inbox = StaticEmailInboxClient([RawEmailMessage(uid="201", raw=_raw_email("email-api-001@example.com"))])
        return poll_email_channel(session, seller_id, channel_account_id, client=inbox, limit=limit)

    monkeypatch.setattr("app.routers.channel_operations.poll_email_channel", fake_poll)

    response = client.post(f"/api/v1/channels/{channel.id}/poll-email", params={"limit": 5})

    assert response.status_code == 200
    assert response.json()["fetched"] == 1
    assert response.json()["items"][0]["duplicate"] is False
    assert db_session.get(models.Message, response.json()["items"][0]["message_id"]).channel_message_id == "email-api-001@example.com"


def test_poll_email_channel_is_tenant_scoped(client, db_session):
    channel = _seed_email_channel(db_session)

    response = client.post(
        f"/api/v1/channels/{channel.id}/poll-email",
        headers={"Authorization": "Bearer seller:2"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "channel_not_found"
