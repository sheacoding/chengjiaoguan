"""
/* ========================================================================== */
/* GEB L3: Agent 工具绑定                                                     */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 PydanticAI RunContext、app.agent.types.CloserAgentDeps 与 app.agent_tools 稳定服务门面
 * [OUTPUT]: 对外提供 get_inquiry、score_inquiry、get_customer、calc_quote、generate_pi、search_knowledge、match_product、send_message、create_followup、request_handoff、CLOSER_AGENT_TOOLS
 * [POS]: app/agent 的 PydanticAI 工具适配层，只把 RunContext 解包为稳定工具签名
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext

from app import agent_tools
from app.agent.types import CloserAgentDeps


def get_inquiry(ctx: RunContext[CloserAgentDeps], inquiry_id: int | None = None) -> dict:
    target_id = _resolve_inquiry_id(ctx, inquiry_id)
    return agent_tools.get_inquiry(ctx.deps.session, ctx.deps.seller_id, target_id)


def score_inquiry(ctx: RunContext[CloserAgentDeps], inquiry_id: int | None = None) -> dict:
    target_id = _resolve_inquiry_id(ctx, inquiry_id)
    return agent_tools.score_inquiry(ctx.deps.session, ctx.deps.seller_id, target_id)


def get_customer(
    ctx: RunContext[CloserAgentDeps],
    customer_id: int | None = None,
    inquiry_id: int | None = None,
) -> dict:
    return agent_tools.get_customer(
        ctx.deps.session,
        ctx.deps.seller_id,
        customer_id=customer_id,
        inquiry_id=inquiry_id or ctx.deps.inquiry_id,
    )


def calc_quote(
    ctx: RunContext[CloserAgentDeps],
    items: list[dict[str, Any]],
    inquiry_id: int | None = None,
    destination: str | None = None,
    currency: str = "USD",
) -> dict:
    target_id = _resolve_inquiry_id(ctx, inquiry_id)
    return agent_tools.calc_quote(
        ctx.deps.session,
        ctx.deps.seller_id,
        target_id,
        items,
        destination=destination,
        currency=currency,
    )


def generate_pi(ctx: RunContext[CloserAgentDeps], quotation_id: int) -> dict:
    return agent_tools.generate_pi(ctx.deps.session, ctx.deps.seller_id, quotation_id)


def search_knowledge(
    ctx: RunContext[CloserAgentDeps],
    query: str,
    source_type: str | None = None,
    limit: int = 5,
) -> list[dict]:
    return agent_tools.search_knowledge(
        ctx.deps.session,
        ctx.deps.seller_id,
        query,
        source_type=source_type,
        limit=limit,
    )


def match_product(
    ctx: RunContext[CloserAgentDeps],
    requirement: str | dict[str, Any],
    limit: int = 5,
) -> list[dict]:
    return agent_tools.match_product(
        ctx.deps.session,
        ctx.deps.seller_id,
        requirement,
        limit=limit,
    )


def send_message(
    ctx: RunContext[CloserAgentDeps],
    content: str,
    conversation_id: int | None = None,
    language: str | None = None,
) -> dict:
    target_id = conversation_id or ctx.deps.conversation_id
    if target_id is None:
        raise ValueError("conversation_id is required")
    return agent_tools.send_message(
        ctx.deps.session,
        ctx.deps.seller_id,
        target_id,
        content,
        language=language,
    )


def create_followup(
    ctx: RunContext[CloserAgentDeps],
    inquiry_id: int | None = None,
    conversation_id: int | None = None,
    delay_hours: int = 24,
    message: str | None = None,
    max_attempts: int = 3,
) -> dict:
    return agent_tools.create_followup(
        ctx.deps.session,
        ctx.deps.seller_id,
        _resolve_inquiry_id(ctx, inquiry_id),
        conversation_id=conversation_id or ctx.deps.conversation_id,
        delay_hours=delay_hours,
        message=message,
        max_attempts=max_attempts,
    )


def request_handoff(
    ctx: RunContext[CloserAgentDeps],
    reason: str,
    summary: str,
    conversation_id: int | None = None,
    suggestion: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict:
    target_id = conversation_id or ctx.deps.conversation_id
    if target_id is None:
        raise ValueError("conversation_id is required")
    return agent_tools.request_handoff(
        ctx.deps.session,
        ctx.deps.seller_id,
        target_id,
        reason,
        summary,
        suggestion=suggestion,
        payload=payload,
    )


CLOSER_AGENT_TOOLS = [
    get_inquiry,
    score_inquiry,
    get_customer,
    calc_quote,
    generate_pi,
    search_knowledge,
    match_product,
    send_message,
    create_followup,
    request_handoff,
]


def _resolve_inquiry_id(ctx: RunContext[CloserAgentDeps], inquiry_id: int | None) -> int:
    target_id = inquiry_id or ctx.deps.inquiry_id
    if target_id is None:
        raise ValueError("inquiry_id is required")
    return target_id
