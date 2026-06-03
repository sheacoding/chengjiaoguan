# Environment
> L3 | 父级: ./CLAUDE.md

<!--
/**
 * [INPUT]: 依赖 app/agent、app/services、scripts、frontend/playwright.config.js 中的 CLOSER_* 配置真源
 * [OUTPUT]: 对外提供生产/演示/测试环境变量地图、默认值、用途与上线判定
 * [POS]: docs 的部署配置镜像，把 provider key、外部服务、调度检查和本地测试配置从代码常量折叠成可读清单
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
-->

## 原则

不要提交 `.env`、密钥、token 或本地数据库。本文只记录变量名、用途和默认行为；真实值必须由部署平台或本机 secret 管理注入。

## Agent 与 LLM

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `CLOSER_AGENT_MODEL` | 未配置 | PydanticAI runtime 使用的模型名；未配置时 readiness 警告，运行时必须显式传 model。 |
| `CLOSER_AGENT_API_KEY_ENV` | provider 默认 | 指向真实模型 API key 的环境变量名；OpenAI provider 默认读取 `OPENAI_API_KEY`。 |
| `OPENAI_API_KEY` | 未配置 | OpenAI-compatible Agent、Graph decision 与 embedding provider 的默认 key 变量。 |
| `CLOSER_GRAPH_DECISION_PROVIDER` | `rule_based` | Graph 决策 provider；生产可用 `http`/`webhook`/`remote` 或 `openai`/`llm`。 |
| `CLOSER_GRAPH_DECISION_ENDPOINT` | 未配置 | HTTP 决策 provider endpoint。 |
| `CLOSER_GRAPH_DECISION_AUTH_TOKEN` | 未配置 | HTTP 决策 provider Bearer token。 |
| `CLOSER_GRAPH_DECISION_MODEL` | 未配置 | OpenAI-compatible graph decision 模型名。 |
| `CLOSER_GRAPH_DECISION_BASE_URL` | OpenAI 默认 | OpenAI-compatible chat completions base URL。 |
| `CLOSER_GRAPH_DECISION_API_KEY_ENV` | `OPENAI_API_KEY` | 指向 graph decision LLM API key 的环境变量名。 |
| `CLOSER_GRAPH_DECISION_TIMEOUT_SECONDS` | `10` | Graph decision 外部请求超时。 |

## RAG 与知识库

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `CLOSER_EMBEDDING_PROVIDER` | `deterministic` | Embedding provider；生产用 `openai`/`openai_compatible`。 |
| `CLOSER_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding 模型名。 |
| `CLOSER_EMBEDDING_ENDPOINT` | OpenAI embeddings URL | OpenAI-compatible embedding endpoint。 |
| `CLOSER_EMBEDDING_API_KEY_ENV` | `OPENAI_API_KEY` | 指向 embedding API key 的环境变量名。 |
| `CLOSER_EMBEDDING_DIMENSIONS` | `1536` | 向量维度。 |
| `CLOSER_EMBEDDING_TIMEOUT_SECONDS` | `10` | Embedding 请求超时。 |
| `CLOSER_KNOWLEDGE_INDEX_PROVIDER` | `disabled` | 知识索引 upsert provider；生产可用 `http`/`managed`。 |
| `CLOSER_KNOWLEDGE_INDEX_ENDPOINT` | 未配置 | 托管索引 upsert endpoint。 |
| `CLOSER_KNOWLEDGE_INDEX_AUTH_TOKEN` | 未配置 | 托管索引 upsert token。 |
| `CLOSER_KNOWLEDGE_INDEX_TIMEOUT_SECONDS` | `10` | 索引 upsert 请求超时。 |
| `CLOSER_KNOWLEDGE_SEARCH_PROVIDER` | `rule_based` | 知识检索 provider；生产可用 `http`/`managed`。 |
| `CLOSER_KNOWLEDGE_SEARCH_ENDPOINT` | 未配置 | 远端重排或托管索引查询 endpoint。 |
| `CLOSER_KNOWLEDGE_SEARCH_AUTH_TOKEN` | 未配置 | 检索 provider token。 |
| `CLOSER_KNOWLEDGE_SEARCH_TIMEOUT_SECONDS` | `10` | 检索请求超时。 |

## 投递、凭据与文件

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `CLOSER_DELIVERY_MODE` | `payload_only` | `live` 才触发 SMTP/WhatsApp Cloud 真实外部发送。 |
| `CLOSER_CREDENTIALS_SECRET` | 开发默认密钥 | 渠道凭据封存 HMAC/加密根密钥；生产必须配置。 |
| `CLOSER_CREDENTIALS_PREVIOUS_SECRETS` | 未配置 | 轮换期读取旧封存凭据，多个值用逗号分隔。 |
| `CLOSER_DOCUMENT_STORAGE_BACKEND` | `local` | PI 文件存储 backend；可用 `local` 或 `http`/`remote`/`s3`/`r2`/`oss` 别名。 |
| `CLOSER_DOCUMENT_STORAGE_DIR` | `tmp/pi_documents` | local backend 根目录；生产 local 模式必须改出 tmp。 |
| `CLOSER_DOCUMENT_STORAGE_ENDPOINT` | 未配置 | HTTP object storage PUT endpoint，支持 `{key}` 占位。 |
| `CLOSER_DOCUMENT_STORAGE_AUTH_TOKEN` | 未配置 | HTTP object storage Bearer token。 |
| `CLOSER_DOCUMENT_STORAGE_TIMEOUT_SECONDS` | `10` | 文件存储请求超时。 |

## 汇率、运维与部署检查

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `CLOSER_EXCHANGE_RATE_PROVIDER` | `disabled` | 全局汇率源 provider；生产可用 `http`/`remote`。 |
| `CLOSER_EXCHANGE_RATE_SOURCE` | `configured` | 汇率来源名称，进入 cache/audit。 |
| `CLOSER_EXCHANGE_RATE_ENDPOINT` | 未配置 | 汇率 HTTP endpoint，支持 `{base}` 和 `{symbols}` 占位。 |
| `CLOSER_EXCHANGE_RATE_AUTH_TOKEN` | 未配置 | 汇率 provider token。 |
| `CLOSER_EXCHANGE_RATE_TIMEOUT_SECONDS` | `10` | 汇率请求超时。 |
| `CLOSER_OPS_MONITOR_PROVIDER` | `disabled` | 运维监控 sink；生产可用 `http`/`webhook`/`remote`。 |
| `CLOSER_OPS_MONITOR_ENDPOINT` | 未配置 | scheduler 事件 webhook endpoint。 |
| `CLOSER_OPS_MONITOR_AUTH_TOKEN` | 未配置 | scheduler 事件 webhook token。 |
| `CLOSER_OPS_MONITOR_TIMEOUT_SECONDS` | `10` | 监控上报请求超时。 |
| `CLOSER_PRODUCTION_BASE_URL` | `http://127.0.0.1:8000` | `scripts/production_check.py` 默认 API 地址。 |
| `CLOSER_PRODUCTION_SELLER_ID` | `1` | `scripts/production_check.py` 默认租户。 |
| `CLOSER_PRODUCTION_TOKEN` | 未配置 | `scripts/production_check.py` 使用的正式 `cak_` token。 |

## 本地演示与 E2E

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | 空字符串 | 前端生产 API 根地址；为空时用同源 `/api` 路径。 |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite 开发代理目标。 |
| `CLOSER_DEMO_BASE_URL` | `http://127.0.0.1:8000` | `scripts/demo_flow.py` 默认 API 地址。 |
| `CLOSER_E2E_PYTHON` | `.venv/bin/python` | Playwright webServer 启动 FastAPI 的 Python 解释器。 |
| `PLAYWRIGHT_BROWSER_CHANNEL` | `chrome` | 前端 E2E 使用的本机浏览器 channel。 |
| `CI` | 未配置 | 影响 Playwright reporter 与是否复用已有 dev server。 |

## 上线判定

生产环境至少要让 `/api/v1/ops/readiness` 中 `agent_model`、`graph_decision`、`embedding_provider`、`knowledge_index`、`knowledge_search`、`exchange_rate_provider`、`monitoring_sink`、`credentials_secret`、`delivery_mode` 和 `document_storage` 不再依赖本地默认值。`readiness.status=ready` 且 `alerts.status=ok` 后，再执行 `scripts/production_check.py --run-scheduler` 做外部 cron/monitoring 彩排。
