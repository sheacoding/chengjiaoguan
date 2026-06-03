"""
/* ========================================================================== */
/* GEB L3: Agent 运行入口                                                     */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 PydanticAI Agent、SQLAlchemy Session、app.agent.model_config、app.agent.types 与 app.agent.tools
 * [OUTPUT]: 对外提供 build_closer_agent、closer_agent、run_closer_agent，运行时可用显式 model 或 CLOSER_AGENT_MODEL
 * [POS]: app/agent 的 PydanticAI 组合根，负责模型运行入口和模型选择，不承载图节点逻辑
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from sqlalchemy.orm import Session

from app.agent.model_config import selected_agent_model
from app.agent.tools import CLOSER_AGENT_TOOLS
from app.agent.types import CloserAgentDeps, CloserAgentOutput


def build_closer_agent(model: str | None = None) -> Agent[CloserAgentDeps, CloserAgentOutput]:
    return Agent(
        model,
        deps_type=CloserAgentDeps,
        output_type=CloserAgentOutput,
        instructions=(
            "You are the operating agent for a cross-border B2B seller. "
            "Use tools before making factual claims about inquiries, customers, or quotes. "
            "Never promise discounts, payment terms, delivery guarantees, or legal commitments "
            "unless a tool result explicitly supports them. Return structured output only."
        ),
        tools=CLOSER_AGENT_TOOLS,
    )


closer_agent = build_closer_agent()


def run_closer_agent(
    session: Session,
    seller_id: int,
    user_prompt: str,
    *,
    inquiry_id: int | None = None,
    conversation_id: int | None = None,
    model: Any | None = None,
) -> CloserAgentOutput:
    runtime_model = selected_agent_model(model)
    result = closer_agent.run_sync(
        user_prompt,
        deps=CloserAgentDeps(
            seller_id=seller_id,
            session=session,
            inquiry_id=inquiry_id,
            conversation_id=conversation_id,
        ),
        model=runtime_model,
    )
    return result.output
