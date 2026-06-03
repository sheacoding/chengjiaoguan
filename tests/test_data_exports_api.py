"""
/* ========================================================================== */
/* GEB L3: 数据导出 API 测试                                                  */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 csv/io、FastAPI TestClient、SQLite 会话夹具与 app.models
 * [OUTPUT]: 验证 exports CSV API 可导出 customers、inquiries、quotations，且保持租户隔离与错误形状
 * [POS]: tests 的 M10 数据导出证明文件，锁住看板导出需求的后端资源面
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import csv
import io
from datetime import date

from app import models


def _rows(response):
    return list(csv.DictReader(io.StringIO(response.text)))


def _seed_export_data(db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    other_seller = models.Seller(id=2, name="Other Exporter", email="other@example.com")
    customer = models.Customer(
        seller_id=1,
        name="Jane Buyer",
        company="ACME Trading",
        country="US",
        email="jane@acme.example",
        channels={"email": "jane@acme.example"},
        preferences={"incoterm": "FOB"},
        grade="A",
        status="active",
    )
    other_customer = models.Customer(seller_id=2, company="Other Buyer", email="other@example.com", status="active")
    db_session.add_all([seller, other_seller, customer, other_customer])
    db_session.flush()
    inquiry = models.Inquiry(
        seller_id=1,
        customer_id=customer.id,
        source_channel="site_form",
        raw_content="Need 5000 LED desk lamps to US.",
        parsed={"product": "LED desk lamp", "quantity": 5000},
        grade="A",
        score="88.50",
        status="quoted",
        language="en",
    )
    other_inquiry = models.Inquiry(seller_id=2, customer_id=other_customer.id, raw_content="Other", status="new")
    db_session.add_all([inquiry, other_inquiry])
    db_session.flush()
    quotation = models.Quotation(
        seller_id=1,
        inquiry_id=inquiry.id,
        customer_id=customer.id,
        currency="USD",
        total_amount="16250.00",
        valid_until=date(2026, 6, 16),
        is_pi=False,
        status="draft",
        created_by="ai",
        hits_floor=False,
        terms={"incoterm": "FOB"},
    )
    other_quotation = models.Quotation(
        seller_id=2,
        inquiry_id=other_inquiry.id,
        customer_id=other_customer.id,
        currency="USD",
        total_amount="1.00",
        status="draft",
    )
    db_session.add_all([quotation, other_quotation])
    db_session.commit()
    return customer, inquiry, quotation


def test_exports_customers_inquiries_and_quotations_csv(client, db_session):
    customer, inquiry, quotation = _seed_export_data(db_session)

    customers = client.get("/api/v1/exports/customers.csv")
    inquiries = client.get("/api/v1/exports/inquiries.csv")
    quotations = client.get("/api/v1/exports/quotations.csv")

    assert customers.status_code == 200
    assert customers.headers["content-disposition"] == 'attachment; filename="customers.csv"'
    customer_rows = _rows(customers)
    assert len(customer_rows) == 1
    assert customer_rows[0]["id"] == str(customer.id)
    assert customer_rows[0]["company"] == "ACME Trading"
    assert '"incoterm": "FOB"' in customer_rows[0]["preferences"]

    inquiry_rows = _rows(inquiries)
    assert len(inquiry_rows) == 1
    assert inquiry_rows[0]["id"] == str(inquiry.id)
    assert inquiry_rows[0]["customer_id"] == str(customer.id)
    assert inquiry_rows[0]["score"] == "88.50"
    assert '"quantity": 5000' in inquiry_rows[0]["parsed"]

    quotation_rows = _rows(quotations)
    assert len(quotation_rows) == 1
    assert quotation_rows[0]["id"] == str(quotation.id)
    assert quotation_rows[0]["total_amount"] == "16250.00"
    assert quotation_rows[0]["valid_until"] == "2026-06-16"


def test_exports_are_tenant_scoped_and_validate_dataset(client, db_session):
    _seed_export_data(db_session)

    other = client.get("/api/v1/exports/customers.csv", headers={"Authorization": "Bearer seller:2"})
    missing = client.get("/api/v1/exports/orders.csv")

    assert len(_rows(other)) == 1
    assert _rows(other)[0]["company"] == "Other Buyer"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "export_dataset_not_found"
