# Demo Runbook
> L3 | 父级: ./CLAUDE.md

<!--
/**
 * [INPUT]: 依赖 /api/v1/demo/seed、approvals、conversations、workers API、scripts/demo_flow.py 与 frontend Playwright E2E
 * [OUTPUT]: 对外提供本地演示主链路步骤，从种子数据到人工审批发送、调度入口再到前端浏览器验证
 * [POS]: docs 的演示操作镜像，把后端可演示能力折叠成可执行路径
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
-->

## 目标

用公开 HTTP API 走通后端主链路：site form 询盘、A 级评分、产品与知识匹配、报价、护栏挂起、人工审批发送、消息查看与调度入口。

## 启动

```bash
uvicorn app.main:app --reload
```

默认本地地址是 `http://127.0.0.1:8000`，默认租户是 `Authorization: Bearer seller:1`。

前端工作台：

```bash
cd frontend
npm install
npm run dev
```

Vite 默认地址是 `http://127.0.0.1:5173`，开发期会把 `/api` 代理到 FastAPI。

## 预演

```bash
.venv/bin/python scripts/demo_flow.py --dry-run --approve --run-workers --json
```

预演只打印 HTTP 步骤，不访问 API。

## 生成演示数据

```bash
.venv/bin/python scripts/demo_flow.py --base-url http://127.0.0.1:8000
```

脚本会调用 `/api/v1/demo/seed`，幂等创建演示产品、价格规则、知识、询盘、报价、pending message_send 审批与 follow-up。

## 执行审批发送

```bash
.venv/bin/python scripts/demo_flow.py --base-url http://127.0.0.1:8000 --approve
```

这一步会批准 demo seed 返回的 pending approval，并通过后端护栏后的正常审批执行器发送 AI 消息。

## 调度入口

```bash
.venv/bin/python scripts/demo_flow.py --base-url http://127.0.0.1:8000 --approve --run-workers
```

`--run-workers` 会额外调用 `/api/v1/workers/run-due`。默认 demo follow-up 是 24 小时后到期，所以本地即时运行通常只证明调度入口可用。

## 前端 E2E

```bash
cd frontend
npm run test:e2e
```

Playwright 会自动启动 FastAPI 与 Vite，并在本地 Chrome 中验证 Demo Seed、客户档案、报价详情、审批发送、通知归档、设置保存、调度入口、密集询盘/客户列表、价格规则创建/版本/更新、渠道凭据轮换与无横向溢出。若本机 Chrome channel 不同，可设置 `PLAYWRIGHT_BROWSER_CHANNEL`。

## 核心法则

演示脚本只走公开 API，不直接访问数据库，不绕过审批，不绕过租户鉴权。默认 delivery mode 是 payload-only，不会触发真实 SMTP、WhatsApp 或外部网络发送。
