# Production Runbook
> L3 | 父级: ./CLAUDE.md

<!--
/**
 * [INPUT]: 依赖 /ops/readiness、/ops/alerts、/ops/scheduler/run、scripts/production_check.py 与生产 provider 配置边界
 * [OUTPUT]: 对外提供生产部署前检查、外部 cron/monitoring 接线与 provider 配置核对路径
 * [POS]: docs 的生产彩排镜像，把剩余真实部署缺口折叠成可执行检查清单
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
-->

## 部署前检查

```bash
.venv/bin/python scripts/production_check.py \
  --base-url https://api.example.com \
  --token "$CLOSER_PRODUCTION_TOKEN" \
  --json
```

默认只读检查 `health`、`readiness`、`alerts`。`--token` 使用正式 `cak_` API key；没有 token 时脚本退回本地 `Bearer seller:<id>` shortcut，只适合开发环境。

## 调度彩排

```bash
.venv/bin/python scripts/production_check.py \
  --base-url https://api.example.com \
  --token "$CLOSER_PRODUCTION_TOKEN" \
  --run-scheduler \
  --json
```

`--run-scheduler` 会调用 `/api/v1/ops/scheduler/run`，可能执行 due follow-up、delivery retry、价格规则汇率刷新和启用的 email polling。生产 cron/queue 只需要定时调用这一条入口；若要跳过外部监控上报，用 `--no-monitoring`。

## Provider 核对

完整环境变量地图见 `docs/ENVIRONMENT.md`。下面是上线前必须不再依赖本地默认值的关键组：

- Agent: `CLOSER_AGENT_MODEL`、`CLOSER_AGENT_API_KEY_ENV` 指向真实模型和 key。
- Graph decision: `CLOSER_GRAPH_DECISION_PROVIDER=openai` 或 `http`，并配置 model/endpoint/key。
- RAG: 配置 embedding provider、knowledge index provider 与 knowledge search provider。
- Delivery: `CLOSER_DELIVERY_MODE=live` 后，email/WhatsApp channel 必须有完整凭据。
- Exchange: 配置全局 `CLOSER_EXCHANGE_RATE_*` 或每条 pricing rule 的 `exchange_rate_provider`，刷新后必须人工确认 cache。
- Monitoring: `CLOSER_OPS_MONITOR_PROVIDER=webhook` 与 `CLOSER_OPS_MONITOR_ENDPOINT` 接入真实监控系统。
- Credentials: `CLOSER_CREDENTIALS_SECRET` 必须存在；旧 key 轮换期才使用 `CLOSER_CREDENTIALS_PREVIOUS_SECRETS`。
- Storage: PI 文件产物按 `CLOSER_DOCUMENT_STORAGE_*` 指向 local 或 HTTP backend。

## 判定规则

`readiness.status=ready` 且 `alerts.status=ok` 才能认为部署配置干净。`degraded/attention` 允许演示但必须记录风险；`unready/critical` 不能进入真实客户链路。

真正的缺口不该藏在代码里。没有真实 provider 凭据时，只能完成边界、配置画像和检查路径；接入真实 key、外部 cron、监控 webhook 与一次生产环境彩排后，T29-T31 才算闭环。
