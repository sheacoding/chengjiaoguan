# agent/
> L2 | 父级: ../CLAUDE.md

成员清单
__init__.py: Agent 子包稳定入口，重新导出类型、运行入口与八步图状态机。
graph.py: Pydantic Graph 组合根，装配 closer_operating_graph 与同步运行入口。
graph_domain/: Agent 图子域，拆分八步节点、决策 policy 与共享 helper，承载 receive/qualify/understand/quote/answer/followup/handoff/persist 主链路。
model_config.py: Agent 模型配置边界，读取 CLOSER_AGENT_MODEL、CLOSER_AGENT_API_KEY_ENV 与 provider key 状态，供 runtime 和 readiness 共用。
runtime.py: PydanticAI Agent 组合根，创建 closer_agent 并提供 run_closer_agent。
tools.py: PydanticAI RunContext 工具绑定，把模型工具调用转发到 app.agent_tools 稳定门面。
types.py: Agent 依赖、结构化输出与图状态 dataclass/Pydantic 模型真源。

架构边界
types.py 只定义状态；model_config.py 只定义生产模型配置事实；tools.py 只做上下文解包；runtime.py 只连接模型与工具，并优先使用显式 model，其次使用 CLOSER_AGENT_MODEL；graph.py 只装配 Graph 并注入 graph decision provider；graph_domain/policy.py 持有规则、HTTP webhook 与 OpenAI-compatible LLM 决策边界；graph_domain/nodes.py 只编排节点和消费 policy 决策；graph_domain/support.py 只处理共享状态转换；旧 app/agent_runtime.py 只保留兼容导出，不再承载实现。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
