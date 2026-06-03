"""
/* ========================================================================== */
/* GEB L3: 渠道投递回执同步                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session/select、app.models、utcnow、delivery_attempts.DEFAULT_RETRY_DELAY 与渠道回执 payload
 * [OUTPUT]: 对外提供 sync_channel_receipts，把 WhatsApp/email/provider 回执同步到 delivery_attempt 状态与 response.receipts
 * [POS]: services 的出站回执状态机薄层，让外部渠道状态回声回到统一投递记录
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow
from app.services.delivery_attempts import DEFAULT_RETRY_DELAY


STATUS_MAP = {
    "accepted": "queued",
    "queued": "queued",
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "opened": "read",
    "clicked": "read",
    "failed": "failed",
    "undelivered": "failed",
    "bounced": "failed",
}


@dataclass(frozen=True)
class DeliveryReceipt:
    provider_message_id: str | None
    external_id: str | None
    status: str
    raw_status: str
    occurred_at: str | None
    error: str | None
    raw: dict[str, Any]


def sync_channel_receipts(
    session: Session,
    seller_id: int,
    channel_account_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    account = session.get(models.ChannelAccount, channel_account_id)
    if account is None or account.seller_id != seller_id:
        raise LookupError("Channel account not found")

    receipts = _normalize_receipts(account.channel_type, payload)
    items = []
    for receipt in receipts:
        attempt = _find_attempt(session, seller_id, account, receipt)
        if attempt is None:
            items.append(_receipt_result(receipt, matched=False))
            continue
        _apply_receipt(attempt, receipt)
        items.append(_receipt_result(receipt, matched=True, attempt=attempt))

    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="system",
            action_type="delivery_receipts_synced",
            target_type="channel_account",
            target_id=account.id,
            is_auto=True,
            snapshot={"received": len(receipts), "matched": sum(1 for item in items if item["matched"])},
        )
    )
    session.flush()
    return {
        "channel_account_id": account.id,
        "channel_type": account.channel_type,
        "received": len(receipts),
        "matched": sum(1 for item in items if item["matched"]),
        "unmatched": sum(1 for item in items if not item["matched"]),
        "items": items,
    }


def _normalize_receipts(channel_type: str, payload: dict[str, Any]) -> list[DeliveryReceipt]:
    if channel_type == "whatsapp":
        return _whatsapp_receipts(payload)
    return _generic_receipts(payload)


def _whatsapp_receipts(payload: dict[str, Any]) -> list[DeliveryReceipt]:
    receipts = []
    for status in _whatsapp_statuses(payload):
        raw_status = str(status.get("status") or "")
        receipts.append(
            DeliveryReceipt(
                provider_message_id=_clean(status.get("id")),
                external_id=_clean(status.get("biz_opaque_callback_data") or status.get("external_id")),
                status=_canonical_status(raw_status),
                raw_status=raw_status,
                occurred_at=_clean(status.get("timestamp")),
                error=_whatsapp_error(status),
                raw=status,
            )
        )
    return receipts


def _generic_receipts(payload: dict[str, Any]) -> list[DeliveryReceipt]:
    values = payload.get("receipts")
    if values is None:
        values = payload.get("events")
    if values is None:
        values = [payload]
    if not isinstance(values, list):
        raise ValueError("receipt payload must contain a list of receipts")

    receipts = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("receipt item must be an object")
        raw_status = str(value.get("status") or value.get("event") or "")
        receipts.append(
            DeliveryReceipt(
                provider_message_id=_clean(value.get("provider_message_id") or value.get("message_id")),
                external_id=_clean(value.get("external_id") or value.get("channel_message_id")),
                status=_canonical_status(raw_status),
                raw_status=raw_status,
                occurred_at=_clean(value.get("occurred_at") or value.get("timestamp")),
                error=_clean(value.get("error") or value.get("reason")),
                raw=value,
            )
        )
    return receipts


def _whatsapp_statuses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            statuses.extend(status for status in (value.get("statuses") or []) if isinstance(status, dict))
    if statuses:
        return statuses
    direct = payload.get("statuses")
    if isinstance(direct, list):
        return [status for status in direct if isinstance(status, dict)]
    raise ValueError("WhatsApp receipt payload does not contain statuses")


def _find_attempt(
    session: Session,
    seller_id: int,
    account: models.ChannelAccount,
    receipt: DeliveryReceipt,
) -> models.DeliveryAttempt | None:
    filters = []
    if receipt.provider_message_id:
        filters.append(models.DeliveryAttempt.provider_message_id == receipt.provider_message_id)
    if receipt.external_id:
        filters.append(models.DeliveryAttempt.external_id == receipt.external_id)
    if not filters:
        return None
    return session.scalar(
        select(models.DeliveryAttempt)
        .where(models.DeliveryAttempt.seller_id == seller_id)
        .where(models.DeliveryAttempt.channel == account.channel_type)
        .where(
            or_(
                models.DeliveryAttempt.channel_account_id == account.id,
                models.DeliveryAttempt.channel_account_id.is_(None),
            )
        )
        .where(or_(*filters))
        .order_by(models.DeliveryAttempt.id.desc())
        .limit(1)
    )


def _apply_receipt(attempt: models.DeliveryAttempt, receipt: DeliveryReceipt) -> None:
    response = dict(attempt.response or {})
    receipts = list(response.get("receipts") or [])
    receipts.append(_receipt_snapshot(receipt))
    response["receipts"] = receipts
    attempt.response = response
    attempt.status = receipt.status
    attempt.error = receipt.error if receipt.status == "failed" else None
    attempt.next_retry_at = utcnow() + DEFAULT_RETRY_DELAY if receipt.status == "failed" else None


def _receipt_result(
    receipt: DeliveryReceipt,
    *,
    matched: bool,
    attempt: models.DeliveryAttempt | None = None,
) -> dict[str, Any]:
    return {
        "matched": matched,
        "delivery_attempt_id": attempt.id if attempt else None,
        "provider_message_id": receipt.provider_message_id,
        "external_id": receipt.external_id,
        "status": receipt.status,
        "raw_status": receipt.raw_status,
        "error": receipt.error,
    }


def _receipt_snapshot(receipt: DeliveryReceipt) -> dict[str, Any]:
    return {
        "provider_message_id": receipt.provider_message_id,
        "external_id": receipt.external_id,
        "status": receipt.status,
        "raw_status": receipt.raw_status,
        "occurred_at": receipt.occurred_at,
        "error": receipt.error,
        "raw": receipt.raw,
    }


def _canonical_status(value: str) -> str:
    status = STATUS_MAP.get(value.lower())
    if status is None:
        raise ValueError(f"Unsupported receipt status: {value}")
    return status


def _whatsapp_error(status: dict[str, Any]) -> str | None:
    errors = status.get("errors") or []
    if not errors:
        return None
    first = errors[0] if isinstance(errors[0], dict) else {}
    return _clean(first.get("message") or first.get("title") or first.get("code"))


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
