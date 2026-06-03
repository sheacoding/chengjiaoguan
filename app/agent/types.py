"""
/* ========================================================================== */
/* GEB L3: Agent 类型契约                                                     */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 dataclasses、typing.Any/TYPE_CHECKING、graph_domain.policy、Pydantic BaseModel/Field 与 SQLAlchemy Session
 * [OUTPUT]: 对外提供 CloserAgentDeps、CloserAgentOutput、CloserGraphState
 * [POS]: app/agent 的状态真源，供 PydanticAI 工具绑定、Graph policy 注入与 Pydantic Graph 节点共享
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session


if TYPE_CHECKING:
    from app.agent.graph_domain.policy import GraphDecisionProvider


@dataclass
class CloserAgentDeps:
    seller_id: int
    session: Session
    inquiry_id: int | None = None
    conversation_id: int | None = None
    decision_provider: GraphDecisionProvider | None = None


class CloserAgentOutput(BaseModel):
    summary: str = Field(description="Concise result or recommendation for the seller.")
    draft_response: str | None = Field(default=None, description="Draft customer-facing response when useful.")
    next_actions: list[str] = Field(
        default_factory=list,
        description="Operational actions the seller or system should take.",
    )
    requires_human_review: bool = Field(
        default=False,
        description="Whether the next action must wait for human approval.",
    )


@dataclass
class CloserGraphState:
    user_prompt: str
    inquiry_id: int | None = None
    conversation_id: int | None = None
    steps: list[str] = field(default_factory=list)
    inquiry: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    customer: dict[str, Any] | None = None
    product_matches: list[dict[str, Any]] = field(default_factory=list)
    knowledge: list[dict[str, Any]] = field(default_factory=list)
    quote: dict[str, Any] | None = None
    send_result: dict[str, Any] | None = None
    followup: dict[str, Any] | None = None
    handoff: dict[str, Any] | None = None
    draft_response: str | None = None
    requires_human_review: bool = False
    handoff_reason: str | None = None
    handoff_summary: str | None = None
    handoff_suggestion: str | None = None
    handoff_payload: dict[str, Any] | None = None
    policy_decisions: list[dict[str, Any]] = field(default_factory=list)
