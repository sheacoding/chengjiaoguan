# chengjiaoguan-closer - 跨境 B2B AI 询盘成交后端
Python 3.12 + FastAPI + SQLAlchemy + Pydantic + PydanticAI + PostgreSQL/pgvector + SQLite tests

<directory>
app/ - 后端机器相：HTTP API、Agent 编排、工具门面、数据模型、确定性业务服务 (3子目录: agent, routers, services...)
docs/ - 语义相执行记录：排期、范围、任务完成顺序 (0子目录)
frontend/ - 前端机器相：React/Vite 工作台，调用公开 API 展示看板、询盘、客户、产品/价格/渠道、审批与设置，并用 Playwright 验证 UI 接缝 (2子目录: e2e, src...)
migrations/ - 生产数据库形态：PostgreSQL/pgvector DDL (0子目录)
scripts/ - 演示自动化：只走公开 HTTP API 的 demo 主链路脚本 (0子目录)
tests/ - 行为证明：SQLite 内存库下的 API、工具、服务契约测试 (0子目录)
</directory>

<config>
pyproject.toml - Python 包、依赖、pytest 路径与 setuptools 发现规则
.gitignore - 排除系统元数据、虚拟环境、缓存、构建产物、Playwright 测试产物、本地数据库、密钥与临时目录
AGENTS.md - Codex/Agent 协作入口，与本文件保持项目契约同构
Closer 工作台（离线版）.html - 前端离线设计真源，内嵌工作台原型、design tokens、示例数据与交互结构
CLAUDE.md - L1 项目宪法：全局地图、工程规则、API 默认契约
</config>

架构决策：
FastAPI 只承载 HTTP 边界；业务规则落在 app/services；Agent 编排落在 app/agent；Agent 工具只能经 app/agent_tools.py 调用稳定服务门面；数据库模型集中在 app/models.py；测试用 SQLite 保持确定性，生产迁移保留 pgvector 形态。

法则：极简·稳定·导航·版本精确

# Closer Backend Collaboration Guide

## Project

Closer is a cross-border B2B AI inquiry closing agent for small exporters. The MVP backend must support this demo path:

1. Inbound inquiry enters through a channel adapter.
2. The system creates or links a customer, inquiry, conversation, and first message.
3. The inquiry is scored as grade A/B/C with explainable signals.
4. Product and knowledge matches ground the reply.
5. The quote engine creates a structured quotation from pricing rules.
6. Floor-price and sensitive-action guardrails create an approval instead of sending unsafe content.
7. A human can review, edit, approve, reject, take over, release, and send.
8. Follow-up tasks keep unreplied inquiries moving.

## Ownership

Role A owns the backend-heavy vertical from the schedule:

- Channel gateway and adapters: site form, email IMAP/SMTP, WhatsApp Cloud API.
- Inquiry scoring and CRM creation.
- Inquiry, conversation, message, takeover, and release APIs.
- Quote engine, quote tools, and PI generation.
- Knowledge ingestion, lightweight RAG search, and product matching.
- `send_message` tool with approval handoff when guardrails trigger.
- Approvals, quotations, and follow-up APIs/tools assigned to A in the balanced plan.

Role B owns the separate Agent orchestration skeleton and global guardrail policy. Keep A-owned tool signatures stable so B can call them from PydanticAI.

## Engineering Rules

- Backend stack: Python, FastAPI, SQLAlchemy, Pydantic, PostgreSQL/pgvector in production, SQLite for local tests.
- Keep API responses aligned with the Backend API Contract under `/api/v1`.
- Enforce tenant isolation by `seller_id`; tests may use `X-Seller-Id: 1`.
- Store money as `Decimal` in services and database models.
- Use deterministic services in tests; do not call real LLMs, IMAP, SMTP, or WhatsApp APIs in unit tests.
- Every completed schedule task must include focused tests and a commit after tests pass.
- Do not commit generated caches, local databases, secrets, or `tmp/`.

## Verification

Use the bundled Python runtime or any Python 3.12 environment:

```powershell
python -m pip install -e .[dev]
python -m pytest
```

For demo development, start the API with:

```powershell
uvicorn app.main:app --reload
```

## API Contract Defaults

- Base path: `/api/v1`
- Auth: `Authorization: Bearer seller:<id>` for local MVP token parsing; tests may still use `X-Seller-Id`, defaulting to seller `1`.
- Error shape: `{ "error": { "code": "...", "message": "..." } }`
- Pagination shape: `{ "items": [...], "total": n, "page": n, "page_size": n }`
