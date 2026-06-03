# routers/
> L2 | 父级: ../CLAUDE.md

成员清单
__init__.py: 路由包标记，汇总 HTTP API 分域模块。
common.py: HTTP 响应序列化与租户 scoped require helper，供各 router 复用。
approvals.py: approvals 队列路由，处理列表、修改、批准、拒绝。
auth.py: auth 路由，处理 API key 列表、签发与撤销轮换。
catalog.py: products、pricing-rules、pricing-rule versions、exchange-rate-cache、channels、渠道凭据轮换、dashboard 配置与看板路由。
channel_operations.py: channels 运维路由，处理 email poll-email 入站轮询入口与 delivery receipt 同步入口。
conversations.py: conversations 与 messages 路由，处理详情、消息、接管、释放与人工消息投递。
customers.py: customers CRM 路由，处理客户列表、详情聚合、档案修改与客户数据擦除。
delivery_attempts.py: delivery-attempts 运维路由，处理投递尝试列表、单条 retry 与 due retry 调度入口。
demo.py: demo 演示路由，暴露 /demo/seed 确定性主链路种子入口。
exports.py: exports 数据导出路由，处理 customers、inquiries、quotations CSV 下载。
inquiries.py: inquiries 路由，处理列表、详情、分级与状态修正。
knowledge.py: knowledge 路由，处理知识入库与检索。
notifications.py: notifications 路由，处理通知列表、未读筛选与 read/archived 状态修改。
quotations.py: quotations 路由，处理报价详情、修改、发送与底价发送审批移交。
settings.py: settings 租户设置路由，处理卖家信息、AI 身份披露开关与 settings JSON 修改。
webhooks.py: channel webhook 路由，处理 site_form 与 WhatsApp 入站归一化。
workers.py: workers/ops 运维路由，处理到期 follow-up、投递重试、价格规则汇率刷新、启用 email 轮询的统一触发入口、scheduler 组合入口、生产 readiness 画像与运行 alerts。

架构边界
router 只处理 HTTP 参数、错误翻译、提交事务与响应组装；业务规则委派给 app/services；共享序列化放 common.py，避免 main.py 回潮成泥团。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
