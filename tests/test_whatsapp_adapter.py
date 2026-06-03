"""
/* ========================================================================== */
/* GEB L3: WhatsApp 适配器测试                                                */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 hmac/sha256、app.models 与 WhatsAppAdapter
 * [OUTPUT]: 验证 WhatsApp webhook 标准化、文本 payload 组合与签名校验
 * [POS]: tests 的 WhatsApp 边界证明文件，锁住 Cloud API payload 与入站解析契约
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import hmac
from hashlib import sha256

from app import models
from app.services.whatsapp_adapter import WhatsAppAdapter


def whatsapp_payload(message_id="wamid.001"):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [{"profile": {"name": "Jane Buyer"}, "wa_id": "15551234567"}],
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": message_id,
                                    "timestamp": "1780379520",
                                    "text": {"body": "Need 800 LED desk lamps for US."},
                                    "type": "text",
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def test_whatsapp_adapter_normalizes_cloud_api_webhook():
    inbound = WhatsAppAdapter().normalize_webhook(whatsapp_payload())

    assert inbound.channel == "whatsapp"
    assert inbound.channel_message_id == "wamid.001"
    assert inbound.from_.name == "Jane Buyer"
    assert inbound.from_.phone == "15551234567"
    assert inbound.content == "Need 800 LED desk lamps for US."
    assert inbound.received_at is not None


def test_whatsapp_adapter_composes_text_and_template_payloads():
    adapter = WhatsAppAdapter()

    text_payload = adapter.compose_text_payload("15551234567", "Thanks for your inquiry.")
    template_payload = adapter.compose_template_payload(
        "15551234567",
        "quote_followup",
        parameters=["Jane", "$3.25"],
    )

    assert text_payload["type"] == "text"
    assert text_payload["text"]["body"] == "Thanks for your inquiry."
    assert template_payload["type"] == "template"
    assert template_payload["template"]["components"][0]["parameters"][1]["text"] == "$3.25"


def test_whatsapp_signature_verification():
    body = b'{"hello":"world"}'
    secret = "app-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()

    assert WhatsAppAdapter().verify_signature(body, signature, secret) is True
    assert WhatsAppAdapter().verify_signature(body, "sha256=bad", secret) is False


def test_whatsapp_webhook_ingests_message(client, db_session):
    response = client.post("/api/v1/webhooks/whatsapp", json=whatsapp_payload())

    assert response.status_code == 201
    data = response.json()
    assert data["duplicate"] is False

    inquiry = db_session.get(models.Inquiry, data["inquiry_id"])
    assert inquiry.source_channel == "whatsapp"
    assert inquiry.parsed["quantity"] == 800

    message = db_session.get(models.Message, data["message_id"])
    assert message.channel_message_id == "wamid.001"
    assert message.sender_role == "customer"
