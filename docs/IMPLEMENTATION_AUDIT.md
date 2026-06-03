# IMPLEMENTATION_AUDIT
> L3 | 父级: ./CLAUDE.md

/**
 * [INPUT]: 依赖根目录原始 docx/xlsx/html 规格、CLAUDE.md、AGENTS.md、app 代码、tests 与 migrations
 * [OUTPUT]: 对外提供当前完成度审计、已补齐项、剩余缺口与下一步优先级
 * [POS]: docs 的实现状态镜像，用来把产品/技术/接口/排期语义相映射回当前机器相
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

## 已读取文档

- `成交官_需求规格说明书_V1.0.docx`: P0/P1/P2 功能需求与验收标准。
- `成交官_产品设计文档_V1.1.docx`: 产品模块 M1-M10、前端页面、Agent 工作流、MVP 范围。
- `成交官_技术架构设计文档_V1.1.docx`: 分层架构、PydanticAI、RAG、报价、护栏、部署与合规。
- `成交官_数据库设计文档_V1.0.docx`: 业务实体、字段、枚举、索引、安全约定。
- `成交官_后端API契约_V1.0.docx`: `/api/v1` REST API、配置/看板接口、错误与分页形状。
- `成交官_Agent工具接口清单_V1.0.docx`: Agent 工具签名、状态机映射、人工审批约定。
- `成交官_两人开发分工排期表_方案A平衡版_V2.1.xlsx`: T01-T31 任务分工、里程碑、接缝清单。
- `跨境B2B_AI询盘成交Agent_市场调研报告.docx`: 市场定位、竞品空白、商业模式与风险。
- `Closer 工作台（离线版）.html`: 离线原型文件；当前可提取文本很少，主要价值是前端视觉参考，React/Vite 工作台与 Playwright E2E 已另落在 frontend/。
- `CLAUDE.md` / `AGENTS.md` / `docs/EXECUTION_PLAN.md` / `migrations/001_initial.sql`: 当前项目契约、执行计划与数据库机器相。
- `docs/COMPLETION_AUDIT.md`: 完成度收口矩阵，明确本地已完成、边界完成与真实外部阻塞。

## 当前已完成且有测试证明

- 数据层：SQLAlchemy ORM 与 PostgreSQL migration 覆盖 seller、seller_api_key、channel_account、product、pricing_rule、pricing_rule_version、customer、inquiry、conversation、message、delivery_attempt、quotation、quotation_item、followup_task、knowledge_chunk、notification、audit_log、approval。
- 入站主链路：site_form webhook 入库，按 channel_message_id 幂等，创建/关联 customer、inquiry、conversation、message。
- 渠道边界：Email 原始邮件解析/SMTP 消息组合/IMAP 未读轮询；WhatsApp webhook 标准化、文本/template payload、签名校验；出站 delivery 边界生成 email/WhatsApp/site_form 投递结果，并通过 payload-only/SMTP/WhatsApp Cloud 可插拔客户端隔离真实发送；渠道回执同步可把 WhatsApp/email/provider 状态回声写回 delivery_attempt。
- 鉴权与租户上下文：支持正式 `Authorization: Bearer cak_<token>` API key 哈希校验、签发、列表与撤销轮换；保留 `Authorization: Bearer seller:<id>` 与 `X-Seller-Id` MVP shortcut；非法 token 返回统一 error shape。
- 询盘/会话/客户 API：询盘列表、详情、分级/状态修正；会话详情、消息列表、人工接管、释放、人工发信；客户列表、详情聚合、档案偏好修改、客户数据擦除与审计。
- 优先级排序：询盘列表默认按 A/B/C 价值级别置顶，再按到达时间排序。
- 甄别与 CRM：score_inquiry 输出 grade/score/signals；get_customer 返回客户画像；customers API 为前端客户页与会话档案抽屉提供租户隔离资源面。
- 产品与配置 API：products 列表/创建/详情/更新/软删除/import，pricing-rules 列表/创建/读取/更新/版本历史、exchange-rate-cache 刷新/确认，channels 列表/创建/凭据 seal 轮换，settings 读取/修改卖家配置与 AI 身份披露开关。
- 知识与产品匹配：知识切块、provider 注入的向量生成、托管索引 upsert 同步、检索；产品字段 token 匹配与解释。
- 报价：MOQ、阶梯价、成本利润、物流、可信汇率源刷新、有效期、底价命中；calc_quote 生成 draft quotation；generate_pi 先创建人工审批，批准后生成含买卖方、品名、数量、单价、总额、有效期与条款的 PI 文档。
- 护栏、审批与通知：send_message 对底价、敏感承诺、大金额、人工接管创建 pending approval；approvals 支持 patch/approve/reject；审批请求会创建未读 notification，批准/拒绝后自动已读；request_handoff 工具已补齐；AI 出站消息、审批后消息和报价发送统一尊重 seller.ai_disclosure。
- 投递运维：delivery-attempts API 支持列表查看、单条手动 retry、due retry 调度入口，失败投递可从记录进入重试闭环；channel sync-receipts API 可把 delivered/read/failed/bounced 等回执并入同一投递状态机。
- 渠道运维：channels poll-email API 支持对 email channel 拉取未读邮件，复用入站主链路创建客户、询盘、会话和消息，并保持 channel_message_id 幂等。
- 后台调度：workers run-due API 统一触发 due follow-up、delivery retry、pricing rule exchange-rate refresh 与显式启用 `poll_enabled` 的 email polling；ops scheduler API 再把 due jobs、readiness、alerts 与 monitoring sink 上报折叠成外部 cron/queue 单入口。
- 生产就绪诊断与运行告警：ops readiness API 只读输出 seller、active API key、agent model、graph decision、knowledge search/index、embedding、monitoring sink、credential secret、delivery mode、document storage、channel credentials/seal 轮换状态、exchange source/cache 与 failed delivery_attempts 的 ready/degraded/unready 画像；ops alerts API 聚合 failed delivery、pending approval、due/paused follow-up 与 exchange cache 风险；ops monitoring sink 可把 scheduler run 事件推送到外部监控 webhook。
- 报价 API：quotation detail/patch/send；命中底价的报价发送会创建 `quotation_send` 审批，批准后才真正发送。
- 跟进：create_followup、run_due_followups、自动暂停/停止/完成。
- 看板与导出：dashboard metrics 保留 today_inquiries、pending_handoffs、auto_handle_rate、conversion，并补充询盘 pipeline、会话接管、审批、报价、投递、跟进与汇率缓存健康指标；exports API 可导出 customers、inquiries、quotations CSV。
- Demo 兜底入口：`/api/v1/demo/seed` 可按租户幂等创建演示产品、价格规则、知识、site_form 询盘、A 级评分、产品/知识匹配、报价、pending message_send 审批与 follow-up。
- Demo 演示脚本：`scripts/demo_flow.py` 可 dry-run、seed、审批发送并触发 workers；`docs/DEMO_RUNBOOK.md` 固化本地彩排路径。
- 生产部署检查：`scripts/production_check.py` 可 dry-run、读取 health/readiness/alerts，并在显式 `--run-scheduler` 时触发 `/ops/scheduler/run` 与 monitoring sink；`docs/PRODUCTION_RUNBOOK.md` 固化 provider、cron/queue、monitoring 与判定规则。
- 环境配置：`docs/ENVIRONMENT.md` 汇总 Agent、Graph decision、embedding、knowledge index/search、delivery、credentials、document storage、exchange rate、ops monitoring、production check、demo 与 E2E 的 `CLOSER_*` 变量。
- 前端工作台：`frontend/` React/Vite 应用可通过 Vite proxy 调用后端 API，展示看板、收件箱、客户、产品、审批、设置、readiness 与 Demo 操作，并支持产品创建、价格规则创建/编辑/版本查看、渠道创建/凭据轮换、设置保存、通知状态处理、客户档案抽屉、报价详情与报价发送；Playwright E2E 可自动启动 API/Vite 并在桌面/移动视口验证 Demo Seed、客户档案、报价详情、审批发送、通知归档、设置保存、调度入口、密集询盘/客户列表、价格规则版本/更新、渠道凭据轮换与无横向溢出。
- 视觉 QA：`docs/VISUAL_QA.md` 固化本地生产形态桌面/移动截图证据，客户列表 20 条长文本数据在 1280 与 390 宽度下均无横向溢出并产生纵向滚动。
- Agent runtime：PydanticAI Agent 暴露核心工具与结构化输出，支持显式 model 或 `CLOSER_AGENT_MODEL` 生产模型配置；Pydantic Graph 八步状态机可跑通报价/回复/跟进与产品超范围转人工，并支持 rule_based、HTTP 与 OpenAI-compatible LLM graph decision provider 注入。

验证命令：

```bash
.venv/bin/python -m pytest
```

当前结果：`165 passed`，无测试警告。

前端结果：`npm run build` 通过，`npm audit --json` 为 0 vulnerabilities，`npm run test:e2e` 为 8 passed。

完成度判定：`docs/COMPLETION_AUDIT.md` 已把仓库内可交付项与真实 provider、cron、monitoring、生产彩排等外部阻塞分离。

## 已补齐的关键缺口

- 补齐 API 契约第五节的配置与看板接口：`/products`、`/products/import`、`/pricing-rules`、`/channels`、`/dashboard/metrics`。
- 补齐 Agent 工具清单中的 `request_handoff`，写入 approvals 队列并切换人工接管。
- 修正 `generate_pi` 工具审批语义：工具先挂起 `pi_generate` approval，卖家批准后由后端生成规范 PI 文档。
- 补齐 API 契约中的 Bearer token 租户解析：`Authorization: Bearer seller:<id>` 优先于 `X-Seller-Id`，并保留 shortcut 兼容测试与 Demo。
- 补齐正式 API key 鉴权：`POST /auth/api-keys` 一次性返回 `cak_` token，数据库只保存 hash；`GET /auth/api-keys` 只暴露 prefix/状态；`POST /auth/api-keys/{id}/revoke` 撤销后 token 立即失效；readiness 会提示租户是否缺少 active key。
- 补齐产品库详情、编辑与软删除接口；删除后产品不再出现在列表、详情和匹配候选中。
- 补齐客户档案 API：`/customers` 支持搜索、分级/状态筛选、分页；`/customers/{id}` 聚合客户资料、询盘、会话、报价与跟进；`PATCH /customers/{id}` 可更新偏好、富化信息与状态并写入审计日志。
- 补齐 GDPR 客户数据擦除 API：`DELETE /customers/{id}` 会租户隔离地擦除 customer PII、关联询盘、会话、消息、报价、跟进、投递尝试、审批 payload 与历史审计快照，并停止后续出站/跟进动作。
- 补齐数据导出 API：`/exports/customers.csv`、`/exports/inquiries.csv`、`/exports/quotations.csv` 输出租户隔离 CSV，并对未知 dataset 返回统一错误形状。
- 补齐设置与 AI 身份披露 API：`GET/PATCH /settings` 可读取/修改 seller 设置，`ai_disclosure` 开启时所有 AI 出站内容统一追加披露文本，关闭时保持原文。
- 修正询盘列表默认排序，符合 FR-M2-03 “高价值置顶”。
- 新增 `app/services/catalog.py`，把配置/看板规则从 HTTP 层剥离。
- 新增 `tests/test_configuration_api.py`，用测试证明配置 API、xlsx 导入、看板与 handoff 工具。
- 补强 dashboard 指标：`/dashboard/metrics` 从四个基础数扩展为 pipeline、conversation、approval、quotation、delivery、followup、exchange_rate_cache 分组指标，同时保持旧字段兼容。
- 在 `app/agent_runtime.py` 增加 Pydantic Graph 八步运行图：receive、qualify、understand、quote、answer、followup、handoff、persist。
- 将 FastAPI startup 从 deprecated `on_event` 迁移到 lifespan，测试输出不再有 deprecation warnings。
- 将 `app/main.py` 拆成组合根 + `app/routers/` 分域路由，HTTP 层不再由单文件承载所有 API。
- 将 `app/agent_runtime.py` 拆成 `app/agent/` 子包，类型、工具绑定、PydanticAI 运行入口与 Pydantic Graph 状态机各自成域，并保留旧导入兼容门面。
- 将 `app/agent/graph.py` 拆成组合根 + `app/agent/graph_domain/` 子域，八步节点进入 nodes.py，共享状态转换进入 support.py，graph.py 不再承载节点细节。
- 新增 `app/services/credentials.py`，channel_account.credentials 写入时封存为带随机 nonce、HMAC、key_id 校验和密文的 JSON 结构，API 只暴露配置状态与 key 状态。
- 补齐 channel credential seal secret 轮换：`CLOSER_CREDENTIALS_PREVIOUS_SECRETS` 可临时解旧封存，`POST /channels/{id}/rotate-credentials` 会重封到当前 secret，readiness 会对 legacy/plaintext 凭据给出 warning。
- 报价引擎补齐确定性汇率换算：pricing_rule.logistics_template.exchange_rates 提供币种映射，目标币种不同且缺少汇率时直接拒绝报价。
- 新增 `app/services/pi_documents.py` 与 `app/services/object_storage.py`，PI 审批通过后把文档文本与 PDF 写入对象存储本地 backend，并把 filename、storage_key、mime_type、size、backend、path 回填到 quotation.terms。
- 产品批量导入补齐行级错误报告：有效行继续创建，坏行返回 row_number/code/message，避免静默丢弃。
- 将配置域服务拆入 `app/services/catalog_domain/`，产品、导入、价格、渠道、看板各自成域，`app/services/catalog.py` 只保留兼容导出。
- 报价发送补齐底价二次确认：`POST /quotations/{id}/send` 触发 floor guardrail 时返回 pending approval，审批通过后由 approvals 执行发送。
- 新增 `app/services/channel_delivery.py`，AI 消息、人工消息、审批后消息和报价发送统一生成渠道 delivery payload、外部消息 id 与审计快照。
- 新增 `app/services/channel_delivery_clients.py`，出站发送支持默认 payload-only、SMTP 和 WhatsApp Cloud HTTP 客户端；`CLOSER_DELIVERY_MODE=live` 才会触发真实外部网络调用，测试默认关闭。
- 新增 `delivery_attempt` 表与 `app/services/delivery_attempts.py`，每次出站投递都会落库记录 client/status/payload/response；失败投递写入 `next_retry_at`，可被 due retry worker 扫描并重新执行，成功清除重试时间，失败重新排期。
- 新增 `app/routers/delivery_attempts.py`，暴露 `/delivery-attempts` 列表、`/delivery-attempts/{id}/retry` 单条手动重试与 `/delivery-attempts/retry-due` 调度入口。
- 新增 `app/services/channel_receipts.py`，暴露 `/channels/{id}/sync-receipts`，支持 WhatsApp statuses 与 generic email/provider receipts，按 provider_message_id 或 external_id 命中 delivery_attempt，追加 response.receipts 并更新状态；失败回执重新写入 next_retry_at。
- 新增 `app/services/email_polling.py` 与 `app/routers/channel_operations.py`，支持 email channel 的 IMAP 未读轮询、acknowledge、幂等入站与 `/channels/{id}/poll-email` 运维入口。
- 新增 `app/services/workers.py` 与 `app/routers/workers.py`，把 `run_due_followups`、`run_due_delivery_retries`、显式启用的 email `poll_email_channel` 收束到 `/workers/run-due`，外部调度器不再需要记住三个入口。
- 新增 `app/services/readiness.py` 与 `/ops/readiness`，部署前即可看到 Agent/RAG provider、全局汇率源 provider、凭据密钥、live delivery、对象存储、渠道凭据、汇率配置和失败投递风险，不需要等到运行时才暴雷。
- 新增 `app/services/ops_alerts.py` 与 `/ops/alerts`，把失败投递、待审批、到期/暂停跟进和汇率缓存风险折叠成 critical/warning 告警列表，便于外部监控拉取。
- 新增 `app/services/ops_monitoring.py` 与 `app/services/ops_scheduler.py`，`/ops/scheduler/run` 可供外部 cron/queue 单次调用，返回 jobs/readiness/alerts/monitoring 汇总，并通过 `CLOSER_OPS_MONITOR_PROVIDER=http/webhook` 推送调度事件；监控上报失败不阻断业务任务，但会进入调度结果。
- 新增 `app/agent/model_config.py`，把 `CLOSER_AGENT_MODEL`、`CLOSER_AGENT_API_KEY_ENV` 与 OpenAI key 需求抽成可测试配置边界，runtime 和 readiness 共享同一份模型事实。
- 将审批副作用拆入 `app/services/approval_execution.py`，`approvals.py` 只保留审批队列状态管理，避免审批类型增加时形成执行泥团。
- 价格规则配置补齐服务层校验：floor_price、margin_rate、tiered_prices、logistics_template 与 exchange_rates 在入库前检查，坏规则返回 `invalid_pricing_rule`。
- 价格规则补齐版本历史：创建写入 v1，后续更新写入递增 pricing_rule_version 快照，`GET /pricing-rules/{id}/versions` 可租户隔离地查看历史。
- 补齐通知系统后端闭环：notification 表、`GET/PATCH /notifications` API、审批请求自动通知、审批解决自动已读、客户擦除时关联通知归档脱敏。
- 新增 `app/services/exchange_rates.py`，报价汇率支持静态表与 `exchange_rate_cache`；缓存必须人工确认且未过期，否则报价拒绝执行。
- 新增 `app/services/exchange_rate_sources.py`，把外部汇率来源抽成 provider 边界；支持 `CLOSER_EXCHANGE_RATE_PROVIDER=http/remote`、source、endpoint、auth token 与 timeout 的全局生产配置画像；刷新只写入 `confirmed=false` 的缓存，人工确认后报价引擎才可使用。
- 补齐价格规则后台汇率 API：`POST /pricing-rules/{id}/refresh-exchange-rate-cache` 拉取待确认汇率，`POST /pricing-rules/{id}/confirm-exchange-rate-cache` 才允许报价消费缓存，并写入审计日志。
- 补齐价格规则汇率后台调度：`/workers/run-due` 会扫描配置了 `exchange_rate_provider` 的 pricing_rule，按过期缓存自动刷新待确认 exchange_rate_cache；刷新来源优先使用请求 rates、规则 endpoint，再回退到全局 `CLOSER_EXCHANGE_RATE_*` provider；单条规则失败折叠为 failed 结果且不阻塞后续规则，仍不绕过人工确认。
- 新增 `app/services/embedding_providers.py`，把知识向量生成拆成 deterministic hash 默认实现与 OpenAI-compatible 生产 provider，知识入库/检索与 readiness 共同消费同一份边界事实。
- 新增 `app/agent/graph_domain/policy.py`，把 Graph 节点的继续/移交/检索/报价决策从节点中抽成 rule_based 默认策略、HTTP 远端 provider 与 OpenAI-compatible LLM JSON 决策 provider，`readiness` 会暴露 graph decision provider 配置状态。
- 新增 `app/services/knowledge_search_providers.py`，把知识检索从 `knowledge.py` 中抽成 rule_based 默认 provider、HTTP 远端重排 provider 与 managed-index 托管索引查询 provider，`readiness` 会暴露知识检索配置状态。
- 补齐 Graph decision 的 OpenAI-compatible 生产 LLM provider：`CLOSER_GRAPH_DECISION_PROVIDER=openai/llm` 会向 chat-completions endpoint 发送 system/user JSON 决策请求，严格解析模型返回的 decision JSON，并在 readiness 中暴露 model、endpoint、api_key_env 与 api_key_configured。
- 新增 `app/services/knowledge_index_providers.py`，知识入库后可通过 `CLOSER_KNOWLEDGE_INDEX_PROVIDER=http/managed` 把 chunk、embedding 与租户 scope upsert 到托管语义索引；默认 disabled 保持测试确定性，`readiness` 暴露索引同步配置状态。
- 新增 `app/services/demo.py` 与 `app/routers/demo.py`，`POST /api/v1/demo/seed` 提供确定性演示种子，锁住询盘入站、甄别、匹配、报价、护栏审批和跟进的后端兜底主链路。
- 新增 `scripts/demo_flow.py` 与 `docs/DEMO_RUNBOOK.md`，把演示主链路折叠成可 dry-run、可审批发送、可调度的本地彩排路径。
- 新增 `scripts/production_check.py` 与 `docs/PRODUCTION_RUNBOOK.md`，把生产部署前 health/readiness/alerts 检查、scheduler/monitoring 显式触发和 provider 核对折叠成可执行路径。
- 新增 `docs/ENVIRONMENT.md`，把散落在 app/services、app/agent、scripts 与 frontend/playwright.config.js 的 `CLOSER_*` 配置折叠成上线环境变量地图。
- 新增 `frontend/` React/Vite 工作台，接入 `/dashboard/metrics`、`/inquiries`、`/customers`、`/customers/{id}`、`/quotations/{id}`、`/products`、`/pricing-rules`、`/pricing-rules/{id}`、`/pricing-rules/{id}/versions`、`/channels`、`/channels/{id}/rotate-credentials`、`/approvals`、`/notifications`、`/settings`、`/ops/readiness`、`/demo/seed` 与 `/workers/run-due`。
- 前端价格与渠道烟测通过：本地浏览器执行 Demo Seed、价格规则更新、版本历史查看与渠道凭据轮换，证据截图 `/private/tmp/closer-pricing-channel-smoke.png`。
- 新增 `frontend/playwright.config.js` 与 `frontend/e2e/workbench.spec.js`，把前端主链路烟测固化为 `npm run test:e2e`；新增 `frontend/src/catalog.jsx`，将产品/价格/渠道 UI 从 `App.jsx` 拆出，组合根从 790 行降到 639 行。
- 补齐前端基础移动/窄屏与长列表交互：列表面板拥有滚动边界，窄屏行布局自然折成单列，按钮和文本不再撑出横向滚动；Playwright 以 desktop/mobile 两个 project 验证主链路与 `scrollWidth <= clientWidth`，窄屏截图见 `/private/tmp/closer-responsive-products.png`。
- 补齐客户/审批前端 E2E：Playwright 以 desktop/mobile 两个 project 打开客户档案、验证客户活动与报价详情、执行行级审批发送，并保持无横向溢出；`App.jsx` 审批队列从“批准第一个”改为按 approval id 行级批准。
- 补齐通知/设置前端 E2E：Playwright 以 desktop/mobile 两个 project 保存卖家设置、归档审批通知、触发 workers 调度入口，并保持无横向溢出。
- 补齐真实数据密集列表前端 E2E：Playwright 通过公开 `/demo/seed` 与 `/webhooks/site_form` API 注入 24 条长文本询盘，验证收件箱和客户列表以 20 条页面密度展示、产生纵向滚动并保持桌面/移动无横向溢出。
- 补齐本地生产形态视觉 QA：生成 `/private/tmp/closer-visual-desktop.png` 与 `/private/tmp/closer-visual-mobile.png`，记录 1280x900 与 390x844 两个视口的客户密集列表指标。

## 仍未完成或仅完成边界

- Agent 编排层已有拆分后的 Pydantic Graph 八步骨架、graph_domain 子域、可配置 PydanticAI model 边界、graph decision provider 边界和环境变量地图；默认仍是 rule_based，本地可测，生产 LLM 决策 provider 已可配置但尚未接入真实 key/model、线上提示词评估与工具选择调优。
- 大模型服务未接真实供应商；解析、应答、议价仍是确定性/边界实现。
- RAG 已有 deterministic hash 默认实现、OpenAI-compatible embedding provider、knowledge index upsert provider 与 knowledge search provider 边界；默认仍是测试友好的 disabled/rule_based 本地形态，生产要显式配置 embedding/search/index provider/API key，并部署真实托管语义索引服务。
- 邮件 IMAP 轮询已有可插拔客户端边界、手动 poll-email API、统一 run-due worker、scheduler 单入口、readiness 配置画像、ops alerts、monitoring sink 与 production_check 接线路径；SMTP 实发与 WhatsApp Cloud API 实发已有可插拔客户端边界、delivery_attempt 失败重试记录、deterministic retry worker、手动/调度 API 与回执同步入口，仍缺生产凭据实际配置、外部队列/cron 实际部署与外部监控系统实际接入。
- 多币种与汇率换算已有确定性 MVP；全局汇率源 provider、规则覆盖 provider、后台刷新/确认 API、缓存、过期策略、人工确认、worker 定时刷新入口、scheduler 单入口、production_check 显式调度入口与审计日志已有本地规则，仍缺真实生产汇率服务 endpoint/key 配置与外部 cron/queue 实际部署。
- 产品库与价格规则 API 仍是 MVP 最小面：缺少批量更新与价格审批策略配置。
- channel_account.credentials 已封存存储并支持 seal secret 重封轮换，readiness 会暴露缺失 `CLOSER_CREDENTIALS_SECRET`、legacy seal 与 plaintext 风险；当前仍为标准库实现的 MVP 封装。Seller API key 签发/撤销轮换已落地。
- 前端 React/Vite 工作台已有可构建、可联调、可 E2E 的操作面；基础移动/窄屏视觉、长列表滚动边界、客户/报价/审批/通知/设置路径 E2E、真实数据密集列表走查与本地生产形态视觉 QA 已补；真实线上环境视觉复核仍需部署后执行。
- 队列、Redis、外部可观测尚未落地；PI 文本与 PDF 已有对象存储边界，且对象存储 backend 已支持 local/http 两种实现。

## 下一步优先级

1. 按 `docs/ENVIRONMENT.md` 配置真实 graph decision LLM key/model，做线上提示词评估与工具选择调优，同时保留 deterministic tests 与显式 provider 注入。
2. 配置并部署真实托管语义索引服务，联调 knowledge index upsert 与 managed-index query，同时保持本地测试继续使用 deterministic fake。
3. 按 `docs/PRODUCTION_RUNBOOK.md` 部署外部队列/cron 调用 `/ops/scheduler/run`，并把 ops monitoring webhook 接入真实监控系统，同时保持测试中使用 deterministic fake。
4. 配置真实生产汇率服务 endpoint/key，部署外部 cron/queue 实际调度，并做前端 dashboard 可视化联调。
5. 把审计告警纳入部署配置，并让 readiness 结果进入外部监控。
6. 真实线上环境部署后，按 `docs/VISUAL_QA.md` 复核生产域名视觉状态。
