# frontend/e2e/
> L2 | 父级: ../CLAUDE.md

成员清单
workbench.spec.js: Playwright 浏览器烟测，走桌面/移动 Demo Seed、客户档案、报价详情、审批发送、通知归档、设置保存、调度入口、设计稿导航页、密集询盘/客户列表、产品页、价格规则版本/更新、渠道凭据轮换与横向溢出检查。

架构边界
e2e/ 只通过浏览器访问 Vite 工作台和公开 `/api/v1` 代理，不直接访问数据库，不绕过审批，不伪造后端状态。测试必须可重复，依赖 demo seed 的幂等数据、本地 payload-only 投递边界和桌面/移动视口。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
