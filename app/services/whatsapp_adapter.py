"""
/* ========================================================================== */
/* GEB L3: WhatsApp 适配器                                                    */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 hmac/sha256、datetime UTC 与 schemas.ChannelContact/InboundMessage
 * [OUTPUT]: 对外提供 WhatsAppAdapter
 * [POS]: services 的 WhatsApp Cloud API 边界，负责 webhook 标准化、payload 组合与签名校验
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import hmac
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from app.schemas import ChannelContact, InboundMessage


class WhatsAppAdapter:
    channel = "whatsapp"

    def normalize_webhook(self, payload: dict[str, Any]) -> InboundMessage:
        value = self._first_change_value(payload)
        messages = value.get("messages") or []
        if not messages:
            raise ValueError("WhatsApp webhook does not contain messages")
        message = messages[0]
        contact = (value.get("contacts") or [{}])[0]
        phone = contact.get("wa_id") or message.get("from")
        profile = contact.get("profile") or {}
        timestamp = message.get("timestamp")

        return InboundMessage(
            channel="whatsapp",
            channel_message_id=message["id"],
            from_=ChannelContact(
                name=profile.get("name"),
                phone=phone,
            ),
            content=self._message_text(message),
            attachments=[],
            received_at=datetime.fromtimestamp(int(timestamp), tz=UTC) if timestamp else None,
            language=None,
        )

    def compose_text_payload(self, to_phone: str, body: str) -> dict[str, Any]:
        return {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }

    def compose_template_payload(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en_US",
        parameters: list[str] | None = None,
    ) -> dict[str, Any]:
        body_parameters = [
            {"type": "text", "text": parameter}
            for parameter in (parameters or [])
        ]
        components = [{"type": "body", "parameters": body_parameters}] if body_parameters else []
        return {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }

    def verify_signature(self, raw_body: bytes, signature: str, app_secret: str) -> bool:
        expected = "sha256=" + hmac.new(app_secret.encode(), raw_body, sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _first_change_value(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return payload["entry"][0]["changes"][0]["value"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Invalid WhatsApp webhook payload") from exc

    def _message_text(self, message: dict[str, Any]) -> str:
        if message.get("type") == "text":
            return (message.get("text") or {}).get("body", "")
        if message.get("type") == "button":
            return (message.get("button") or {}).get("text", "")
        return f"[{message.get('type', 'unknown')} message]"
