"""
/* ========================================================================== */
/* GEB L3: Email 适配器                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 Python email 标准库与 schemas.ChannelContact/InboundMessage
 * [OUTPUT]: 对外提供 OutboundEmail 与 EmailAdapter
 * [POS]: services 的 email 渠道边界，负责原始邮件标准化与 SMTP 文本消息组合
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from dataclasses import dataclass
from email import message_from_string
from email.message import EmailMessage
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime

from app.schemas import ChannelContact, InboundMessage


@dataclass(frozen=True)
class OutboundEmail:
    from_email: str
    to_email: str
    subject: str
    body: str
    message_id: str | None = None


class EmailAdapter:
    channel = "email"

    def normalize_raw_email(self, raw_email: str) -> InboundMessage:
        parsed = message_from_string(raw_email, policy=default)
        display_name, email_address = parseaddr(parsed.get("from", ""))
        channel_message_id = (parsed.get("message-id") or parsed.get("x-mailer-id") or "").strip("<>")
        if not channel_message_id:
            channel_message_id = f"email:{abs(hash(raw_email))}"
        received_at = None
        if parsed.get("date"):
            received_at = parsedate_to_datetime(parsed["date"])

        return InboundMessage(
            channel="email",
            channel_message_id=channel_message_id,
            from_=ChannelContact(
                name=display_name or None,
                email=email_address.lower() or None,
            ),
            content=self._extract_text(parsed),
            attachments=[],
            received_at=received_at,
            language=None,
        )

    def compose_smtp_message(self, outbound: OutboundEmail) -> EmailMessage:
        message = EmailMessage()
        message["From"] = outbound.from_email
        message["To"] = outbound.to_email
        message["Subject"] = outbound.subject
        if outbound.message_id:
            message["Message-ID"] = f"<{outbound.message_id.strip('<>')}>"
        message.set_content(outbound.body)
        return message

    def _extract_text(self, parsed) -> str:
        if parsed.is_multipart():
            for part in parsed.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_content().strip()
            for part in parsed.walk():
                if part.get_content_maintype() == "text":
                    return part.get_content().strip()
            return ""
        return parsed.get_content().strip()
