"""
/* ========================================================================== */
/* GEB L3: 设置 API 测试                                                      */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI TestClient、SQLite 会话夹具、app.agent_tools、app.models 与 seller_settings
 * [OUTPUT]: 验证 settings API 可读写 seller 设置、记录审计，并让 AI 身份披露开关影响出站消息
 * [POS]: tests 的租户设置证明文件，锁住设置页与 AI 披露合规需求的后端行为
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import agent_tools, models
from app.services.seller_settings import AI_DISCLOSURE_TEXT


def _seed_conversation(db_session):
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
        channel="email",
        language="en",
    )
    db_session.add(conversation)
    db_session.flush()
    return conversation


def test_settings_api_reads_updates_and_audits_seller_settings(client, db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    db_session.commit()

    current = client.get("/api/v1/settings")
    patched = client.patch(
        "/api/v1/settings",
        json={
            "name": "Closer Demo Exporter",
            "phone": "+15550001111",
            "ai_disclosure": False,
            "settings": {"large_order_approval_threshold": "5000", "reply_tone": "concise"},
        },
    )

    assert current.status_code == 200
    assert current.json()["ai_disclosure"] is True
    assert patched.status_code == 200
    assert patched.json()["name"] == "Closer Demo Exporter"
    assert patched.json()["phone"] == "+15550001111"
    assert patched.json()["ai_disclosure"] is False
    assert patched.json()["settings"]["large_order_approval_threshold"] == "5000"
    audit = db_session.query(models.AuditLog).filter_by(action_type="seller_settings_updated").one()
    assert audit.target_type == "seller"


def test_settings_api_rejects_blank_required_settings(client, db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    db_session.commit()

    response = client.patch("/api/v1/settings", json={"name": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_settings"


def test_ai_disclosure_setting_controls_outbound_message_content(client, db_session):
    conversation = _seed_conversation(db_session)
    client.patch("/api/v1/settings", json={"ai_disclosure": False})

    without_disclosure = agent_tools.send_message(db_session, 1, conversation.id, "Thanks, we can help.")
    client.patch("/api/v1/settings", json={"ai_disclosure": True})
    with_disclosure = agent_tools.send_message(db_session, 1, conversation.id, "We will prepare a quote.")

    first = db_session.get(models.Message, without_disclosure["message_id"])
    second = db_session.get(models.Message, with_disclosure["message_id"])
    assert first.content == "Thanks, we can help."
    assert AI_DISCLOSURE_TEXT not in without_disclosure["delivery"]["payload"]["body"]
    assert second.content.endswith(AI_DISCLOSURE_TEXT)
    assert with_disclosure["delivery"]["payload"]["body"].rstrip().endswith(AI_DISCLOSURE_TEXT)
