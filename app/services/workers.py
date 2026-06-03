"""
/* ========================================================================== */
/* GEB L3: 后台任务统一调度边界                                               */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、ChannelAccount、credentials、followups、delivery_attempts、email_polling 与 pricing 服务
 * [OUTPUT]: 对外提供 run_due_jobs，统一执行到期 follow-up、投递重试、显式启用的 email 轮询与价格规则汇率刷新
 * [POS]: services 的 deterministic worker 薄层，给外部 cron/queue/API 一个稳定入口
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.catalog_domain.pricing import run_due_pricing_rule_exchange_rate_refreshes
from app.services.credentials import reveal_credentials
from app.services.delivery_attempts import run_due_delivery_retries
from app.services.email_polling import EmailInboxClient, poll_email_channel
from app.services.followups import run_due_followups


EmailClientFactory = Callable[[models.ChannelAccount], EmailInboxClient | None]


def run_due_jobs(
    session: Session,
    seller_id: int,
    *,
    followup_limit: int = 50,
    delivery_retry_limit: int = 50,
    email_channel_limit: int = 20,
    email_message_limit: int = 20,
    pricing_exchange_rate_limit: int = 20,
    email_client_factory: EmailClientFactory | None = None,
) -> dict[str, Any]:
    followups = run_due_followups(session, seller_id=seller_id, limit=followup_limit)
    delivery_retries = run_due_delivery_retries(session, seller_id, limit=delivery_retry_limit)
    pricing_exchange_rate_refreshes = run_due_pricing_rule_exchange_rate_refreshes(
        session,
        seller_id,
        limit=pricing_exchange_rate_limit,
    )
    email_polls = _run_email_polls(
        session,
        seller_id,
        channel_limit=email_channel_limit,
        message_limit=email_message_limit,
        client_factory=email_client_factory,
    )
    return {
        "followups": _bucket(followups),
        "delivery_retries": _bucket(delivery_retries),
        "pricing_exchange_rate_refreshes": _bucket(pricing_exchange_rate_refreshes),
        "email_polls": _bucket(email_polls),
        "total_jobs": len(followups) + len(delivery_retries) + len(pricing_exchange_rate_refreshes) + len(email_polls),
    }


def _run_email_polls(
    session: Session,
    seller_id: int,
    *,
    channel_limit: int,
    message_limit: int,
    client_factory: EmailClientFactory | None,
) -> list[dict[str, Any]]:
    results = []
    for account in _connected_email_channels(session, seller_id, channel_limit):
        try:
            if not _polling_enabled(account):
                continue
            client = client_factory(account) if client_factory else None
            poll = poll_email_channel(session, seller_id, account.id, client=client, limit=message_limit)
            results.append({"status": "ok"} | poll)
        except Exception as exc:
            results.append({"channel_account_id": account.id, "status": "failed", "error": str(exc)})
    return results


def _connected_email_channels(session: Session, seller_id: int, limit: int) -> list[models.ChannelAccount]:
    return session.scalars(
        select(models.ChannelAccount)
        .where(models.ChannelAccount.seller_id == seller_id)
        .where(models.ChannelAccount.channel_type == "email")
        .where(models.ChannelAccount.status == "connected")
        .order_by(models.ChannelAccount.id.asc())
        .limit(min(max(limit, 1), 100))
    ).all()


def _polling_enabled(account: models.ChannelAccount) -> bool:
    credentials = reveal_credentials(account.credentials)
    return bool(credentials.get("poll_enabled") or credentials.get("polling_enabled"))


def _bucket(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": items, "total": len(items)}
