"""
/* ========================================================================== */
/* GEB L3: 配置域服务包根                                                     */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 catalog_domain 的 products、imports、pricing、channels、dashboard 模块
 * [OUTPUT]: 对外汇总产品 CRUD、导入报告、价格规则、价格规则版本、汇率缓存刷新确认、汇率定时刷新、渠道账号、凭据轮换与 dashboard metrics 服务
 * [POS]: services/catalog_domain 的稳定包入口，被 app.services.catalog 兼容门面重导出
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app.services.catalog_domain.channels import create_channel, list_channels, rotate_channel_credentials
from app.services.catalog_domain.dashboard import dashboard_metrics
from app.services.catalog_domain.imports import (
    ProductImportError,
    ProductImportFailed,
    ProductImportResult,
    import_products,
    import_products_with_report,
)
from app.services.catalog_domain.pricing import (
    confirm_pricing_rule_exchange_rate_cache,
    create_pricing_rule,
    get_pricing_rule,
    list_pricing_rule_versions,
    list_pricing_rules,
    refresh_pricing_rule_exchange_rate_cache,
    run_due_pricing_rule_exchange_rate_refreshes,
    update_pricing_rule,
)
from app.services.catalog_domain.products import (
    create_product,
    delete_product,
    get_product,
    list_products,
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
