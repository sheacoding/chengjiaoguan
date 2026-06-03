"""
/* ========================================================================== */
/* GEB L3: Agent 图子域入口                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 app.agent.graph_domain.nodes 与 support 的公共导出
 * [OUTPUT]: 对外提供八步节点与 graph_support helper
 * [POS]: app/agent/graph_domain 的稳定入口，供 app.agent.graph 组合根使用
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

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
from app.agent.graph_domain.support import fallback_response, graph_output, need_handoff, query_text, record_step, resolve_graph_ids

__all__ = [
    "NegotiateAndAnswer",
    "PersistMemory",
    "QualifyInquiry",
    "ReceiveInquiry",
    "ReplyWithQuote",
    "RequestHumanHandoff",
    "ScheduleFollowup",
    "UnderstandRequirement",
    "fallback_response",
    "graph_output",
    "need_handoff",
    "query_text",
    "record_step",
    "resolve_graph_ids",
]
