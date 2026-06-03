# services/
> L2 | 父级: ../CLAUDE.md

成员清单
__init__.py: 服务包标记，隔离业务规则层。
approval_execution.py: 审批执行器，执行 message_send、quotation_send、pi_generate、handoff 的具体副作用。
approvals.py: 审批工作流服务，处理 pending 审批的列表、修改、批准、拒绝与队列状态。
auth_keys.py: API key 鉴权服务，签发一次性明文 token、存储哈希、校验 Bearer cak_ 与撤销轮换。
channel_gateway.py: 入站渠道网关，确保卖家/渠道账号/客户/询盘/会话/首条消息并实现幂等。
channel_delivery.py: 出站渠道投递边界，把 Message 转成 email/WhatsApp/site_form delivery payload，并委派可插拔客户端执行。
channel_delivery_clients.py: 出站渠道客户端边界，提供 payload-only 默认客户端、SMTP 客户端与 WhatsApp Cloud HTTP 客户端。
channel_receipts.py: 渠道投递回执同步服务，把 WhatsApp/email/provider 状态回声写回 delivery_attempt.status 与 response.receipts。
delivery_attempts.py: 投递尝试记录服务，把 delivery 结果固化为 delivery_attempt，并提供失败重试候选查询与 deterministic retry 执行。
catalog.py: 配置与看板服务兼容门面，重新导出 catalog_domain 的公共服务契约，含价格规则版本列表。
catalog_domain/: 配置域服务子包，分离产品、导入、价格、汇率缓存刷新确认、渠道与 dashboard 指标规则。
credentials.py: 渠道凭据封装服务，把 channel_account.credentials 从明文 JSON 转成带 HMAC/key_id 校验的可轮换封存结构。
crm.py: CRM 客户档案服务，按 customer_id/inquiry_id 返回画像，提供客户列表、档案修改与询盘/会话/报价/跟进聚合。
data_privacy.py: 数据隐私擦除服务，按租户擦除 customer 及其询盘、会话、消息、报价、跟进、投递、审批、通知与审计快照。
data_exports.py: 数据导出服务，把 customers、inquiries、quotations 租户数据序列化为确定性 CSV。
demo.py: Demo 场景种子服务，用确定性产品、知识、询盘、报价、审批与跟进编排 MVP 主链路。
email_adapter.py: Email 适配边界，解析原始邮件并组合 SMTP 文本消息。
email_polling.py: Email IMAP 轮询边界，从 email channel 拉取未读邮件并复用 channel_gateway 入站落库。
embedding_providers.py: 知识向量 provider 边界，提供测试用确定性哈希向量与生产 OpenAI-compatible embedding HTTP 客户端。
exchange_rate_sources.py: 汇率来源边界，提供全局 HTTP provider 配置画像，显式拉取外部汇率并写入待人工确认的 exchange_rate_cache。
exchange_rates.py: 汇率解析服务，读取静态汇率或已确认未过期的 exchange_rate_cache。
followups.py: 跟进任务服务，创建和执行到期 follow-up，并通过 outbound 发送。
knowledge.py: 轻量 RAG 服务，文本切块、provider 向量生成、索引 upsert 同步与 search provider 检索。
knowledge_index_providers.py: 知识索引 provider 边界，提供 disabled 默认实现与 HTTP 托管语义索引 upsert 同步。
knowledge_search_providers.py: 知识检索 provider 边界，提供 rule_based 默认排序、HTTP 远端重排与 managed-index 托管索引查询。
outbound.py: 出站消息服务，执行敏感承诺、地板价、大金额与人工接管护栏，并调用 channel_delivery 投递边界。
object_storage.py: 对象存储边界，提供本地 backend、远端 HTTP backend、元数据结构与 storage_key 安全校验。
notifications.py: 通知状态机服务，把审批等人工处理事件固化为未读/已读/归档 notification。
ops_alerts.py: 运维告警聚合服务，只读折叠失败投递、待审批、到期/暂停跟进与汇率缓存风险。
ops_monitoring.py: 运维监控 sink 边界，提供 disabled 默认实现与 HTTP webhook 事件上报。
ops_scheduler.py: 运维调度组合边界，把 due jobs、readiness、alerts 与 monitoring 上报收束成外部 cron/queue 单入口。
pi_documents.py: PI 文档产物服务，把批准后的 PI 文本与 PDF 交给 object_storage 并返回可追踪元数据。
readiness.py: 生产就绪诊断服务，只读检查租户、API key、Agent 模型、Graph 决策 provider、知识检索/索引 provider、embedding provider、全局汇率源 provider、monitoring sink、凭据密钥、delivery mode、渠道凭据与 seal 轮换状态、对象存储、汇率配置与失败投递状态。
product_matching.py: 产品匹配服务，用 token 重叠给产品字段打分并解释命中原因。
quotations.py: 报价记录服务，读取、修改、生成 PI 文档与文件产物、创建底价发送审批、发送 quotation 并生成消息。
quote_engine.py: 报价计算核心，处理 MOQ、阶梯价、成本利润、物流、可信汇率换算、有效期、地板价。
quote_language.py: 报价文案渲染器，把 QuoteResult 转成确定性客户消息。
scoring.py: 询盘打分服务，按公司、邮箱、数量、产品、目的地、垃圾/竞品信号输出 A/B/C。
seller_settings.py: 卖家设置服务，读取/修改 seller 设置并为 AI 出站消息应用身份披露文本。
whatsapp_adapter.py: WhatsApp Cloud API 适配边界，标准化 webhook、组合 payload、校验签名。
workers.py: 后台任务统一调度边界，把到期 follow-up、投递重试、价格规则汇率刷新与显式启用的 email 轮询收束成一个 deterministic due jobs 入口。

架构边界
服务层只接受 Session 与标量输入；不读取 HTTP 请求；API key 只在 auth_keys.py 存 hash 与撤销状态，明文只在创建响应出现一次；审批队列状态留在 approvals.py，副作用执行进入 approval_execution.py；人工需要处理的提醒统一进入 notifications.py，审批解决时通知必须同步已读；隐私擦除统一进入 data_privacy.py，必须同时阻断后续出站动作并擦掉关联审计快照/通知；真实外部渠道网络调用必须隔离在 channel_delivery_clients.py 或 email_polling.py，默认测试用替身不触网；RAG 向量生成必须隔离在 embedding_providers.py，默认测试用确定性哈希，生产显式配置 provider/API key；RAG 索引同步必须隔离在 knowledge_index_providers.py，默认 disabled，生产通过 HTTP upsert 托管语义索引；RAG 检索必须隔离在 knowledge_search_providers.py，默认 rule_based 排序，生产可切换 HTTP 重排或 managed-index 托管索引查询；channel_receipts.py 只同步外部回执事实，不重新发送消息；workers.py 只编排已有服务，不拥有业务规则；ops_scheduler.py 只组合 workers/readiness/alerts/monitoring，不直接拥有业务任务；ops_monitoring.py 只负责外部事件上报，失败必须反映在调度结果中；readiness.py 与 ops_alerts.py 只读配置/运行事实，不触发发送、轮询、审批或刷新；所有出站结果必须写入 delivery_attempts.py 形成可重试记录；AI 身份披露统一由 seller_settings.py 应用，出站消息、审批后消息与报价发送不得各写一套；外部汇率获取必须隔离在 exchange_rate_sources.py，全局 provider 由 CLOSER_EXCHANGE_RATE_* 配置，单条 pricing_rule 可用 rates/endpoint 覆盖，定时刷新由 workers.py 调度、catalog_domain/pricing.py 执行，报价只消费已确认未过期的缓存；文件产物写入必须隔离在 object_storage.py，业务服务只传 storage_key 与 bytes，storage backend 可在 local/http 间切换；配置域规则进入 catalog_domain 子包，catalog.py 仅保留兼容导出；所有 LLM/网络能力在测试中必须被确定性替身隔离。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
