# scripts/
> L2 | 父级: ../CLAUDE.md

成员清单
demo_flow.py: Demo 主链路脚本，通过 HTTP API 调用 /demo/seed、审批发送与 workers 调度，不直接访问数据库。
production_check.py: 生产部署检查脚本，通过公开 HTTP API 读取 health/readiness/alerts，并可显式触发 scheduler/monitoring 入口。

架构边界
scripts/ 只编排公开 API，不能绕过 FastAPI、services 护栏或租户鉴权；演示动作必须可 dry-run，避免默认触发外部副作用。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
