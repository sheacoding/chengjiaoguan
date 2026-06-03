"""
/* ========================================================================== */
/* GEB L3: 渠道账号服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session/select、app.models、ensure_seller 与 credentials seal/rotation 服务
 * [OUTPUT]: 对外提供 list_channels、create_channel、rotate_channel_credentials
 * [POS]: services/catalog_domain 的渠道配置真源，管理 channel_account、凭据封存与 seal secret 轮换
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.channel_gateway import ensure_seller
from app.services.credentials import rotate_credentials_seal, seal_credentials


def list_channels(session: Session, seller_id: int) -> list[models.ChannelAccount]:
    return session.scalars(
        select(models.ChannelAccount)
        .where(models.ChannelAccount.seller_id == seller_id)
        .order_by(models.ChannelAccount.id.desc())
    ).all()


def create_channel(session: Session, seller_id: int, data: dict[str, Any]) -> models.ChannelAccount:
    ensure_seller(session, seller_id)
    account = models.ChannelAccount(
        seller_id=seller_id,
        channel_type=data["channel_type"],
        name=data.get("name"),
        credentials=seal_credentials(data.get("credentials")),
        status=data.get("status") or "connected",
    )
    session.add(account)
    session.flush()
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="human",
            action_type="channel_connected",
            target_type="channel_account",
            target_id=account.id,
            is_auto=False,
            snapshot={"channel_type": account.channel_type, "status": account.status},
        )
    )
    return account


def rotate_channel_credentials(session: Session, seller_id: int, channel_account_id: int) -> tuple[models.ChannelAccount, bool]:
    account = session.get(models.ChannelAccount, channel_account_id)
    if account is None or account.seller_id != seller_id:
        raise LookupError("Channel not found")
    rotated_credentials, rotated = rotate_credentials_seal(account.credentials)
    account.credentials = rotated_credentials
    if rotated:
        session.add(
            models.AuditLog(
                seller_id=seller_id,
                actor="human",
                action_type="channel_credentials_rotated",
                target_type="channel_account",
                target_id=account.id,
                is_auto=False,
                snapshot={"channel_type": account.channel_type, "rotated": True},
            )
        )
    session.flush()
    return account, rotated
