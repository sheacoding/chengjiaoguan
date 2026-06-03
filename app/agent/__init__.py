"""
/* ========================================================================== */
/* GEB L3: Agent 子包根                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 app.agent.types、app.agent.model_config、app.agent.runtime 与 app.agent.graph 的公共导出
 * [OUTPUT]: 对外提供 CloserAgentDeps、CloserAgentOutput、CloserGraphState、AgentModelConfig、模型配置 helper、closer_agent、closer_operating_graph、build_closer_agent、run_closer_agent、run_closer_graph、run_closer_graph_result、closer_graph_mermaid
 * [POS]: app/agent 的稳定包入口，折叠 Agent 类型、模型配置、工具绑定、图状态机与运行门面
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app.agent.graph import (
    closer_graph_mermaid,
    closer_operating_graph,
    run_closer_graph,
    run_closer_graph_result,
)
from app.agent.model_config import AgentModelConfig, configured_agent_model, get_agent_model_config, selected_agent_model
from app.agent.runtime import build_closer_agent, closer_agent, run_closer_agent
from app.agent.types import CloserAgentDeps, CloserAgentOutput, CloserGraphState

__all__ = [
    "AgentModelConfig",
    "CloserAgentDeps",
    "CloserAgentOutput",
    "CloserGraphState",
    "build_closer_agent",
    "closer_agent",
    "closer_graph_mermaid",
    "closer_operating_graph",
    "configured_agent_model",
    "get_agent_model_config",
    "run_closer_agent",
    "run_closer_graph",
    "run_closer_graph_result",
    "selected_agent_model",
]
