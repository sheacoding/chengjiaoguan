"""
/* ========================================================================== */
/* GEB L3: 配置 API 测试                                                      */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI TestClient、SQLite 会话夹具、app.agent_tools、app.models、quote_engine 与 credentials reveal helper
 * [OUTPUT]: 验证 products CRUD、pricing-rules、价格规则版本、汇率缓存刷新确认、channels、凭据封存、dashboard 与 request_handoff 契约
 * [POS]: tests 的配置接口证明文件，覆盖 API 契约第五节缺失的 MVP 配置面
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from zipfile import ZipFile
from io import BytesIO

import pytest

from app import agent_tools, models
from app.database import utcnow
from app.services.credentials import SEAL_VERSION, reveal_credentials
from app.services.quote_engine import QuoteItemInput, calculate_quote


def test_product_pricing_channel_and_dashboard_api(client, db_session):
    product_response = client.post(
        "/api/v1/products",
        json={
            "name": "LED Desk Lamp",
            "sku": "LAMP-10W",
            "specs": {"power": "10W"},
            "cost": "2.00",
            "currency": "USD",
            "moq": 100,
            "description": "Aluminum desk lamp.",
        },
    )
    assert product_response.status_code == 201
    product = product_response.json()
    assert product["id"] == 1
    assert product["cost"] == 2.0

    products = client.get("/api/v1/products", params={"status": "active"}).json()
    assert products["total"] == 1
    assert products["items"][0]["sku"] == "LAMP-10W"

    rule_response = client.post(
        "/api/v1/pricing-rules",
        json={
            "product_id": product["id"],
            "margin_rate": "0.25",
            "logistics_template": {"unit_cost": "0.10"},
            "tiered_prices": [{"min_qty": 500, "price": "3.20"}],
            "valid_days": 14,
            "floor_price": "3.00",
            "currency": "USD",
        },
    )
    assert rule_response.status_code == 201
    rule = rule_response.json()
    assert rule["product_id"] == product["id"]

    patched = client.put(
        f"/api/v1/pricing-rules/{rule['id']}",
        json={"floor_price": "3.10", "valid_days": 10},
    )
    assert patched.status_code == 200
    assert patched.json()["floor_price"] == 3.1
    versions = client.get(f"/api/v1/pricing-rules/{rule['id']}/versions")
    assert versions.status_code == 200
    assert versions.json()["total"] == 2
    assert versions.json()["items"][0]["version"] == 2
    assert versions.json()["items"][0]["snapshot"]["floor_price"] == "3.10"
    assert versions.json()["items"][1]["version"] == 1
    assert versions.json()["items"][1]["snapshot"]["floor_price"] == "3.00"
    assert db_session.query(models.PricingRuleVersion).filter_by(pricing_rule_id=rule["id"]).count() == 2

    channel_response = client.post(
        "/api/v1/channels",
        json={"channel_type": "email", "name": "Sales inbox", "credentials": {"host": "imap.example.com"}},
    )
    assert channel_response.status_code == 201
    assert channel_response.json()["credentials_configured"] is True
    assert channel_response.json()["credentials_key_status"] == "current"
    stored_channel = db_session.get(models.ChannelAccount, channel_response.json()["id"])
    assert stored_channel.credentials["_sealed"] == SEAL_VERSION
    assert "imap.example.com" not in str(stored_channel.credentials)
    assert reveal_credentials(stored_channel.credentials) == {"host": "imap.example.com"}

    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add(customer)
    db_session.flush()
    inquiry_won = models.Inquiry(seller_id=1, customer_id=customer.id, status="won", grade="A")
    inquiry_new = models.Inquiry(seller_id=1, customer_id=customer.id, status="new", grade="B")
    db_session.add_all([inquiry_won, inquiry_new])
    db_session.flush()
    conversation = models.Conversation(
        seller_id=1,
        customer_id=customer.id,
        inquiry_id=inquiry_won.id,
        channel="email",
        is_human_takeover=True,
        status="open",
    )
    db_session.add(conversation)
    db_session.flush()
    message = models.Message(conversation_id=conversation.id, sender_role="ai", content="Quote is ready.")
    db_session.add(message)
    db_session.flush()
    now = utcnow()
    stored_rule = db_session.get(models.PricingRule, rule["id"])
    stored_rule.logistics_template = {
        "exchange_rate_cache": {
            "source": "demo_bank",
            "confirmed": False,
            "expires_at": now.date().isoformat(),
            "rates": {"USD": {"EUR": "0.90"}},
        }
    }
    db_session.add_all(
        [
            models.Approval(
                seller_id=1,
                conversation_id=conversation.id,
                inquiry_id=inquiry_won.id,
                type="handoff",
                reason="large_order_amount",
                summary="Large order needs review.",
                status="pending",
                executed=False,
            ),
            models.Quotation(
                seller_id=1,
                inquiry_id=inquiry_won.id,
                customer_id=customer.id,
                currency="USD",
                total_amount="128.50",
                status="draft",
                hits_floor=True,
            ),
            models.DeliveryAttempt(
                seller_id=1,
                message_id=message.id,
                channel="email",
                external_id="closer:email:out:dashboard",
                status="failed",
                next_retry_at=now,
                payload={},
                response={},
            ),
            models.FollowupTask(
                seller_id=1,
                inquiry_id=inquiry_new.id,
                conversation_id=conversation.id,
                next_run_at=now,
                status="active",
            ),
        ]
    )
    db_session.commit()

    metrics = client.get("/api/v1/dashboard/metrics")
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["today_inquiries"] == 2
    assert payload["pending_handoffs"] == 1
    assert payload["auto_handle_rate"] == 0.5
    assert payload["conversion"] == 0.5
    assert payload["total_inquiries"] == 2
    assert payload["inquiries_by_grade"] == {"A": 1, "B": 1, "C": 0}
    assert payload["inquiries_by_status"]["won"] == 1
    assert payload["inquiries_by_status"]["new"] == 1
    assert payload["conversation"] == {"open": 1, "human_takeover": 1}
    assert payload["approval"]["pending"] == 1
    assert payload["quotation"]["draft"] == 1
    assert payload["quotation"]["hits_floor"] == 1
    assert payload["quotation"]["total_amount"] == 128.5
    assert payload["delivery"]["failed"] == 1
    assert payload["delivery"]["retry_due"] == 1
    assert payload["followup"]["active"] == 1
    assert payload["followup"]["due"] == 1
    assert payload["exchange_rate_cache"] == {"configured": 1, "unconfirmed": 1, "expired": 0, "missing_expires_at": 0}


def test_product_detail_update_and_soft_delete(client, db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    product = models.Product(seller_id=1, name="LED Desk Lamp", sku="OLD", status="active")
    db_session.add_all([seller, product])
    db_session.commit()

    detail = client.get(f"/api/v1/products/{product.id}")
    patched = client.patch(
        f"/api/v1/products/{product.id}",
        json={
            "sku": "LAMP-10W",
            "specs": {"power": "10W"},
            "cost": "2.50",
            "description": "Updated lamp.",
        },
    )
    deleted = client.delete(f"/api/v1/products/{product.id}")
    list_after_delete = client.get("/api/v1/products")
    detail_after_delete = client.get(f"/api/v1/products/{product.id}")

    assert detail.status_code == 200
    assert detail.json()["sku"] == "OLD"
    assert patched.status_code == 200
    assert patched.json()["sku"] == "LAMP-10W"
    assert patched.json()["specs"]["power"] == "10W"
    assert patched.json()["cost"] == 2.5
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert list_after_delete.json()["total"] == 0
    assert detail_after_delete.status_code == 404
    assert db_session.get(models.Product, product.id).deleted_at is not None


def test_product_api_is_tenant_scoped(client, db_session):
    db_session.add_all(
        [
            models.Seller(id=1, name="Seller One", email="one@example.com"),
            models.Seller(id=2, name="Seller Two", email="two@example.com"),
            models.Product(seller_id=1, name="Seller One Product", status="active"),
        ]
    )
    db_session.commit()

    response = client.patch(
        "/api/v1/products/1",
        headers={"Authorization": "Bearer seller:2"},
        json={"name": "Cross tenant edit"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "product_not_found"
    assert db_session.get(models.Product, 1).name == "Seller One Product"


def test_channel_credentials_can_be_resealed_after_secret_rotation(client, db_session, monkeypatch):
    monkeypatch.setenv("CLOSER_CREDENTIALS_SECRET", "old-secret")
    created = client.post(
        "/api/v1/channels",
        json={"channel_type": "email", "name": "Sales inbox", "credentials": {"host": "imap.example.com"}},
    )
    channel_id = created.json()["id"]

    monkeypatch.setenv("CLOSER_CREDENTIALS_SECRET", "new-secret")
    monkeypatch.setenv("CLOSER_CREDENTIALS_PREVIOUS_SECRETS", "old-secret")
    legacy = client.get("/api/v1/channels")
    rotated = client.post(f"/api/v1/channels/{channel_id}/rotate-credentials")

    assert legacy.status_code == 200
    assert legacy.json()["items"][0]["credentials_key_status"] == "legacy"
    assert rotated.status_code == 200
    assert rotated.json()["rotated"] is True
    assert rotated.json()["credentials_key_status"] == "current"
    db_session.expire_all()
    stored_channel = db_session.get(models.ChannelAccount, channel_id)
    assert reveal_credentials(stored_channel.credentials) == {"host": "imap.example.com"}


def test_channel_credentials_require_secret_outside_dev_mode(client, monkeypatch):
    monkeypatch.delenv("CLOSER_ALLOW_DEV_CREDENTIALS", raising=False)
    monkeypatch.delenv("CLOSER_CREDENTIALS_SECRET", raising=False)

    response = client.post(
        "/api/v1/channels",
        json={"channel_type": "email", "name": "Sales inbox", "credentials": {"host": "imap.example.com"}},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "credentials_secret_required"


def test_pricing_rule_versions_are_tenant_scoped(client, db_session):
    db_session.add_all(
        [
            models.Seller(id=1, name="Seller One", email="one@example.com"),
            models.Seller(id=2, name="Seller Two", email="two@example.com"),
            models.Product(id=1, seller_id=1, name="Seller One Product", status="active"),
        ]
    )
    db_session.commit()
    created = client.post(
        "/api/v1/pricing-rules",
        json={"product_id": 1, "floor_price": "3.00", "currency": "USD"},
    )

    response = client.get(
        f"/api/v1/pricing-rules/{created.json()['id']}/versions",
        headers={"Authorization": "Bearer seller:2"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "pricing_rule_not_found"


def test_pricing_rule_api_rejects_invalid_rule_shape(client, db_session):
    db_session.add_all(
        [
            models.Seller(id=1, name="Demo Exporter", email="owner@example.com"),
            models.Product(seller_id=1, name="LED Desk Lamp", status="active"),
        ]
    )
    db_session.commit()

    negative_floor = client.post(
        "/api/v1/pricing-rules",
        json={"product_id": 1, "floor_price": "-1.00", "currency": "USD"},
    )
    duplicate_tier = client.post(
        "/api/v1/pricing-rules",
        json={
            "product_id": 1,
            "floor_price": "3.00",
            "tiered_prices": [{"min_qty": 500, "price": "3.20"}, {"min_qty": 500, "price": "3.10"}],
        },
    )
    invalid_exchange = client.post(
        "/api/v1/pricing-rules",
        json={
            "product_id": 1,
            "floor_price": "3.00",
            "logistics_template": {"exchange_rates": {"USD": {"EUR": "0"}}},
        },
    )
    invalid_cache = client.post(
        "/api/v1/pricing-rules",
        json={
            "product_id": 1,
            "floor_price": "3.00",
            "logistics_template": {"exchange_rate_cache": {"confirmed": True, "rates": {"USD": {"EUR": "0.90"}}}},
        },
    )

    assert negative_floor.status_code == 422
    assert negative_floor.json()["error"]["code"] == "invalid_pricing_rule"
    assert duplicate_tier.status_code == 422
    assert "unique" in duplicate_tier.json()["error"]["message"]
    assert invalid_exchange.status_code == 422
    assert "exchange_rates" in invalid_exchange.json()["error"]["message"]
    assert invalid_cache.status_code == 422
    assert "expires_at" in invalid_cache.json()["error"]["message"]


def test_pricing_rule_exchange_rate_cache_refresh_and_confirm_api(client, db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    product = models.Product(
        seller_id=1,
        name="LED Desk Lamp",
        cost="2.00",
        currency="USD",
        moq=100,
        status="active",
    )
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add_all([seller, product, customer])
    db_session.flush()
    inquiry = models.Inquiry(seller_id=1, customer_id=customer.id, raw_content="Need 1000 lamps", status="new")
    db_session.add(inquiry)
    db_session.flush()
    rule = models.PricingRule(
        seller_id=1,
        product_id=product.id,
        margin_rate="0.25",
        logistics_template={"unit_cost": "0.10"},
        floor_price="2.00",
        currency="USD",
    )
    db_session.add(rule)
    db_session.commit()

    refreshed = client.post(
        f"/api/v1/pricing-rules/{rule.id}/refresh-exchange-rate-cache",
        json={
            "target_currencies": ["EUR"],
            "source": "demo_bank",
            "rates": {"USD": {"EUR": "0.80"}},
            "ttl_days": 3,
        },
    )

    assert refreshed.status_code == 200
    cache = refreshed.json()["logistics_template"]["exchange_rate_cache"]
    assert cache["source"] == "demo_bank"
    assert cache["confirmed"] is False
    assert cache["rates"] == {"USD": {"EUR": "0.80"}}

    with pytest.raises(ValueError, match="manually confirmed"):
        calculate_quote(db_session, 1, inquiry.id, [QuoteItemInput(product_id=product.id, quantity=1000)], currency="EUR")

    confirmed = client.post(f"/api/v1/pricing-rules/{rule.id}/confirm-exchange-rate-cache")

    assert confirmed.status_code == 200
    assert confirmed.json()["logistics_template"]["exchange_rate_cache"]["confirmed"] is True
    result = calculate_quote(db_session, 1, inquiry.id, [QuoteItemInput(product_id=product.id, quantity=1000)], currency="EUR")
    assert str(result.lines[0].unit_price) == "2.08"


def test_products_import_accepts_xlsx_template(client):
    response = client.post(
        "/api/v1/products/import",
        files={
            "file": (
                "products.xlsx",
                _xlsx_bytes(
                    [
                        ["name", "sku", "cost", "currency", "moq", "specs"],
                        ["LED Desk Lamp", "LAMP-10W", "2.25", "USD", "100", "{\"power\":\"10W\"}"],
                        ["Travel Bottle", "BOT-500", "1.10", "USD", "200", "{\"volume\":\"500ml\"}"],
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["total"] == 2
    assert payload["errors"] == []
    assert payload["items"][0]["specs"]["power"] == "10W"


def test_products_import_reports_row_level_errors(client):
    response = client.post(
        "/api/v1/products/import",
        files={
            "file": (
                "products.csv",
                (
                    "name,sku,cost,currency,moq,specs\n"
                    "LED Desk Lamp,LAMP-10W,2.25,USD,100,{}\n"
                    ",NO-NAME,1.00,USD,10,{}\n"
                    "Bad MOQ,BAD-MOQ,1.00,USD,abc,{}\n"
                ).encode(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["sku"] == "LAMP-10W"
    assert payload["errors"] == [
        {"row_number": 3, "code": "missing_name", "message": "Product name is required"},
        {"row_number": 4, "code": "invalid_moq", "message": "moq must be a number"},
    ]


def test_request_handoff_tool_creates_pending_approval(db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add_all([seller, customer])
    db_session.flush()
    inquiry = models.Inquiry(seller_id=1, customer_id=customer.id, raw_content="Need custom contract.", status="new")
    db_session.add(inquiry)
    db_session.flush()
    conversation = models.Conversation(seller_id=1, customer_id=customer.id, inquiry_id=inquiry.id, channel="email")
    db_session.add(conversation)
    db_session.flush()

    result = agent_tools.request_handoff(
        db_session,
        1,
        conversation.id,
        "contract_terms",
        "Customer asks for non-standard contract terms.",
        suggestion="Owner should review payment and penalty clauses.",
    )

    approval = db_session.get(models.Approval, result["approval_id"])
    assert result["status"] == "pending"
    assert approval.type == "handoff"
    assert approval.summary.startswith("Customer asks")
    assert db_session.get(models.Conversation, conversation.id).is_human_takeover is True
    assert db_session.get(models.Inquiry, inquiry.id).status == "pending_approval"


def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    strings = [cell for row in rows for cell in row]
    index = {value: offset for offset, value in enumerate(strings)}
    shared_items = "".join(f"<si><t>{_xml(value)}</t></si>" for value in strings)
    sheet_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = "".join(f'<c t="s"><v>{index[cell]}</v></c>' for cell in row)
        sheet_rows.append(f'<row r="{row_number}">{cells}</row>')
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Products" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{shared_items}</sst>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>",
        )
    return buffer.getvalue()


def _xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
