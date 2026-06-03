"""
/* ========================================================================== */
/* GEB L3: 客户档案 API 测试                                                  */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI TestClient、SQLite 会话夹具、app.models、agent_tools 与 channel_gateway
 * [OUTPUT]: 验证 customers API 可列表筛选、详情聚合、修改档案、GDPR 擦除、记录审计并保持租户隔离
 * [POS]: tests 的 CRM HTTP 契约证明文件，锁住前端客户页和会话档案抽屉需要的后端资源面
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import date, timedelta

from app import agent_tools, models
from app.database import utcnow
from app.schemas import ChannelContact, InboundMessage
from app.services.channel_gateway import ingest_inbound_message
from app.services.notifications import create_notification


def _seed_customer_flow(db_session):
    inbound = InboundMessage(
        channel="site_form",
        channel_message_id="customer-api-001",
        from_=ChannelContact(
            name="Jane Buyer",
            company="ACME Trading",
            country="US",
            email="jane@acme.example",
            phone="+15551234567",
        ),
        content="Need 5000 LED desk lamps to US.",
        language="en",
    )
    inquiry, conversation, _, _ = ingest_inbound_message(db_session, 1, inbound)
    customer = db_session.get(models.Customer, inquiry.customer_id)
    inquiry.grade = "A"
    inquiry.score = 88
    customer.grade = "A"
    product = models.Product(seller_id=1, name="LED Desk Lamp", sku="LAMP-10W", status="active")
    db_session.add(product)
    db_session.flush()
    quotation = models.Quotation(
        seller_id=1,
        inquiry_id=inquiry.id,
        customer_id=customer.id,
        currency="USD",
        total_amount="16250.00",
        valid_until=date(2026, 6, 16),
        status="draft",
        created_by="ai",
    )
    quotation.items.append(
        models.QuotationItem(product_id=product.id, quantity=5000, unit_price="3.25", amount="16250.00")
    )
    db_session.add(quotation)
    db_session.flush()
    agent_tools.create_followup(db_session, 1, inquiry.id, conversation.id, delay_hours=24, max_attempts=2)
    db_session.commit()
    return customer, inquiry, conversation, quotation


def _add_privacy_sensitive_records(db_session, customer, inquiry, conversation):
    message = db_session.query(models.Message).filter_by(conversation_id=conversation.id).one()
    message.attachments = [{"name": "jane-private.pdf", "url": "https://acme.example/private"}]
    attempt = models.DeliveryAttempt(
        seller_id=1,
        message_id=message.id,
        channel="email",
        external_id="jane@acme.example",
        status="failed",
        client="smtp",
        provider_message_id="provider-jane",
        attempt_count=1,
        next_retry_at=utcnow() - timedelta(minutes=1),
        error="private email jane@acme.example bounced",
        payload={"to": "jane@acme.example", "body": "Need 5000 LED desk lamps"},
        response={"error": "ACME private mailbox"},
    )
    approval = models.Approval(
        seller_id=1,
        conversation_id=conversation.id,
        inquiry_id=inquiry.id,
        type="message_send",
        reason="manual_review",
        summary="Email Jane at ACME about 5000 LED desk lamps.",
        suggestion="Use jane@acme.example",
        payload={"customer_email": "jane@acme.example"},
        status="pending",
    )
    old_audit = models.AuditLog(
        seller_id=1,
        actor="human",
        action_type="customer_updated",
        target_type="customer",
        target_id=customer.id,
        is_auto=False,
        snapshot={"email": "jane@acme.example"},
    )
    db_session.add_all([attempt, approval, old_audit])
    db_session.flush()
    notification = create_notification(
        db_session,
        1,
        type="approval_requested",
        severity="warning",
        title="Review Jane at ACME",
        body="Email jane@acme.example before sending quote.",
        target_type="approval",
        target_id=approval.id,
        context={"email": "jane@acme.example"},
    )
    db_session.commit()
    return message, attempt, approval, notification


def test_customers_list_detail_and_patch(client, db_session):
    customer, inquiry, conversation, quotation = _seed_customer_flow(db_session)

    listed = client.get("/api/v1/customers", params={"q": "ACME", "grade": "A"})
    detail = client.get(f"/api/v1/customers/{customer.id}")
    patched = client.patch(
        f"/api/v1/customers/{customer.id}",
        json={
            "preferences": {"incoterm": "FOB", "language": "en"},
            "enrichment": {"website": "https://acme.example"},
            "status": "active",
        },
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["company"] == "ACME Trading"
    assert detail.status_code == 200
    assert detail.json()["inquiries"][0]["id"] == inquiry.id
    assert detail.json()["conversations"][0]["id"] == conversation.id
    assert detail.json()["quotations"][0]["id"] == quotation.id
    assert detail.json()["followups"][0]["status"] == "active"
    assert patched.status_code == 200
    assert patched.json()["preferences"]["incoterm"] == "FOB"
    assert patched.json()["enrichment"]["website"] == "https://acme.example"
    audit = db_session.query(models.AuditLog).filter_by(action_type="customer_updated").one()
    assert audit.target_id == customer.id


def test_delete_customer_erases_customer_graph(client, db_session):
    customer, inquiry, conversation, quotation = _seed_customer_flow(db_session)
    message, attempt, approval, notification = _add_privacy_sensitive_records(db_session, customer, inquiry, conversation)

    response = client.delete(f"/api/v1/customers/{customer.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "erased"
    assert body["erased"]["customer"] == 1
    assert body["erased"]["inquiries"] == 1
    assert body["erased"]["conversations"] == 1
    assert body["erased"]["messages"] == 1
    assert body["erased"]["delivery_attempts"] == 1
    assert body["erased"]["quotations"] == 1
    assert body["erased"]["followups"] == 1
    assert body["erased"]["approvals"] == 1
    assert body["erased"]["notifications"] == 1
    assert body["erased"]["audit_logs"] >= 1

    db_session.expire_all()
    erased_customer = db_session.get(models.Customer, customer.id)
    erased_inquiry = db_session.get(models.Inquiry, inquiry.id)
    erased_conversation = db_session.get(models.Conversation, conversation.id)
    erased_message = db_session.get(models.Message, message.id)
    erased_attempt = db_session.get(models.DeliveryAttempt, attempt.id)
    erased_quote = db_session.get(models.Quotation, quotation.id)
    erased_approval = db_session.get(models.Approval, approval.id)
    erased_notification = db_session.get(models.Notification, notification.id)
    followup = db_session.query(models.FollowupTask).filter_by(inquiry_id=inquiry.id).one()

    assert erased_customer.deleted_at is not None
    assert erased_customer.status == "erased"
    assert erased_customer.email is None
    assert erased_customer.company is None
    assert erased_customer.channels == {}
    assert erased_customer.preferences == {}
    assert erased_inquiry.deleted_at is not None
    assert erased_inquiry.raw_content == "[erased]"
    assert erased_inquiry.parsed == {}
    assert erased_inquiry.grade is None
    assert erased_inquiry.score is None
    assert erased_conversation.status == "erased"
    assert erased_conversation.is_human_takeover is False
    assert erased_message.content == "[erased]"
    assert erased_message.attachments == []
    assert erased_message.channel_message_id == f"erased:{message.id}"
    assert erased_attempt.status == "erased"
    assert erased_attempt.external_id == f"erased:{attempt.id}"
    assert erased_attempt.payload == {"erased": True}
    assert erased_attempt.response == {"erased": True}
    assert erased_attempt.provider_message_id is None
    assert erased_attempt.error is None
    assert erased_attempt.next_retry_at is None
    assert erased_quote.deleted_at is not None
    assert erased_quote.status == "erased"
    assert erased_quote.terms == {"erased": True}
    assert followup.status == "stopped"
    assert followup.stop_reason == "customer_erased"
    assert followup.schedule == {}
    assert followup.next_run_at is None
    assert erased_approval.status == "cancelled"
    assert erased_approval.summary == "Customer data erased."
    assert erased_approval.payload == {"erased": True}
    assert erased_notification.status == "archived"
    assert erased_notification.title == "Customer data erased."
    assert erased_notification.body == "[erased]"
    assert erased_notification.context == {"erased": True}

    detail = client.get(f"/api/v1/customers/{customer.id}")
    listed = client.get("/api/v1/customers", params={"q": "ACME"})
    exported = client.get("/api/v1/exports/customers.csv")

    assert detail.status_code == 404
    assert listed.json()["total"] == 0
    assert "ACME Trading" not in exported.text
    assert "jane@acme.example" not in exported.text
    erasure_audit = db_session.query(models.AuditLog).filter_by(action_type="customer_erased").one()
    assert erasure_audit.snapshot["counts"]["messages"] == 1
    for audit in db_session.query(models.AuditLog).all():
        assert "jane@acme.example" not in str(audit.snapshot)


def test_customers_api_is_tenant_scoped(client, db_session):
    customer, _, _, _ = _seed_customer_flow(db_session)

    detail = client.get(f"/api/v1/customers/{customer.id}", headers={"Authorization": "Bearer seller:2"})
    patched = client.patch(
        f"/api/v1/customers/{customer.id}",
        headers={"Authorization": "Bearer seller:2"},
        json={"status": "inactive"},
    )
    deleted = client.delete(f"/api/v1/customers/{customer.id}", headers={"Authorization": "Bearer seller:2"})

    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "customer_not_found"
    assert patched.status_code == 404
    assert deleted.status_code == 404
    assert db_session.get(models.Customer, customer.id).status == "active"
    assert db_session.get(models.Customer, customer.id).deleted_at is None
