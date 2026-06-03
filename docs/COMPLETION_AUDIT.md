# Completion Audit
> L3 | 父级: ./CLAUDE.md

<!--
/**
 * [INPUT]: 依赖 EXECUTION_PLAN.md、IMPLEMENTATION_AUDIT.md、DEMO_RUNBOOK.md、PRODUCTION_RUNBOOK.md、ENVIRONMENT.md、VISUAL_QA.md 与当前测试证据
 * [OUTPUT]: 对外提供项目完成度矩阵，区分已实现、本地可证、生产边界与外部阻塞
 * [POS]: docs 的收口审计镜像，把分散的计划、实现、演示、上线语义折叠成最终判定表
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
-->

## 审计口径

完成不等于“有代码”。完成必须同时满足机器相和语义相：

- 已完成：代码、API、测试、文档都存在，本地确定性环境可复核。
- 边界完成：provider/client/API/脚本/readiness 已存在，但需要真实外部系统接线才能闭环。
- 外部阻塞：缺少真实 key、域名、cron、monitoring、托管服务或生产彩排，当前仓库无法单方面完成。

## 完成度矩阵

| 范围 | 要求来源 | 本地证据 | 状态 | 剩余动作 |
| --- | --- | --- | --- | --- |
| 原始规格读取 | `EXECUTION_PLAN.md` 与 `IMPLEMENTATION_AUDIT.md` 的 Source Documents 列表 | 需求、产品、架构、数据库、API、Agent 工具、排期、市场调研、离线工作台均已登记 | 已完成 | 无 |
| 入站主链路 | MVP path 1-2，T05-T10 | site form、email、WhatsApp 入站边界；customer、inquiry、conversation、message 创建；相关 API 测试覆盖 | 已完成 | 生产渠道凭据另见外部项 |
| 询盘甄别与客户画像 | MVP path 3，T08-T09 | `score_inquiry`、`get_customer`、客户列表/详情/擦除 API 与测试 | 已完成 | 真实模型增强不影响本地确定性闭环 |
| 知识与产品匹配 | MVP path 4，T13-T14 | 知识切块、embedding provider、index upsert provider、search provider、产品 token 匹配与测试 | 边界完成 | 配置真实 embedding/search/index provider 与托管语义索引 |
| 报价与 PI | MVP path 5，T11-T12 | MOQ、阶梯价、汇率、底价、PI 文档、对象存储边界与测试 | 已完成 | 生产对象存储 backend 与真实汇率源另见外部项 |
| 护栏与人工审批 | MVP path 6-7，T15/T18 | `send_message`、quotation send、PI generate、handoff approval、副作用执行器与通知闭环测试 | 已完成 | 无 |
| 跟进与后台任务 | MVP path 8，T19 | follow-up、delivery retry、email polling、exchange refresh、workers run-due 与 ops scheduler 测试 | 边界完成 | 外部 cron/queue 定时调用 `/ops/scheduler/run` |
| API 契约与租户隔离 | Backend API Contract | `/api/v1`、error shape、pagination、Bearer API key、seller shortcut、SQLite deterministic tests | 已完成 | 生产必须使用正式 `cak_` token |
| Agent 编排 | Agent 工具清单、T04/T16 | PydanticAI runtime、八步 Graph、工具门面、rule_based/HTTP/OpenAI-compatible decision provider 与测试 | 边界完成 | 接真实 LLM key/model，做线上 prompt 与工具选择评估 |
| 配置与运维面 | API 契约配置项、T29-T31 | products、pricing rules、channels、settings、dashboard、readiness、alerts、monitoring sink、production check 脚本 | 边界完成 | 接真实 monitoring webhook、生产 provider 与部署平台 |
| 前端工作台 | 产品设计文档 M1-M10、T20-T28 | React/Vite 工作台、build、Playwright desktop/mobile E2E、视觉 QA 截图与无横向溢出指标 | 本地已完成 | 真实线上域名和生产 API 组合仍需视觉复核 |
| Demo 主链路 | T30/T31 | `/demo/seed`、`scripts/demo_flow.py`、`DEMO_RUNBOOK.md`、前端 Demo 操作与 E2E | 本地已完成 | 用真实部署执行最后生产彩排 |
| 测试证明 | 工程规则 | `.venv/bin/python -m pytest` 记录为 `165 passed`；前端 `npm run build`、`npm run test:e2e` 记录为 `8 passed`；`npm audit --json` 记录 0 漏洞 | 已完成 | 修改代码后继续复跑聚焦测试或全量测试 |
| 分形文档同构 | GEB 协议 | L1/L2/L3 文档已覆盖 `app`、`tests`、`docs`、`scripts`、`frontend`；GEB 扫描作为复核命令 | 已完成 | 每次文件职责变化继续更新对应 CLAUDE.md 与 L3 |

## 外部阻塞清单

这些不是代码缺口，不能用本地 mock 假装完成：

| 阻塞项 | 当前仓库已提供 | 真正完成条件 |
| --- | --- | --- |
| 真实 LLM/Agent provider | `CLOSER_AGENT_MODEL`、`CLOSER_AGENT_API_KEY_ENV`、Graph decision provider 边界、readiness 画像 | 部署真实 key/model，线上跑 prompt、工具调用与失败回退评估 |
| 真实 RAG/向量服务 | embedding、index upsert、search provider 与环境变量地图 | 接托管语义索引，完成 upsert/query 联调和容量/延迟检查 |
| 真实邮件与 WhatsApp 投递 | SMTP/WhatsApp Cloud client、delivery_attempt、retry、receipt sync | 配置生产 channel credentials，打开 `CLOSER_DELIVERY_MODE=live` 并完成小流量实发 |
| 真实汇率源 | exchange-rate provider、cache refresh/confirm、worker/scheduler 接口 | 配置生产 endpoint/key，刷新待确认缓存，人工确认后用于报价 |
| 外部调度 | `/ops/scheduler/run`、workers、`scripts/production_check.py --run-scheduler` | 部署 cron/queue 定时调用，观察 due jobs、失败重试、汇率刷新和 email polling |
| 外部监控 | ops alerts、readiness、monitoring sink provider | 接真实 webhook/监控系统，验证 warning/critical 可见且不丢失 |
| 真实线上视觉与演示彩排 | 本地 Vite/Playwright/视觉截图、Demo runbook | 生产域名、真实 API、浏览器组合下复跑视觉 QA 与 Demo 主链路 |

## 判定

当前状态可以判定为：本地 MVP 机器相已完成，生产接线边界已完成，真实外部系统闭环未完成。

因此，项目不应被标记为“全部完成”。正确状态是：仓库内可交付部分已收口；剩余工作受真实 provider、生产部署、外部调度、监控接入和线上彩排阻塞。

## 复核命令

```bash
.venv/bin/python -m pytest
cd frontend && npm run build
cd frontend && npm run test:e2e
cd frontend && npm audit --json
rg --files-without-match '\[PROTOCOL\]: 变更时更新此头部，然后检查 CLAUDE.md' app tests docs migrations scripts frontend -g '*.py' -g '*.md' -g '*.js' -g '*.jsx' -g '*.css' -g '*.html'
```
