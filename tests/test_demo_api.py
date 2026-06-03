"""
/* ========================================================================== */
/* GEB L3: Demo 场景 API 测试                                                 */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI TestClient、SQLite 会话夹具与 app.models
 * [OUTPUT]: 验证 /api/v1/demo/seed 可创建确定性演示主链路、护栏审批和跟进，并保持幂等与租户隔离
 * [POS]: tests 的 Demo 主链路证明文件，锁住兜底假数据入口不会绕过业务服务
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import models
from app.services.demo import DEMO_PRODUCT_SKU


def test_demo_seed_creates_main_flow_and_is_idempotent(client, db_session):
    first = client.post("/api/v1/demo/seed")
    second = client.post("/api/v1/demo/seed")

    assert first.status_code == 200
    assert second.status_code == 200
    payload = first.json()
    repeat = second.json()
    assert payload["scenario"] == "site_form_quote_guardrail"
    assert payload["product_matches"][0]["product_id"] == payload["product_id"]
    assert payload["score"]["grade"] == "A"
    assert payload["quotation"]["total_amount"] > 0
    assert payload["approval"]["status"] == "pending_approval"
    assert payload["approval"]["reason"] == "below_floor_price"
    assert "below_floor_price" in payload["approval"]["reasons"]
    assert payload["followup"]["status"] == "active"
    assert repeat["duplicate_inbound"] is True
    assert repeat["inquiry_id"] == payload["inquiry_id"]
    assert repeat["approval"]["approval_id"] == payload["approval"]["approval_id"]
    assert db_session.query(models.Product).filter_by(sku=DEMO_PRODUCT_SKU).count() == 1
    assert db_session.query(models.Inquiry).count() == 1
    assert db_session.query(models.Quotation).count() == 1
    assert db_session.query(models.Approval).count() == 1
    assert db_session.query(models.FollowupTask).count() == 1


def test_demo_seed_is_tenant_scoped(client, db_session):
    seller_one = client.post("/api/v1/demo/seed")
    seller_two = client.post("/api/v1/demo/seed", headers={"Authorization": "Bearer seller:2"})

    assert seller_one.status_code == 200
    assert seller_two.status_code == 200
    assert seller_one.json()["seller_id"] == 1
    assert seller_two.json()["seller_id"] == 2
    assert seller_one.json()["inquiry_id"] != seller_two.json()["inquiry_id"]
    assert db_session.query(models.Product).filter_by(seller_id=1, sku=DEMO_PRODUCT_SKU).count() == 1
    assert db_session.query(models.Product).filter_by(seller_id=2, sku=DEMO_PRODUCT_SKU).count() == 1
