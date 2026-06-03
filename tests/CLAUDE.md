# tests/
> L2 | 父级: ../CLAUDE.md

成员清单
conftest.py: pytest 夹具，创建 SQLite 内存库、TestClient、会话覆盖，并默认关闭 live delivery。
test_agent_runtime.py: 验证 PydanticAI runtime 的工具绑定、模型配置选择、结构化输出与 Pydantic Graph 八步状态机。
test_approvals_quotations_api.py: 验证审批与报价 API 的修改、发送、批准、拒绝、底价发送审批、PI 文本/PDF 生成与文件产物路径。
test_auth_dependency.py: 验证 Bearer seller token、Bearer cak_ API key、MVP 租户头 shortcut、撤销轮换与鉴权错误形状。
test_channel_delivery_clients.py: 验证 payload-only、SMTP 与 WhatsApp Cloud 出站客户端边界，不触真实网络。
test_channel_receipts.py: 验证 WhatsApp/email/provider 回执可同步 delivery_attempt 状态、追加 response.receipts 并保持租户隔离。
test_configuration_api.py: 验证产品库 CRUD、导入错误报告、价格规则校验、价格规则版本、汇率缓存刷新确认、渠道、凭据轮换、运营看板指标与 request_handoff 工具。
test_conversation_api.py: 验证会话详情、消息列表、人工接管、释放、人工发信与 delivery 返回。
test_crm_tool.py: 验证 get_customer 工具按询盘或客户返回 CRM 画像。
test_customers_api.py: 验证 customers API 可列表筛选、详情聚合、修改档案、GDPR 擦除、记录审计并保持租户隔离。
test_data_exports_api.py: 验证 exports CSV API 可导出 customers、inquiries、quotations，且保持租户隔离与错误形状。
test_delivery_attempts_api.py: 验证 delivery-attempts 列表、手动 retry、due retry 调度入口与租户隔离。
test_delivery_attempts.py: 验证 failed delivery_attempt 的 due retry worker，可成功转 queued 或失败后重新排期。
test_demo_api.py: 验证 /demo/seed 可一键生成演示主链路，并保持幂等与租户隔离。
test_demo_flow_script.py: 验证 demo_flow dry-run 输出 API 编排步骤且不访问网络。
test_embedding_providers.py: 验证确定性哈希 embedding、OpenAI-compatible HTTP provider、环境选择与 readiness 配置画像。
test_email_adapter.py: 验证 Email 原始邮件标准化与 SMTP 消息组合。
test_email_polling.py: 验证 Email IMAP 轮询服务、幂等入站、acknowledge、poll-email API 与租户隔离。
test_followups.py: 验证 follow-up 创建、执行、暂停、停止、完成。
test_graph_policy.py: 验证 Agent 图 rule_based、HTTP 与 OpenAI-compatible LLM 决策 provider 请求、解析与配置画像。
test_knowledge.py: 验证知识切块、嵌入、入库、检索。
test_knowledge_index_providers.py: 验证 disabled/http 知识索引 provider、入库 upsert 同步与 readiness 配置画像。
test_knowledge_search_providers.py: 验证 rule_based、HTTP 重排与 managed-index 托管索引查询 provider 与配置画像。
test_models_schema.py: 验证 ORM schema、seller_api_key、pricing_rule_version、delivery_attempt、migration 与基础数据模型可建表可落库。
test_notifications_api.py: 验证 notifications API 列表/标记、审批请求自动通知、审批解决后通知已读与租户隔离。
test_object_storage.py: 验证本地/远端对象存储写入元数据、storage config 与 unsafe storage key 拒绝。
test_ops_alerts.py: 验证 ops alerts 聚合失败投递、待审批、到期/暂停跟进、汇率缓存风险并保持租户隔离。
test_ops_monitoring.py: 验证 disabled/http 运维监控 sink、事件上报请求与配置画像。
test_ops_scheduler.py: 验证 scheduler 单入口可组合 due jobs、readiness、alerts 与 monitoring 上报并保持租户隔离。
test_product_matching.py: 验证产品匹配工具的字段命中与排序。
test_production_check_script.py: 验证 production_check dry-run 输出部署检查步骤、保护 token 且默认不触发 scheduler。
test_project_contract.py: 验证项目文档包含 API、租户、任务、工具契约。
test_quote_engine.py: 验证报价引擎的 MOQ、阶梯价、利润、汇率换算、全局/规则汇率源刷新、汇率缓存过期/确认、地板价。
test_quote_tools.py: 验证 calc_quote 与 generate_pi 审批型 Agent 工具，并证明 PI 文本/PDF 文件落盘。
test_readiness.py: 验证生产 readiness 服务和 /ops/readiness API 能暴露 API key、Agent/RAG/汇率/监控 provider、渠道凭据 seal 轮换等 ready/degraded/unready 配置画像。
test_scoring_tool.py: 验证询盘打分工具输出 grade、score、signals。
test_send_message_tool.py: 验证出站消息发送、email/WhatsApp delivery payload、默认客户端状态、delivery_attempt 记录、失败重试候选与护栏审批移交。
test_settings_api.py: 验证 settings API 可读写 seller 设置、记录审计，并让 AI 身份披露开关影响出站消息。
test_site_form_webhook.py: 验证 site_form webhook 入站与幂等。
test_whatsapp_adapter.py: 验证 WhatsApp webhook 标准化、payload 组合、签名校验。
test_workers.py: 验证 unified worker 服务与 /workers/run-due API 可统一触发 due follow-up、投递重试、价格规则汇率刷新与启用 email 轮询。

测试法则
测试用 SQLite 内存库证明行为；禁止真实 LLM、IMAP、SMTP、WhatsApp、托管索引、全局汇率源与运维监控网络调用；live delivery、knowledge index、global exchange provider 与 ops monitor 默认被 conftest 关闭；每个任务用聚焦测试锁住一条业务路径。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
