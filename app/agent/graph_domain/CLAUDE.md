# graph_domain/
> L2 | 父级: ../CLAUDE.md

成员清单
__init__.py: 图子域稳定入口，导出八步节点与 graph_support helper。
nodes.py: Pydantic Graph 八步节点，按 receive/qualify/understand/quote/answer/followup/handoff/persist 编排工具调用。
policy.py: Graph 决策 provider 边界，提供 rule_based 默认策略、HTTP 远端策略与 OpenAI-compatible LLM JSON 决策配置。
support.py: 图运行辅助函数，解析 inquiry/conversation id、记录步骤、设置 handoff、生成 fallback 与结构化输出。

架构边界
nodes.py 只表达节点跳转、工具调用与 policy 消费；policy.py 只决定是否继续、移交、检索或报价，并把 HTTP webhook 与 OpenAI-compatible chat completion 请求隔离在 provider 内；support.py 只处理共享状态转换与输出组装；../graph.py 只装配 Graph 和运行入口。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
