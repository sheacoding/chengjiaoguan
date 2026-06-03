"""
/* ========================================================================== */
/* GEB L3: 配置与看板服务兼容门面                                             */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 app.services.catalog_domain 的产品、导入、价格、价格规则版本、汇率缓存刷新确认、汇率定时刷新、渠道、凭据轮换与看板服务
 * [OUTPUT]: 对外重新导出产品 CRUD、价格规则、价格规则版本、汇率缓存刷新确认、汇率定时刷新、渠道账号、凭据轮换、产品导入/错误报告与 dashboard metrics
 * [POS]: services 的旧导入兼容层，真实配置域规则已迁入 catalog_domain/
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app.services.catalog_domain import (
    ProductImportError,
    ProductImportFailed,
    ProductImportResult,
    confirm_pricing_rule_exchange_rate_cache,
    create_channel,
    create_pricing_rule,
    create_product,
    dashboard_metrics,
    delete_product,
    get_pricing_rule,
    get_product,
    import_products,
    import_products_with_report,
    list_channels,
    list_pricing_rule_versions,
    list_pricing_rules,
    list_products,
    refresh_pricing_rule_exchange_rate_cache,
    rotate_channel_credentials,
    run_due_pricing_rule_exchange_rate_refreshes,
    update_pricing_rule,
    update_product,
)

__all__ = [
    "ProductImportError",
    "ProductImportFailed",
    "ProductImportResult",
    "confirm_pricing_rule_exchange_rate_cache",
    "create_channel",
    "create_pricing_rule",
    "create_product",
    "dashboard_metrics",
    "delete_product",
    "get_pricing_rule",
    "get_product",
    "import_products",
    "import_products_with_report",
    "list_channels",
    "list_pricing_rule_versions",
    "list_pricing_rules",
    "list_products",
    "refresh_pricing_rule_exchange_rate_cache",
    "rotate_channel_credentials",
    "run_due_pricing_rule_exchange_rate_refreshes",
    "update_pricing_rule",
    "update_product",
]
