"""
/* ========================================================================== */
/* GEB L3: Email IMAP 轮询                                                    */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 imaplib、EmailAdapter、channel_gateway、credentials 与 channel_account 配置
 * [OUTPUT]: 对外提供 RawEmailMessage、EmailInboxClient、ImapEmailInboxClient、StaticEmailInboxClient、poll_email_channel
 * [POS]: services 的 email 入站轮询边界，把 IMAP 拉取和入站事实创建解耦，测试中可用静态 inbox 替身
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import imaplib
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app import models
from app.services.channel_gateway import ingest_inbound_message
from app.services.credentials import reveal_credentials
from app.services.email_adapter import EmailAdapter


@dataclass(frozen=True)
class RawEmailMessage:
    uid: str
    raw: str


class EmailInboxClient(Protocol):
    def fetch_unseen(self, credentials: dict[str, Any], *, limit: int) -> list[RawEmailMessage]:
        raise NotImplementedError

    def acknowledge(self, credentials: dict[str, Any], uids: list[str]) -> None:
        raise NotImplementedError


class StaticEmailInboxClient:
    def __init__(self, messages: list[RawEmailMessage]):
        self.messages = messages
        self.acknowledged: list[str] = []

    def fetch_unseen(self, credentials: dict[str, Any], *, limit: int) -> list[RawEmailMessage]:
        return self.messages[:limit]

    def acknowledge(self, credentials: dict[str, Any], uids: list[str]) -> None:
        self.acknowledged.extend(uids)


class ImapEmailInboxClient:
    def fetch_unseen(self, credentials: dict[str, Any], *, limit: int) -> list[RawEmailMessage]:
        mailbox = _mailbox(credentials)
        with _imap_connection(credentials) as connection:
            connection.select(mailbox)
            status, data = connection.uid("search", None, "UNSEEN")
            _require_ok(status, "IMAP search failed")
            uids = (data[0] or b"").decode().split()[:limit]
            messages = []
            for uid in uids:
                fetch_status, fetched = connection.uid("fetch", uid, "(RFC822)")
                _require_ok(fetch_status, "IMAP fetch failed")
                raw = _raw_message(fetched)
                if raw:
                    messages.append(RawEmailMessage(uid=uid, raw=raw))
            return messages

    def acknowledge(self, credentials: dict[str, Any], uids: list[str]) -> None:
        if not uids:
            return
        mailbox = _mailbox(credentials)
        with _imap_connection(credentials) as connection:
            connection.select(mailbox)
            for uid in uids:
                status, _ = connection.uid("store", uid, "+FLAGS", "(\\Seen)")
                _require_ok(status, "IMAP acknowledge failed")


def poll_email_channel(
    session: Session,
    seller_id: int,
    channel_account_id: int,
    *,
    client: EmailInboxClient | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    account = session.get(models.ChannelAccount, channel_account_id)
    if account is None or account.seller_id != seller_id or account.channel_type != "email":
        raise LookupError("Email channel account not found")
    credentials = reveal_credentials(account.credentials)
    inbox = client or ImapEmailInboxClient()
    raw_messages = inbox.fetch_unseen(credentials, limit=max(1, min(limit, 100)))

    items = []
    acknowledged: list[str] = []
    for raw_message in raw_messages:
        inbound = EmailAdapter().normalize_raw_email(raw_message.raw)
        inquiry, conversation, message, duplicate = ingest_inbound_message(session, seller_id, inbound)
        acknowledged.append(raw_message.uid)
        items.append(
            {
                "uid": raw_message.uid,
                "inquiry_id": inquiry.id,
                "conversation_id": conversation.id,
                "message_id": message.id,
                "customer_id": inquiry.customer_id,
                "duplicate": duplicate,
            }
        )

    inbox.acknowledge(credentials, acknowledged)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="system",
            action_type="email_poll_completed",
            target_type="channel_account",
            target_id=account.id,
            is_auto=True,
            snapshot={"fetched": len(raw_messages), "acknowledged": len(acknowledged)},
        )
    )
    session.flush()
    return {
        "channel_account_id": account.id,
        "fetched": len(raw_messages),
        "ingested": sum(1 for item in items if not item["duplicate"]),
        "duplicates": sum(1 for item in items if item["duplicate"]),
        "items": items,
    }


def _imap_connection(credentials: dict[str, Any]):
    host = _required(credentials, "host")
    port = int(credentials.get("port") or 993)
    username = _required(credentials, "username")
    password = _required(credentials, "password")
    timeout = float(credentials.get("timeout_seconds") or 10)
    if credentials.get("use_ssl", True):
        connection = imaplib.IMAP4_SSL(host, port, timeout=timeout)
    else:
        connection = imaplib.IMAP4(host, port, timeout=timeout)
    connection.login(username, password)
    return connection


def _mailbox(credentials: dict[str, Any]) -> str:
    return str(credentials.get("mailbox") or "INBOX")


def _raw_message(fetched) -> str | None:
    for part in fetched:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
            return part[1].decode("utf-8", errors="replace")
    return None


def _require_ok(status: str, message: str) -> None:
    if status != "OK":
        raise ValueError(message)


def _required(credentials: dict[str, Any], key: str) -> str:
    value = credentials.get(key)
    if value in (None, ""):
        raise ValueError(f"{key} credential is required")
    return str(value)
