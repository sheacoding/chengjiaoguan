"""
/* ========================================================================== */
/* GEB L3: 通知 API 测试                                                      */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI TestClient、SQLite 会话夹具、app.models、agent_tools、notifications 服务与 channel_gateway
 * [OUTPUT]: 验证 notifications API 列表/标记、审批请求自动通知、审批解决后通知已读与租户隔离
 * [POS]: tests 的通知资源契约证明文件，锁住前端工作台未读提醒需要的后端资源面
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import agent_tools, models
from app.schemas import ChannelContact, InboundMessage
from app.services.channel_gateway import ingest_inbound_message
from app.services.notifications import create_notification


def test_notifications_api_lists_and_marks_status(client, db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    notification = create_notification(
        db_session,
        1,
        type="ops_alert",
        severity="warning",
        title="Delivery failed",
        body="One delivery attempt needs retry.",
        target_type="delivery_attempt",
        target_id=42,
        context={"status": "failed"},
    )
    db_session.commit()

    listed = client.get("/api/v1/notifications", params={"status": "unread"})
    patched = client.patch(f"/api/v1/notifications/{notification.id}", json={"status": "read"})
    cross_tenant = client.patch(
        f"/api/v1/notifications/{notification.id}",
        headers={"Authorization": "Bearer seller:2"},
        json={"status": "archived"},
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["title"] == "Delivery failed"
    assert patched.status_code == 200
    assert patched.json()["status"] == "read"
    assert patched.json()["read_at"] is not None
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["code"] == "notification_not_found"


def test_approval_request_creates_and_resolves_notification(client, db_session):
    inbound = InboundMessage(
        channel="site_form",
        channel_message_id="notification-approval-001",
        from_=ChannelContact(email="buyer@example.com"),
        content="Need 5000 LED desk lamps.",
        language="en",
    )
    inquiry, conversation, _, _ = ingest_inbound_message(db_session, 1, inbound)
    db_session.add(models.PricingRule(seller_id=1, floor_price="3.00", currency="USD"))
    db_session.commit()

    pending = agent_tools.send_message(db_session, 1, conversation.id, "We can offer USD 2.80 per unit.")
    db_session.commit()
    unread = client.get("/api/v1/notifications", params={"status": "unread"})
    rejected = client.post(f"/api/v1/approvals/{pending['approval_id']}/reject", json={"reason": "Too cheap"})
    unread_after_reject = client.get("/api/v1/notifications", params={"status": "unread"})
    read_after_reject = client.get("/api/v1/notifications", params={"status": "read"})

    assert unread.status_code == 200
    assert unread.json()["total"] == 1
    item = unread.json()["items"][0]
    assert item["type"] == "approval_requested"
    assert item["severity"] == "warning"
    assert item["target_type"] == "approval"
    assert item["target_id"] == pending["approval_id"]
    assert item["context"]["inquiry_id"] == inquiry.id
    assert rejected.status_code == 200
    assert unread_after_reject.json()["total"] == 0
    assert read_after_reject.json()["total"] == 1
