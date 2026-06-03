"""
/* ========================================================================== */
/* GEB L3: Agent 报价工具测试                                                 */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest、Decimal、SQLite 会话夹具、app.agent_tools、app.models 与 approvals 服务
 * [OUTPUT]: 验证 calc_quote 草稿报价、generate_pi 审批语义、PI 文档文本/PDF 与文件产物、租户隔离
 * [POS]: tests 的 Agent 报价工具证明文件，锁住工具门面到报价/审批服务的成交链路
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from decimal import Decimal

import pytest

from app import agent_tools, models
from app.services.approvals import approve_approval


def _seed(db_session):
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
    return inquiry, product


def test_calc_quote_tool_creates_draft_quotation_and_lines(db_session):
    inquiry, product = _seed(db_session)

    result = agent_tools.calc_quote(
        db_session,
        1,
        inquiry.id,
        [{"product_id": product.id, "quantity": 500}],
        destination="US",
    )
    db_session.commit()

    assert result["quotation_id"] == 1
    assert result["total_amount"] == 1650.0
    assert result["hits_floor"] is False
    assert "Thanks for your inquiry" in result["message"]

    quotation = db_session.get(models.Quotation, result["quotation_id"])
    assert quotation.status == "draft"
    assert quotation.created_by == "ai"
    assert quotation.items[0].quantity == 500


def test_generate_pi_requests_approval_before_mutating_quotation(db_session):
    inquiry, product = _seed(db_session)
    quote = agent_tools.calc_quote(db_session, 1, inquiry.id, [{"product_id": product.id, "quantity": 500}])

    pi = agent_tools.generate_pi(db_session, 1, quote["quotation_id"])

    assert pi["status"] == "pending_approval"
    approval = db_session.get(models.Approval, pi["approval_id"])
    assert approval.type == "pi_generate"
    assert approval.payload["quotation_id"] == quote["quotation_id"]
    assert db_session.get(models.Quotation, quote["quotation_id"]).is_pi is False


def test_generate_pi_approval_creates_formal_pi_document(db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_DIR", str(tmp_path))
    inquiry, product = _seed(db_session)
    quote = agent_tools.calc_quote(db_session, 1, inquiry.id, [{"product_id": product.id, "quantity": 500}])
    pending = agent_tools.generate_pi(db_session, 1, quote["quotation_id"])

    result = approve_approval(db_session, 1, pending["approval_id"])
    quotation = db_session.get(models.Quotation, quote["quotation_id"])

    assert result["status"] == "approved"
    assert result["result"]["pi_number"] == "PI-000001"
    assert "PROFORMA INVOICE" in result["result"]["pi_document"]
    assert "LED Desk Lamp" in result["result"]["pi_document"]
    assert quotation.is_pi is True
    assert quotation.terms["pi_document"] == result["result"]["pi_document"]
    pi_file = result["result"]["pi_document_file"]
    assert pi_file["filename"] == "PI-000001.txt"
    assert pi_file["storage_key"] == "seller_1/PI-000001.txt"
    assert tmp_path.joinpath("seller_1", "PI-000001.txt").read_text(encoding="utf-8") == result["result"]["pi_document"]
    pdf_file = result["result"]["pi_pdf_file"]
    pdf_path = tmp_path.joinpath("seller_1", "PI-000001.pdf")
    assert pdf_file["filename"] == "PI-000001.pdf"
    assert pdf_file["mime_type"] == "application/pdf"
    assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
    assert pdf_path.read_bytes().rstrip().endswith(b"%%EOF")


def test_generate_pi_is_tenant_scoped(db_session):
    inquiry, product = _seed(db_session)
    quote = agent_tools.calc_quote(db_session, 1, inquiry.id, [{"product_id": product.id, "quantity": 500}])

    with pytest.raises(LookupError):
        agent_tools.generate_pi(db_session, 2, quote["quotation_id"])
