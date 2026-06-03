"""
/* ========================================================================== */
/* GEB L3: Agent 八步图节点                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 Pydantic Graph BaseNode/End、app.agent_tools、app.agent.types 与 graph_domain.support/policy
 * [OUTPUT]: 对外提供 ReceiveInquiry、QualifyInquiry、UnderstandRequirement、ReplyWithQuote、NegotiateAndAnswer、ScheduleFollowup、RequestHumanHandoff、PersistMemory
 * [POS]: app/agent/graph_domain 的节点层，只表达节点跳转、工具调用、policy 消费与状态写入
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from app import agent_tools
from app.agent.graph_domain.support import (
    apply_policy_decision,
    fallback_response,
    graph_output,
    need_handoff,
    policy_decision,
    query_text,
    record_step,
    resolve_graph_ids,
)
from app.agent.types import CloserAgentDeps, CloserAgentOutput, CloserGraphState


@dataclass
class ReceiveInquiry(BaseNode[CloserGraphState, CloserAgentDeps, CloserAgentOutput]):
    async def run(self, ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> QualifyInquiry:
        record_step(ctx, "receive")
        resolve_graph_ids(ctx)
        if ctx.state.inquiry_id is not None:
            ctx.state.inquiry = agent_tools.get_inquiry(ctx.deps.session, ctx.deps.seller_id, ctx.state.inquiry_id)
        return QualifyInquiry()


@dataclass
class QualifyInquiry(BaseNode[CloserGraphState, CloserAgentDeps, CloserAgentOutput]):
    async def run(self, ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> UnderstandRequirement | RequestHumanHandoff:
        record_step(ctx, "qualify")
        if ctx.state.inquiry_id is None:
            need_handoff(ctx, "missing_inquiry", "No inquiry is attached to this graph run.")
            return RequestHumanHandoff()
        ctx.state.score = agent_tools.score_inquiry(ctx.deps.session, ctx.deps.seller_id, ctx.state.inquiry_id)
        if apply_policy_decision(ctx, policy_decision(ctx, "qualify")):
            return RequestHumanHandoff()
        return UnderstandRequirement()


@dataclass
class UnderstandRequirement(BaseNode[CloserGraphState, CloserAgentDeps, CloserAgentOutput]):
    async def run(self, ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> ReplyWithQuote | RequestHumanHandoff:
        record_step(ctx, "understand")
        inquiry = ctx.state.inquiry or {}
        parsed = inquiry.get("parsed") or {}
        requirement = parsed or inquiry.get("raw_summary") or ctx.state.user_prompt

        try:
            ctx.state.product_matches = agent_tools.match_product(ctx.deps.session, ctx.deps.seller_id, requirement)
        except ValueError:
            ctx.state.product_matches = []

        decision = policy_decision(ctx, "understand", extra={"requirement": requirement})
        query = decision.knowledge_query or query_text(requirement)
        if query:
            try:
                ctx.state.knowledge = agent_tools.search_knowledge(ctx.deps.session, ctx.deps.seller_id, query, limit=3)
            except ValueError:
                ctx.state.knowledge = []

        if apply_policy_decision(ctx, decision):
            return RequestHumanHandoff()
        return ReplyWithQuote()


@dataclass
class ReplyWithQuote(BaseNode[CloserGraphState, CloserAgentDeps, CloserAgentOutput]):
    async def run(self, ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> NegotiateAndAnswer | RequestHumanHandoff:
        record_step(ctx, "quote")
        inquiry = ctx.state.inquiry or {}
        parsed = inquiry.get("parsed") or {}
        quantity = parsed.get("quantity")
        decision = policy_decision(ctx, "quote")
        if apply_policy_decision(ctx, decision):
            return RequestHumanHandoff()
        if decision.should_quote and ctx.state.inquiry_id is not None and quantity and ctx.state.product_matches:
            product_id = int(ctx.state.product_matches[0]["product_id"])
            try:
                ctx.state.quote = agent_tools.calc_quote(
                    ctx.deps.session,
                    ctx.deps.seller_id,
                    ctx.state.inquiry_id,
                    [{"product_id": product_id, "quantity": int(quantity)}],
                    destination=parsed.get("destination"),
                )
            except (LookupError, ValueError) as exc:
                need_handoff(ctx, "quote_unavailable", str(exc), payload={"parsed": parsed})
                return RequestHumanHandoff()

            ctx.state.draft_response = ctx.state.quote["message"]
            if ctx.state.quote["hits_floor"]:
                need_handoff(
                    ctx,
                    "below_floor_price",
                    "Calculated quote hits the configured floor price guardrail.",
                    suggestion=ctx.state.draft_response,
                    payload={"quotation_id": ctx.state.quote["quotation_id"]},
                )
                return RequestHumanHandoff()

        if ctx.state.draft_response is None:
            ctx.state.draft_response = fallback_response(ctx)
        return NegotiateAndAnswer()


@dataclass
class NegotiateAndAnswer(BaseNode[CloserGraphState, CloserAgentDeps, CloserAgentOutput]):
    async def run(self, ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> ScheduleFollowup | RequestHumanHandoff | PersistMemory:
        record_step(ctx, "answer")
        if apply_policy_decision(ctx, policy_decision(ctx, "answer")):
            return RequestHumanHandoff()
        if ctx.state.conversation_id is None or not ctx.state.draft_response:
            return PersistMemory()
        result = agent_tools.send_message(
            ctx.deps.session,
            ctx.deps.seller_id,
            ctx.state.conversation_id,
            ctx.state.draft_response,
            language=(ctx.state.inquiry or {}).get("language"),
        )
        if result["status"] == "pending_approval":
            ctx.state.handoff = result
            ctx.state.requires_human_review = True
            ctx.state.handoff_reason = result["reason"]
            return PersistMemory()
        ctx.state.send_result = result
        return ScheduleFollowup()


@dataclass
class ScheduleFollowup(BaseNode[CloserGraphState, CloserAgentDeps, CloserAgentOutput]):
    async def run(self, ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> PersistMemory:
        record_step(ctx, "followup")
        if ctx.state.inquiry_id is not None and ctx.state.conversation_id is not None and ctx.state.send_result:
            ctx.state.followup = agent_tools.create_followup(
                ctx.deps.session,
                ctx.deps.seller_id,
                ctx.state.inquiry_id,
                conversation_id=ctx.state.conversation_id,
                delay_hours=24,
            )
        return PersistMemory()


@dataclass
class RequestHumanHandoff(BaseNode[CloserGraphState, CloserAgentDeps, CloserAgentOutput]):
    async def run(self, ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> PersistMemory:
        record_step(ctx, "handoff")
        ctx.state.requires_human_review = True
        if ctx.state.handoff is None and ctx.state.conversation_id is not None:
            ctx.state.handoff = agent_tools.request_handoff(
                ctx.deps.session,
                ctx.deps.seller_id,
                ctx.state.conversation_id,
                ctx.state.handoff_reason or "human_review_required",
                ctx.state.handoff_summary or "Human review is required before the AI continues.",
                suggestion=ctx.state.handoff_suggestion,
                payload=ctx.state.handoff_payload,
            )
        return PersistMemory()


@dataclass
class PersistMemory(BaseNode[CloserGraphState, CloserAgentDeps, CloserAgentOutput]):
    async def run(self, ctx: GraphRunContext[CloserGraphState, CloserAgentDeps]) -> End[CloserAgentOutput]:
        record_step(ctx, "persist")
        if ctx.state.inquiry_id is not None:
            try:
                ctx.state.customer = agent_tools.get_customer(
                    ctx.deps.session,
                    ctx.deps.seller_id,
                    inquiry_id=ctx.state.inquiry_id,
                )
            except LookupError:
                ctx.state.customer = None
        return End(graph_output(ctx.state))
