"""
/* ========================================================================== */
/* GEB L3: 投递尝试记录                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session/select、datetime timedelta、app.models、credentials、channel_delivery_clients 与 delivery result
 * [OUTPUT]: 对外提供 list_delivery_attempts、record_delivery_attempt、list_retryable_delivery_attempts、retry_delivery_attempt、run_due_delivery_retries
 * [POS]: services 的出站投递状态机薄层，把一次性 delivery 结果固化为可查询、可重试、可执行的记录
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.database import utcnow
from app.services.channel_delivery_clients import send_with_delivery_client
from app.services.credentials import reveal_credentials


DEFAULT_RETRY_DELAY = timedelta(minutes=5)


def list_delivery_attempts(
    session: Session,
    seller_id: int,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[models.DeliveryAttempt], int, int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    query = select(models.DeliveryAttempt).where(models.DeliveryAttempt.seller_id == seller_id)
    if status:
        query = query.where(models.DeliveryAttempt.status == status)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    attempts = session.scalars(
        query.order_by(models.DeliveryAttempt.created_at.desc(), models.DeliveryAttempt.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return attempts, total, page, page_size


def record_delivery_attempt(
    session: Session,
    seller_id: int,
    message: models.Message,
    result: dict[str, Any],
) -> models.DeliveryAttempt:
    client = result.get("client") if isinstance(result.get("client"), dict) else {}
    status = str(result.get("status") or client.get("status") or "queued")
    attempt = models.DeliveryAttempt(
        seller_id=seller_id,
        message_id=message.id,
        channel_account_id=result.get("channel_account_id"),
        channel=str(result.get("channel") or "unknown"),
        external_id=str(result.get("external_id") or message.channel_message_id or ""),
        status=status,
        client=client.get("client"),
        provider_message_id=client.get("provider_message_id"),
        attempt_count=1,
        next_retry_at=utcnow() + DEFAULT_RETRY_DELAY if status == "failed" else None,
        error=client.get("error") or result.get("reason"),
        payload=result.get("payload") or {},
        response=client,
    )
    session.add(attempt)
    session.flush()
    return attempt


def list_retryable_delivery_attempts(
    session: Session,
    seller_id: int,
    *,
    limit: int = 50,
    now=None,
) -> list[models.DeliveryAttempt]:
    checkpoint = now or utcnow()
    return session.scalars(
        select(models.DeliveryAttempt)
        .where(models.DeliveryAttempt.seller_id == seller_id)
        .where(models.DeliveryAttempt.status == "failed")
        .where(models.DeliveryAttempt.next_retry_at.is_not(None))
        .where(models.DeliveryAttempt.next_retry_at <= checkpoint)
        .order_by(models.DeliveryAttempt.next_retry_at.asc(), models.DeliveryAttempt.id.asc())
        .limit(limit)
    ).all()


def retry_delivery_attempt(session: Session, seller_id: int, attempt_id: int) -> dict[str, Any]:
    attempt = session.get(models.DeliveryAttempt, attempt_id)
    if attempt is None or attempt.seller_id != seller_id:
        raise LookupError("Delivery attempt not found")
    if attempt.status != "failed":
        return _attempt_result(attempt, skipped=True)

    credentials = _attempt_credentials(session, attempt)
    client = _send_client(attempt.channel, attempt.payload or {}, credentials)
    _apply_retry_result(attempt, client)
    session.flush()
    return _attempt_result(attempt)


def run_due_delivery_retries(
    session: Session,
    seller_id: int,
    *,
    limit: int = 50,
    now=None,
) -> list[dict[str, Any]]:
    attempts = list_retryable_delivery_attempts(session, seller_id, limit=limit, now=now)
    return [retry_delivery_attempt(session, seller_id, attempt.id) for attempt in attempts]


def _apply_retry_result(attempt: models.DeliveryAttempt, client: dict[str, Any]) -> None:
    status = str(client.get("status") or "failed")
    attempt.attempt_count += 1
    attempt.status = status
    attempt.client = client.get("client")
    attempt.provider_message_id = client.get("provider_message_id")
    attempt.response = client
    attempt.error = client.get("error")
    attempt.next_retry_at = utcnow() + DEFAULT_RETRY_DELAY if status == "failed" else None


def _send_client(channel: str, payload: dict[str, Any], credentials: dict[str, Any]) -> dict[str, Any]:
    try:
        return send_with_delivery_client(channel, payload, credentials)
    except Exception as exc:
        return {"status": "failed", "client": "delivery_client", "error": str(exc)}


def _attempt_credentials(session: Session, attempt: models.DeliveryAttempt) -> dict[str, Any]:
    if attempt.channel_account_id is None:
        return {}
    account = session.get(models.ChannelAccount, attempt.channel_account_id)
    if account is None:
        return {}
    return reveal_credentials(account.credentials)


def _attempt_result(attempt: models.DeliveryAttempt, *, skipped: bool = False) -> dict[str, Any]:
    return {
        "delivery_attempt_id": attempt.id,
        "message_id": attempt.message_id,
        "status": attempt.status,
        "channel": attempt.channel,
        "attempt_count": attempt.attempt_count,
        "next_retry_at": attempt.next_retry_at,
        "client": attempt.client,
        "provider_message_id": attempt.provider_message_id,
        "error": attempt.error,
        "skipped": skipped,
    }
