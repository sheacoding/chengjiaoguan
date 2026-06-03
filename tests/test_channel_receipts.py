"""
/* ========================================================================== */
/* GEB L3: 渠道投递回执测试                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLite 会话夹具、FastAPI TestClient、app.models 与 channel_receipts 服务
 * [OUTPUT]: 验证 WhatsApp/generic 回执可同步 delivery_attempt 状态、追加 response.receipts 并保持租户隔离
 * [POS]: tests 的出站回执证明文件，锁住外部渠道状态回声到投递记录的闭环
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import models
from app.services.channel_receipts import sync_channel_receipts


def _seed_attempt(db_session, *, channel_type: str = "whatsapp", provider_id: str = "wamid.out.001"):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add_all([seller, customer])
    db_session.flush()
    inquiry = models.Inquiry(seller_id=1, customer_id=customer.id, raw_content="Need lamps", status="new")
    db_session.add(inquiry)
    db_session.flush()
    conversation = models.Conversation(
        seller_id=1,
        customer_id=customer.id,
        inquiry_id=inquiry.id,
        channel=channel_type,
    )
    channel = models.ChannelAccount(
        seller_id=1,
        channel_type=channel_type,
        name="Outbound channel",
        credentials={},
        status="connected",
    )
    db_session.add_all([conversation, channel])
    db_session.flush()
    message = models.Message(
        conversation_id=conversation.id,
        sender_role="ai",
        channel_message_id=f"closer:{channel_type}:out:1",
        content="Thanks.",
    )
    db_session.add(message)
    db_session.flush()
    attempt = models.DeliveryAttempt(
        seller_id=1,
        message_id=message.id,
        channel_account_id=channel.id,
        channel=channel_type,
        external_id=message.channel_message_id,
        status="sent",
        client=f"{channel_type}_client",
        provider_message_id=provider_id,
        payload={},
        response={"provider_message_id": provider_id},
    )
    db_session.add(attempt)
    db_session.flush()
    return channel, attempt


def test_sync_whatsapp_delivery_receipts_updates_attempt_status(db_session):
    channel, attempt = _seed_attempt(db_session)
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {"id": "wamid.out.001", "status": "delivered", "timestamp": "1780379521"}
                            ]
                        }
                    }
                ]
            }
        ]
    }

    result = sync_channel_receipts(db_session, 1, channel.id, payload)

    assert result["matched"] == 1
    assert result["items"][0]["delivery_attempt_id"] == attempt.id
    assert db_session.get(models.DeliveryAttempt, attempt.id).status == "delivered"
    assert db_session.get(models.DeliveryAttempt, attempt.id).response["receipts"][0]["raw_status"] == "delivered"


def test_failed_receipt_makes_attempt_retryable(db_session):
    channel, attempt = _seed_attempt(db_session)
    payload = {
        "statuses": [
            {
                "id": "wamid.out.001",
                "status": "failed",
                "errors": [{"message": "Recipient is unreachable"}],
            }
        ]
    }

    result = sync_channel_receipts(db_session, 1, channel.id, payload)
    stored = db_session.get(models.DeliveryAttempt, attempt.id)

    assert result["matched"] == 1
    assert stored.status == "failed"
    assert stored.error == "Recipient is unreachable"
    assert stored.next_retry_at is not None


def test_generic_email_receipt_matches_external_id(client, db_session):
    channel, attempt = _seed_attempt(db_session, channel_type="email", provider_id="")
    payload = {
        "receipts": [
            {
                "external_id": "closer:email:out:1",
                "status": "bounced",
                "reason": "Mailbox unavailable",
            }
        ]
    }

    response = client.post(f"/api/v1/channels/{channel.id}/sync-receipts", json=payload)

    assert response.status_code == 200
    assert response.json()["matched"] == 1
    stored = db_session.get(models.DeliveryAttempt, attempt.id)
    assert stored.status == "failed"
    assert stored.error == "Mailbox unavailable"


def test_sync_receipts_is_tenant_scoped(client, db_session):
    channel, _ = _seed_attempt(db_session)

    response = client.post(
        f"/api/v1/channels/{channel.id}/sync-receipts",
        headers={"Authorization": "Bearer seller:2"},
        json={"statuses": [{"id": "wamid.out.001", "status": "delivered"}]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "channel_not_found"
