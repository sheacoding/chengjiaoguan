"""
/* ========================================================================== */
/* GEB L3: 产品匹配测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLite 会话夹具、agent_tools、models 与 product_matching 服务
 * [OUTPUT]: 验证产品字段 token 命中、排序、解释与软删除过滤
 * [POS]: tests 的产品匹配证明文件，锁住询盘理解到产品候选的确定性桥梁
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import agent_tools, models
from app.services.product_matching import match_product


def _seed_products(db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    lamp = models.Product(
        seller_id=1,
        name="LED Desk Lamp",
        sku="LAMP-01",
        specs={"certification": "CE", "brightness": "adjustable"},
        description="Aluminum desk lamp for hotel and office projects.",
        status="active",
    )
    bottle = models.Product(
        seller_id=1,
        name="Insulated Water Bottle",
        sku="BOT-02",
        specs={"capacity": "500ml"},
        description="Stainless steel bottle with logo printing.",
        status="active",
    )
    db_session.add_all([lamp, bottle])
    db_session.flush()
    return lamp, bottle


def test_match_product_ranks_best_product_from_requirement(db_session):
    lamp, _ = _seed_products(db_session)

    matches = match_product(
        db_session,
        1,
        {"product": "adjustable LED desk lamp", "certification": "CE"},
    )

    assert matches[0]["product_id"] == lamp.id
    assert matches[0]["score"] > 0
    assert set(matches[0]["matched_fields"]) >= {"name", "specs"}


def test_match_product_is_tenant_scoped(db_session):
    _seed_products(db_session)
    db_session.add(models.Seller(id=2, name="Other Exporter", email="other@example.com"))
    db_session.add(
        models.Product(
            seller_id=2,
            name="LED Desk Lamp",
            sku="PRIVATE",
            specs={"certification": "CE"},
            description="Private catalog item.",
            status="active",
        )
    )

    matches = agent_tools.match_product(db_session, 2, "LED desk lamp CE")

    assert len(matches) == 1
    assert matches[0]["sku"] == "PRIVATE"


def test_match_product_ignores_inactive_products(db_session):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    db_session.add(
        models.Product(
            seller_id=1,
            name="Archived LED Lamp",
            sku="OLD",
            specs={"certification": "CE"},
            status="inactive",
        )
    )

    assert match_product(db_session, 1, "LED lamp CE") == []
