# migrations/
> L2 | 父级: ../CLAUDE.md

成员清单
001_initial.sql: PostgreSQL 初始 DDL，创建 seller、seller_api_key、channel_account、product、pricing_rule、pricing_rule_version、customer、inquiry、conversation、message、delivery_attempt、quotation、followup_task、knowledge_chunk、notification、audit_log、approval 及索引。

架构边界
迁移表达生产数据库真相；app/models.py 表达 ORM 真相；两者字段、类型、索引必须同构。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
