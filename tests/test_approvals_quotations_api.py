"""
/* ========================================================================== */
/* GEB L3: 审批与报价 API 测试                                                */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI TestClient、SQLite 会话夹具、Decimal、app.agent_tools 与 app.models
 * [OUTPUT]: 验证 approval patch/approve/reject、quotation detail/patch/send、底价报价发送审批、PI 审批执行与文本/PDF 文件产物
 * [POS]: tests 的审批报价接口证明文件，锁住人工审批与报价 API 的安全成交路径
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from decimal import Decimal

from app import agent_tools, models
from app.services.seller_settings import AI_DISCLOSURE_TEXT


def _seed_conversation(db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    product = models.Product(seller_id=1, name="LED Desk Lamp", cost=Decimal("2.00"), moq=100, status="active")
    db_session.add_all([seller, customer, product])
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
    rule = models.PricingRule(
        seller_id=1,
        product_id=product.id,
        margin_rate=Decimal("0.25"),
        logistics_template={"unit_cost": "0.10"},
        tiered_prices=[{"min_qty": 500, "price": "3.20"}],
        valid_days=10,
        floor_price=Decimal("3.00"),
        currency="USD",
    )
    db_session.add_all([conversation, rule])
    db_session.flush()
    return inquiry, conversation, product


def test_approval_patch_and_approve_executes_message_send(client, db_session):
    _, conversation, _ = _seed_conversation(db_session)
    pending = agent_tools.send_message(db_session, 1, conversation.id, "We can offer USD 2.80 per unit.")

    listed = client.get("/api/v1/approvals")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == pending["approval_id"]

    patched = client.patch(
        f"/api/v1/approvals/{pending['approval_id']}",
        json={"payload": {"content": "We can offer USD 3.20 per unit after review."}},
    )
    assert patched.status_code == 200
    assert patched.json()["payload"]["content"].endswith("after review.")

    approved = client.post(f"/api/v1/approvals/{pending['approval_id']}/approve")

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["executed"] is True
    message = db_session.get(models.Message, approved.json()["result"]["message_id"])
    assert message.content.startswith("We can offer USD 3.20 per unit after review.")
    assert message.content.endswith(AI_DISCLOSURE_TEXT)
    assert db_session.get(models.Conversation, conversation.id).is_human_takeover is False


def test_approval_reject_marks_pending_item_rejected(client, db_session):
    _, conversation, _ = _seed_conversation(db_session)
    pending = agent_tools.send_message(db_session, 1, conversation.id, "We guarantee delivery and contract terms.")

    rejected = client.post(
        f"/api/v1/approvals/{pending['approval_id']}/reject",
        json={"reason": "Owner will reply manually"},
    )

    assert rejected.status_code == 200
    approval = db_session.get(models.Approval, pending["approval_id"])
    assert approval.status == "rejected"
    assert approval.payload["reject_reason"] == "Owner will reply manually"


def test_quotation_detail_patch_and_send(client, db_session):
    inquiry, conversation, product = _seed_conversation(db_session)
    quote = agent_tools.calc_quote(db_session, 1, inquiry.id, [{"product_id": product.id, "quantity": 500}])

    detail = client.get(f"/api/v1/quotations/{quote['quotation_id']}")
    assert detail.status_code == 200
    assert detail.json()["items"][0]["quantity"] == 500

    patched = client.patch(
        f"/api/v1/quotations/{quote['quotation_id']}",
        json={
            "terms": {"message": "Updated reviewed quote."},
            "items": [{"product_id": product.id, "quantity": 1000, "unit_price": "3.10"}],
        },
    )
    assert patched.status_code == 200
    assert patched.json()["total_amount"] == 3100.0

    sent = client.post(f"/api/v1/quotations/{quote['quotation_id']}/send")

    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert db_session.get(models.Quotation, quote["quotation_id"]).status == "sent"
    messages = client.get(f"/api/v1/conversations/{conversation.id}/messages").json()["items"]
    assert messages[-1]["content"].startswith("Updated reviewed quote.")
    assert messages[-1]["content"].endswith(AI_DISCLOSURE_TEXT)


def test_quotation_send_floor_hit_creates_approval_then_approve_sends(client, db_session):
    inquiry, _, product = _seed_conversation(db_session)
    rule = db_session.query(models.PricingRule).filter_by(product_id=product.id).one()
    rule.tiered_prices = [{"min_qty": 500, "price": "2.50"}]
    quote = agent_tools.calc_quote(db_session, 1, inquiry.id, [{"product_id": product.id, "quantity": 500}])

    response = client.post(f"/api/v1/quotations/{quote['quotation_id']}/send")
    approved = client.post(f"/api/v1/approvals/{response.json()['approval_id']}/approve")

    assert response.status_code == 202
    assert response.json()["status"] == "pending_approval"
    assert response.json()["reason"] == "below_floor_price"
    approval = db_session.get(models.Approval, response.json()["approval_id"])
    assert approval.type == "quotation_send"
    assert approval.payload["quotation_id"] == quote["quotation_id"]
    assert approved.status_code == 200
    assert approved.json()["result"]["status"] == "sent"
    assert approved.json()["result"]["delivery"]["status"] == "queued"
    assert db_session.get(models.Quotation, quote["quotation_id"]).status == "sent"


def test_generate_pi_approval_executes_through_api(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_DIR", str(tmp_path))
    inquiry, _, product = _seed_conversation(db_session)
    quote = agent_tools.calc_quote(db_session, 1, inquiry.id, [{"product_id": product.id, "quantity": 500}])
    pending = agent_tools.generate_pi(db_session, 1, quote["quotation_id"])

    approved = client.post(f"/api/v1/approvals/{pending['approval_id']}/approve")
    detail = client.get(f"/api/v1/quotations/{quote['quotation_id']}")

    assert approved.status_code == 200
    assert approved.json()["result"]["pi_number"] == "PI-000001"
    assert "PROFORMA INVOICE" in approved.json()["result"]["pi_document"]
    assert detail.json()["is_pi"] is True
    assert detail.json()["terms"]["pi_document"] == approved.json()["result"]["pi_document"]
    pi_file = approved.json()["result"]["pi_document_file"]
    assert pi_file["filename"] == "PI-000001.txt"
    assert detail.json()["terms"]["pi_document_file"]["storage_key"] == "seller_1/PI-000001.txt"
    assert tmp_path.joinpath("seller_1", "PI-000001.txt").exists()
    pdf_file = approved.json()["result"]["pi_pdf_file"]
    assert pdf_file["filename"] == "PI-000001.pdf"
    assert detail.json()["terms"]["pi_pdf_file"]["storage_key"] == "seller_1/PI-000001.pdf"
    assert tmp_path.joinpath("seller_1", "PI-000001.pdf").exists()
