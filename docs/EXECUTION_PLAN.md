# Execution Plan
> L3 | 父级: ./CLAUDE.md

<!--
/**
 * [INPUT]: 依赖根目录原始规格文档、CLAUDE.md、AGENTS.md 与当前后端排期
 * [OUTPUT]: 对外提供开发提交顺序、MVP 范围裁剪与验证约束
 * [POS]: docs 的执行路径镜像，和 IMPLEMENTATION_AUDIT.md 共同描述计划与现实的差距
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
-->

## Source Documents Verified

- `成交官_需求规格说明书_V1.0.docx`: M1-M10 功能需求、P0/P1/P2 优先级、M8 客户档案、M10 数据看板、非功能安全合规。
- `成交官_产品设计文档_V1.1.docx`: Agent 工作流、前端 7 页面、会话右侧客户档案抽屉、报价规则与产品库、首次配置向导。
- `成交官_技术架构设计文档_V1.1.docx`: 接入层、Agent 编排层、能力服务层、数据层；队列、缓存、对象存储、向量库、护栏与审计。
- `成交官_数据库设计文档_V1.0.docx`: seller 根租户、13 张核心表、多租户索引、jsonb 可变字段、软删除与审计。
- `成交官_后端API契约_V1.0.docx`: `/api/v1` 主链路、错误形状、分页形状、入站幂等、配置与看板接口。
- `成交官_Agent工具接口清单_V1.0.docx`: 10 个工具、PydanticAI Graph 八步状态机、human-in-the-loop 审批约定。
- `成交官_两人开发分工排期表_方案A平衡版_V2.1.xlsx`: T01-T31 排期；A 负责后端大头，队友负责前端与部分 Agent 编排。
- `跨境B2B_AI询盘成交Agent_市场调研报告.docx`: inbound 询盘成交定位、小微工贸卖家、报价/议价差异化与主要风险。
- `Closer 工作台（离线版）.html`: 前端视觉参考；当前仓库已有 React/Vite 工作台、移动/窄屏基础适配与 Playwright 主链路 E2E，仍需更全面视觉 QA 与部署联调。

## Current Evidence

- 验证命令：`.venv/bin/python -m pytest`
- 当前结果：`165 passed`
- 前端验证：`cd frontend && npm run build`、`npm audit --json`、`npm run test:e2e` 当前 `8 passed`
- 视觉 QA：`docs/VISUAL_QA.md` 记录桌面 1280x900、移动 390x844 截图与无横向溢出指标
- 环境配置：`docs/ENVIRONMENT.md` 汇总所有生产 provider、投递、存储、汇率、监控、演示与 E2E 环境变量
- 完成度审计：`docs/COMPLETION_AUDIT.md` 区分仓库内已完成、本地可证、生产边界与真实外部阻塞
- 浏览器烟测：Demo Seed、价格规则更新、价格规则版本查看、渠道凭据轮换与窄屏产品页无横向溢出通过；截图见 `/private/tmp/closer-pricing-channel-smoke.png`、`/private/tmp/closer-responsive-products.png`
- GEB 扫描：`app/`、`tests/`、`docs/`、`scripts/`、`frontend/` 下 Python/Markdown/JS/JSX/CSS/HTML 文件均带 `[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md`

## Schedule Reality

已完成或已有确定性边界：

- T01/T02: API 契约、工具清单、DB schema 与 PostgreSQL migration 已落地。
- T04/T16: PydanticAI runtime 与 Pydantic Graph 八步状态机已有本地可测骨架；graph decision provider 已支持 rule_based、HTTP 与 OpenAI-compatible LLM JSON 决策，生产模型配置与策略调优仍需部署。
- T05-T07: site form、email、WhatsApp 入站/出站边界已落地，真实凭据和生产部署未配置。
- T08-T10: 甄别打分、CRM 建档、询盘/会话/消息/接管/释放 API 已落地。
- T11-T15: 报价引擎、PI 审批、知识入库/检索、产品匹配、send_message 护栏已落地。
- T17-T19: approvals、quotations、follow-up、delivery retry、workers run-due、ops scheduler/monitoring sink 已落地。
- 配置面补强: auth api-keys、products、pricing-rules、pricing-rule versions、exchange-rate-cache、channels、channel credential rotation、settings、dashboard 运营指标、customers、exports、notifications API 已落地。

### A-Owned Task Evidence

- T05: 渠道网关与 site form webhook 入库，测试见 `tests/test_site_form_webhook.py`。
- T06: Email 解析、SMTP 组合、IMAP 轮询边界，测试见 `tests/test_email_adapter.py` 与 `tests/test_email_polling.py`。
- T07: WhatsApp webhook、payload、签名与 Cloud API 客户端边界，测试见 `tests/test_whatsapp_adapter.py` 与 `tests/test_channel_delivery_clients.py`。
- T08: 询盘甄别打分与 `score_inquiry` 工具，测试见 `tests/test_scoring_tool.py`。
- T09: CRM 建档、跨渠道合并与 `get_customer` 工具，测试见 `tests/test_crm_tool.py`。
- T10: inquiries、conversations、messages、takeover、release API，测试见 `tests/test_conversation_api.py`。
- T11: 报价规则计算、MOQ、阶梯价、汇率、底价，测试见 `tests/test_quote_engine.py`。
- T12: `calc_quote`、`generate_pi`、报价文案与 PI 文件产物，测试见 `tests/test_quote_tools.py`。
- T13: 知识切块、向量 provider、索引 upsert provider 与 search provider 边界，测试见 `tests/test_knowledge.py`、`tests/test_embedding_providers.py`、`tests/test_knowledge_index_providers.py`、`tests/test_knowledge_search_providers.py`。
- T14: `match_product` 产品匹配工具，测试见 `tests/test_product_matching.py`。
- T15: `send_message` 出站工具、护栏审批、delivery_attempt，测试见 `tests/test_send_message_tool.py`。
- T18: approvals 与 quotations API，测试见 `tests/test_approvals_quotations_api.py`。
- T19: follow-up 与 unified worker 调度，测试见 `tests/test_followups.py` 与 `tests/test_workers.py`。

未完成或仅完成边界：

- T03/T20-T28: React/Vite 工作台已落地，可调用后端 API 展示看板、收件箱、客户、产品、审批、设置与 Demo 操作，并已支持产品创建、价格规则创建/编辑/版本查看、渠道创建/凭据轮换、设置保存、通知处理、客户档案抽屉、报价详情与报价发送；Playwright E2E 已覆盖桌面/移动 Demo Seed、客户档案、报价详情、审批发送、通知归档、设置保存、调度入口、密集询盘/客户列表、价格规则版本/更新、渠道凭据轮换与无横向溢出；基础移动/窄屏视觉、长列表滚动边界、真实数据密集列表走查与本地生产形态视觉 QA 已补，仍缺真实线上环境视觉复核。
- T29: 真 LLM key/model、托管语义索引、真 WhatsApp/SMTP/IMAP、生产汇率服务 endpoint/key、外部队列/cron、外部监控系统尚未部署；后端 scheduler/monitoring、全局汇率源 provider 与环境变量地图已就绪。
- T30/T31: Demo 主链路已有后端能力、`/demo/seed` 兜底假数据入口、`scripts/demo_flow.py` 演示脚本、`docs/DEMO_RUNBOOK.md`、`scripts/production_check.py`、`docs/PRODUCTION_RUNBOOK.md` 与前端 Demo/配置操作台；部署前检查、readiness/alerts、scheduler/monitoring 接线已有路径，还缺真实生产环境彩排。
- P1/P2 深化: 正式 API key 认证、GDPR 客户擦除、价格规则版本化、通知系统与 channel credential seal secret 轮换已进入 API。

## Next Implementation Queue

1. 按 `docs/ENVIRONMENT.md` 配置 production provider 并调优：LLM graph decision model/key、embedding/search/index provider、exchange-rate provider、delivery live credentials。
2. 按 `docs/COMPLETION_AUDIT.md` 的外部阻塞清单逐项核销真实 LLM、RAG、投递、汇率、cron、monitoring 与生产视觉彩排。
3. 按 `docs/PRODUCTION_RUNBOOK.md` 部署外部 cron/queue 调用 `/ops/scheduler/run`，并把 `CLOSER_OPS_MONITOR_*` 接入真实监控系统。
4. 真实线上环境部署后，按 `docs/VISUAL_QA.md` 复核生产域名视觉状态。
5. 最后做 Demo 主链路彩排：用前端 Demo 操作台或 `scripts/demo_flow.py --approve --run-workers` 生成现场数据，再走人工审批发送、消息查看、调度入口与部署联调。

## Scope Decisions

- 外部网络能力全部走 provider/client 边界；测试默认 deterministic，不调用真实 LLM、IMAP、SMTP、WhatsApp、汇率源。
- 报价与发送的危险动作在服务端护栏拦截，前端和 Agent 都不可绕过。
- SQLite 用于本地行为证明；PostgreSQL/pgvector 形态由 migration 保留。
- 兼容旧导入只保留在门面文件；新业务规则进入明确领域模块。
