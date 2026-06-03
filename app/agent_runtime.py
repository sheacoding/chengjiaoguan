"""
/* ========================================================================== */
/* GEB L3: Agent 运行时兼容门面                                               */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 app.agent 子包的类型、模型配置、PydanticAI 运行入口与 Pydantic Graph 状态机导出
 * [OUTPUT]: 对外重新导出 CloserAgentDeps、CloserAgentOutput、CloserGraphState、AgentModelConfig、模型配置 helper、closer_operating_graph、build_closer_agent、closer_agent、run_closer_agent、run_closer_graph、run_closer_graph_result、closer_graph_mermaid
 * [POS]: app 的旧导入兼容层，让外部继续 import app.agent_runtime，同时真实实现迁入 app/agent/
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app.agent import (
    AgentModelConfig,
    CloserAgentDeps,
    CloserAgentOutput,
    CloserGraphState,
    build_closer_agent,
    closer_agent,
    closer_graph_mermaid,
    closer_operating_graph,
    configured_agent_model,
    get_agent_model_config,
    run_closer_agent,
    run_closer_graph,
    run_closer_graph_result,
    selected_agent_model,
)

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
