# app/
> L2 | 父级: ../CLAUDE.md

成员清单
__init__.py: Python 包标记，声明 app 为后端核心模块。
agent/: Agent 编排子包，拆分类型、PydanticAI 工具绑定、运行入口与 Pydantic Graph 八步状态机。
agent_runtime.py: 旧 Agent 运行时兼容门面，重新导出 app/agent 公共契约。
agent_tools.py: Agent 工具门面，把稳定工具签名转发到服务层并落库报价。
database.py: SQLAlchemy 数据库基础设施，提供 Base、engine、SessionLocal、get_session、utcnow。
dependencies.py: FastAPI 依赖入口，解析正式 Authorization Bearer cak_ API key、MVP Bearer seller token，并保留租户头 X-Seller-Id。
errors.py: API 错误形状适配器，统一输出 {"error": {"code", "message"}}。
main.py: FastAPI 应用工厂与组合根，负责 lifespan、错误处理和 router 装配。
models.py: SQLAlchemy ORM 真源，定义卖家、API key、渠道、价格规则版本、询盘、会话、消息、投递尝试、报价、知识、通知、审批、审计。
routers/: HTTP 资源域路由层，承载 auth、webhook、inquiries、customers、conversations、settings、demo、delivery-attempts、channel-operations、workers、exports、catalog、knowledge、approvals、notifications、quotations。
schemas.py: Pydantic 入参与响应模型，约束 webhook、询盘补丁、消息、客户补丁、卖家设置补丁、API key、知识、价格规则、汇率缓存刷新、审批、通知、报价补丁。
services/: 业务规则层，承载渠道、CRM、打分、报价、知识、出站、审批、跟进等确定性能力。

架构边界
app/main.py 只装配应用；app/routers 处理 HTTP 参数、错误翻译和响应组装；app/services 不依赖 FastAPI；app/agent_tools.py 是 Role B 可调用工具签名的稳定门面；app/agent 只编排工具，不直接改写业务规则；app/agent_runtime.py 只保留兼容导出。

坏味道警戒
app/ 顶层仍超过 8 成员；Agent 泥团已拆入 app/agent/，下一次结构性改动优先把数据库模型或通用基础设施继续分域，防止 app 顶层再次膨胀。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
