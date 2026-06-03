"""
/* ========================================================================== */
/* GEB L3: 鉴权依赖测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI TestClient、SQLite 会话夹具与 app.models
 * [OUTPUT]: 验证 Authorization Bearer seller:<id>、Bearer cak_<token> API key、X-Seller-Id shortcut、撤销与 invalid_token 错误
 * [POS]: tests 的租户上下文证明文件，覆盖 API 契约中的 Bearer token 与正式 API key 接缝
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import models


def test_bearer_token_selects_seller_tenant(client, db_session):
    db_session.add_all(
        [
            models.Seller(id=1, name="Seller One", email="one@example.com"),
            models.Seller(id=2, name="Seller Two", email="two@example.com"),
            models.Product(seller_id=1, name="Private Lamp", status="active"),
            models.Product(seller_id=2, name="Tenant Bottle", status="active"),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/products", headers={"Authorization": "Bearer seller:2"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Tenant Bottle"


def test_invalid_bearer_token_uses_contract_error_shape(client):
    response = client.get("/api/v1/products", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_token",
            "message": "Authorization must be Bearer seller:<id> or Bearer cak_<token>",
        }
    }


def test_missing_authorization_is_rejected_when_dev_auth_disabled(client, db_session, monkeypatch):
    monkeypatch.delenv("CLOSER_ALLOW_DEV_AUTH", raising=False)
    db_session.add_all(
        [
            models.Seller(id=1, name="Seller One", email="one@example.com"),
            models.Customer(seller_id=1, email="secret@example.com", company="Secret Buyer"),
        ]
    )
    db_session.commit()

    customers = client.get("/api/v1/customers")
    export = client.get("/api/v1/exports/customers.csv")
    api_keys = client.get("/api/v1/auth/api-keys")

    assert customers.status_code == 401
    assert export.status_code == 401
    assert api_keys.status_code == 401
    assert customers.json()["error"] == {
        "code": "invalid_token",
        "message": "Authorization must be Bearer cak_<token>",
    }


def test_x_seller_id_shortcut_still_works_for_mvp_tests(client, db_session):
    db_session.add_all(
        [
            models.Seller(id=7, name="Shortcut Seller", email="shortcut@example.com"),
            models.Product(seller_id=7, name="Shortcut Product", status="active"),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/products", headers={"X-Seller-Id": "7"})

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "Shortcut Product"


def test_api_key_can_be_created_used_listed_and_revoked(client, db_session):
    db_session.add_all(
        [
            models.Seller(id=1, name="Seller One", email="one@example.com"),
            models.Product(seller_id=1, name="Private Lamp", status="active"),
        ]
    )
    db_session.commit()

    created = client.post(
        "/api/v1/auth/api-keys",
        headers={"Authorization": "Bearer seller:1"},
        json={"name": "Production backend", "scopes": ["api"]},
    )

    assert created.status_code == 201
    token = created.json()["token"]
    assert token.startswith("cak_")
    assert created.json()["token_prefix"] == token[:16]
    assert "token_hash" not in created.json()
    api_key_id = created.json()["id"]

    listed = client.get("/api/v1/auth/api-keys", headers={"Authorization": "Bearer seller:1"})
    api_call = client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})
    stored_key = db_session.get(models.SellerApiKey, api_key_id)

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert "token" not in listed.json()["items"][0]
    assert api_call.status_code == 200
    assert api_call.json()["items"][0]["name"] == "Private Lamp"
    assert stored_key.token_hash != token
    assert stored_key.last_used_at is not None

    revoked = client.post(f"/api/v1/auth/api-keys/{api_key_id}/revoke", headers={"Authorization": "Bearer seller:1"})
    denied = client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})

    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["revoked_at"] is not None
    assert denied.status_code == 401


def test_api_key_management_is_tenant_scoped(client, db_session):
    db_session.add_all(
        [
            models.Seller(id=1, name="Seller One", email="one@example.com"),
            models.Seller(id=2, name="Seller Two", email="two@example.com"),
        ]
    )
    db_session.commit()
    created = client.post(
        "/api/v1/auth/api-keys",
        headers={"Authorization": "Bearer seller:1"},
        json={"name": "Seller one key"},
    )

    response = client.post(
        f"/api/v1/auth/api-keys/{created.json()['id']}/revoke",
        headers={"Authorization": "Bearer seller:2"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "api_key_not_found"
    assert db_session.get(models.SellerApiKey, created.json()["id"]).status == "active"
