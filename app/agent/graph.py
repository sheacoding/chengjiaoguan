"""
/* ========================================================================== */
/* GEB L3: Agent 八步图组合根                                                 */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 Pydantic Graph、SQLAlchemy Session、app.agent.types、graph_domain.policy 与 graph_domain 八步节点
 * [OUTPUT]: 对外提供八个图节点、closer_operating_graph、run_closer_graph_result、run_closer_graph、closer_graph_mermaid
 * [POS]: app/agent 的编排图组合根，只装配 Graph、运行入口与默认 graph policy provider
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from pydantic_graph.graph import Graph, GraphRunResult
from sqlalchemy.orm import Session

from app.agent.graph_domain.nodes import (
    NegotiateAndAnswer,
    PersistMemory,
    QualifyInquiry,
    ReceiveInquiry,
    ReplyWithQuote,
    RequestHumanHandoff,
    ScheduleFollowup,
    UnderstandRequirement,
)
from app.agent.graph_domain.policy import GraphDecisionProvider, get_graph_decision_provider
from app.agent.types import CloserAgentDeps, CloserAgentOutput, CloserGraphState


closer_operating_graph = Graph(
    nodes=(
        ReceiveInquiry,
        QualifyInquiry,
        UnderstandRequirement,
        ReplyWithQuote,
        NegotiateAndAnswer,
        ScheduleFollowup,
        RequestHumanHandoff,
        PersistMemory,
    ),
    name="closer_operating_graph",
    auto_instrument=False,
)


def run_closer_graph_result(
    session: Session,
    seller_id: int,
    user_prompt: str,
    *,
    inquiry_id: int | None = None,
    conversation_id: int | None = None,
    decision_provider: GraphDecisionProvider | None = None,
) -> GraphRunResult[CloserGraphState, CloserAgentOutput]:
    state = CloserGraphState(user_prompt=user_prompt, inquiry_id=inquiry_id, conversation_id=conversation_id)
    deps = CloserAgentDeps(
        seller_id=seller_id,
        session=session,
        inquiry_id=inquiry_id,
        conversation_id=conversation_id,
        decision_provider=decision_provider or get_graph_decision_provider(),
    )
    return closer_operating_graph.run_sync(ReceiveInquiry(), state=state, deps=deps, infer_name=False)


def run_closer_graph(
    session: Session,
    seller_id: int,
    user_prompt: str,
    *,
    inquiry_id: int | None = None,
    conversation_id: int | None = None,
    decision_provider: GraphDecisionProvider | None = None,
) -> CloserAgentOutput:
    return run_closer_graph_result(
        session,
        seller_id,
        user_prompt,
        inquiry_id=inquiry_id,
        conversation_id=conversation_id,
        decision_provider=decision_provider,
    ).output


def closer_graph_mermaid() -> str:
    return closer_operating_graph.mermaid_code(start_node=ReceiveInquiry, infer_name=False)
