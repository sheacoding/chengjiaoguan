# catalog_domain/
> L2 | 父级: ../CLAUDE.md

成员清单
__init__.py: 配置域服务包入口，汇总产品、导入、价格、渠道和看板服务导出。
channels.py: 渠道账号服务，创建封存凭据的 channel_account、列出卖家渠道并执行凭据 seal secret 重封轮换。
common.py: 配置域共享 helper，处理分页、产品租户校验与空字符串规整。
dashboard.py: 看板指标服务，计算询盘 pipeline、会话接管、审批、报价、投递、跟进与汇率缓存健康指标。
imports.py: 产品导入服务，解析 CSV/XLSX 并返回行级错误报告。
pricing.py: 价格规则服务，创建、读取、更新、列出 pricing_rule 与 pricing_rule_version，按请求 rates/规则 endpoint/全局汇率 provider 刷新 exchange_rate_cache，并校验阶梯价、物流成本、静态汇率、汇率缓存与金额正数约束。
products.py: 产品库服务，处理 product CRUD、软删除和审计日志。

架构边界
产品、价格、价格规则版本、汇率缓存、渠道、凭据轮换、导入、看板各自只承载一种变化原因；dashboard.py 只读聚合运营事实，不推进状态机；pricing_rule_version 只保存不可变快照，不参与报价计算；汇率定时刷新只扫描 pricing_rule 的 exchange_rate_provider 配置，实际获取先走规则内 rates/endpoint，再回退到 exchange_rate_sources 的全局 provider；app/services/catalog.py 只做旧导入兼容，不再承载业务规则。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
