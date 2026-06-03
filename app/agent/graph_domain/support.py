"""
/* ========================================================================== */
/* GEB L3: Agent 图辅助函数                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 Pydantic GraphRunContext、app.models、graph_domain.policy 与 app.agent.types 的状态/输出契约
 * [OUTPUT]: 对外提供 resolve_graph_ids、record_step、policy_decision、apply_policy_decision、need_handoff、query_text、fallback_response、graph_output
 * [POS]: app/agent/graph_domain 的共享状态转换层，避免节点文件重复处理图上下文细节
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from typing import Any

from pydantic_graph import GraphRunContext

from app import models
from app.agent.graph_domain.policy import GraphPolicyContext, GraphPolicyDecision, RuleBasedGraphDecisionProvider
from app.agent.types import CloserAgentDeps, CloserAgentOutput, CloserGraphState


DEFAULT_DECISION_PROVIDER = RuleBasedGraphDecisionProvider()


def resolve_graph_ids(ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> None:
    if ctx.state.inquiry_id is None:
        ctx.state.inquiry_id = ctx.deps.inquiry_id
    if ctx.state.conversation_id is None:
        ctx.state.conversation_id = ctx.deps.conversation_id
    if ctx.state.inquiry_id is None and ctx.state.conversation_id is not None:
        conversation = ctx.deps.session.get(models.Conversation, ctx.state.conversation_id)
        if conversation is not None and conversation.seller_id == ctx.deps.seller_id:
            ctx.state.inquiry_id = conversation.inquiry_id


def record_step(ctx: GraphRunContext[CloserGraphState, CloserAgentDeps], name: str) -> None:
    ctx.state.steps.append(name)


def policy_decision(
    ctx: GraphRunContext[CloserGraphState, CloserAgentDeps],
    stage: str,
    *,
    extra: dict[str, Any] | None = None,
) -> GraphPolicyDecision:
    provider = ctx.deps.decision_provider or DEFAULT_DECISION_PROVIDER
    decision = provider.decide(
        GraphPolicyContext(
            stage=stage,
            seller_id=ctx.deps.seller_id,
            user_prompt=ctx.state.user_prompt,
            inquiry_id=ctx.state.inquiry_id,
            conversation_id=ctx.state.conversation_id,
            inquiry=ctx.state.inquiry,
            score=ctx.state.score,
            product_matches=ctx.state.product_matches,
            knowledge=ctx.state.knowledge,
            extra=extra or {},
        )
    )
    snapshot = decision.snapshot()
    snapshot["stage"] = stage
    snapshot["provider"] = provider.name
    ctx.state.policy_decisions.append(snapshot)
    return decision


def apply_policy_decision(
    ctx: GraphRunContext[CloserGraphState, CloserAgentDeps],
    decision: GraphPolicyDecision,
) -> bool:
    if decision.draft_response:
        ctx.state.draft_response = decision.draft_response
    if not decision.requires_human_review:
        return False
    need_handoff(
        ctx,
        decision.handoff_reason or "graph_policy_handoff",
        decision.handoff_summary or "Graph decision policy requested human review.",
        suggestion=decision.handoff_suggestion,
        payload=dict(decision.handoff_payload or {}),
    )
    return True


def need_handoff(
    ctx: GraphRunContext[CloserGraphState, CloserAgentDeps],
    reason: str,
    summary: str,
    *,
    suggestion: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    ctx.state.requires_human_review = True
    ctx.state.handoff_reason = reason
    ctx.state.handoff_summary = summary
    ctx.state.handoff_suggestion = suggestion
    ctx.state.handoff_payload = payload


def query_text(requirement: str | dict[str, Any]) -> str:
    if isinstance(requirement, str):
        return requirement
    return " ".join(str(value) for value in requirement.values() if value)


def fallback_response(ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> str:
    if ctx.state.knowledge:
        return f"Thanks for your inquiry. Based on our available information: {ctx.state.knowledge[0]['content']}"
    return "Thanks for your inquiry. We have received your request and will confirm the best option shortly."


def graph_output(state: CloserGraphState) -> CloserAgentOutput:
    next_actions = list(state.steps)
    if state.requires_human_review and "approve_or_edit_handoff" not in next_actions:
        next_actions.append("approve_or_edit_handoff")
    if state.followup and "wait_for_followup" not in next_actions:
        next_actions.append("wait_for_followup")

    if state.requires_human_review:
        summary = state.handoff_summary or "Human review is required before continuing."
    elif state.send_result:
        summary = "Inquiry was scored, matched, quoted, answered, and scheduled for follow-up."
    else:
        summary = "Inquiry was processed through the operating graph."

    return CloserAgentOutput(
        summary=summary,
        draft_response=state.draft_response,
        next_actions=next_actions,
        requires_human_review=state.requires_human_review,
    )
