"""
/* ========================================================================== */
/* GEB L3: 报价引擎测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest、Decimal、date、SQLite 会话夹具、app.models、quote_engine.calculate_quote 与 exchange_rate_sources
 * [OUTPUT]: 验证 MOQ、阶梯价、成本利润、物流、汇率换算、汇率源刷新、汇率缓存过期/确认与地板价判断
 * [POS]: tests 的报价算法证明文件，锁住服务层金额计算的确定性契约
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import date
from decimal import Decimal

import pytest

from app import models
from app.services.exchange_rate_sources import (
    MappingExchangeRateProvider,
    confirm_exchange_rate_cache,
    get_exchange_rate_provider_config,
    refresh_exchange_rate_cache,
)
from app.services.catalog_domain.pricing import refresh_pricing_rule_exchange_rate_cache
from app.services.quote_engine import QuoteItemInput, calculate_quote


def _seed_quote_data(db_session, *, moq=500, tiers=None, floor_price="3.20"):
    seller = db_session.get(models.Seller, 1) or models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    product = models.Product(
        seller_id=1,
        name="LED Desk Lamp 10W",
        sku="LED-10W",
        cost=Decimal("2.10"),
        moq=moq,
        currency="USD",
        status="active",
    )
    db_session.add_all([seller, customer, product])
    db_session.flush()
    inquiry = models.Inquiry(
        seller_id=1,
        customer_id=customer.id,
        source_channel="email",
        raw_content="Need lamps",
        status="new",
    )
    db_session.add(inquiry)
    db_session.flush()
    rule = models.PricingRule(
        seller_id=1,
        product_id=product.id,
        margin_rate=Decimal("0.30"),
        logistics_template={"unit_cost": "0.20", "destination_unit_costs": {"US": "0.25"}},
        tiered_prices=tiers or [{"min_qty": 1000, "price": "3.30"}, {"min_qty": 5000, "price": "3.05"}],
        valid_days=16,
        floor_price=Decimal(floor_price),
        currency="USD",
    )
    db_session.add(rule)
    db_session.flush()
    return inquiry, product


def test_calculate_quote_uses_tiered_price_and_destination_logistics(db_session):
    inquiry, product = _seed_quote_data(db_session)

    result = calculate_quote(
        db_session,
        1,
        inquiry.id,
        [QuoteItemInput(product_id=product.id, quantity=1000)],
        destination="US",
    )

    assert result.currency == "USD"
    assert result.total_amount == Decimal("3550.00")
    assert result.lines[0].unit_price == Decimal("3.55")
    assert result.valid_until is not None
    assert result.hits_floor is False


def test_calculate_quote_detects_floor_price_hit(db_session):
    inquiry, product = _seed_quote_data(db_session)

    result = calculate_quote(db_session, 1, inquiry.id, [QuoteItemInput(product_id=product.id, quantity=5000)])

    assert result.lines[0].unit_price == Decimal("3.25")
    assert result.hits_floor is False

    inquiry2, product2 = _seed_quote_data(db_session, tiers=[{"min_qty": 500, "price": "2.90"}], floor_price="3.20")
    result2 = calculate_quote(db_session, 1, inquiry2.id, [QuoteItemInput(product_id=product2.id, quantity=500)])
    assert result2.hits_floor is True


def test_calculate_quote_rejects_below_moq_quantity(db_session):
    inquiry, product = _seed_quote_data(db_session, moq=1000)

    with pytest.raises(ValueError, match="below MOQ"):
        calculate_quote(db_session, 1, inquiry.id, [QuoteItemInput(product_id=product.id, quantity=500)])


def test_calculate_quote_uses_cost_margin_when_no_tier_matches(db_session):
    inquiry, product = _seed_quote_data(db_session, tiers=[])

    result = calculate_quote(db_session, 1, inquiry.id, [QuoteItemInput(product_id=product.id, quantity=500)])

    assert result.lines[0].unit_price == Decimal("2.93")
    assert result.total_amount == Decimal("1465.00")


def test_calculate_quote_converts_rule_currency_to_requested_currency(db_session):
    inquiry, product = _seed_quote_data(db_session)
    rule = db_session.query(models.PricingRule).filter_by(product_id=product.id).one()
    rule.logistics_template = {
        "unit_cost": "0.20",
        "destination_unit_costs": {"US": "0.25"},
        "exchange_rates": {"USD": {"EUR": "0.90"}},
    }
    db_session.flush()

    result = calculate_quote(
        db_session,
        1,
        inquiry.id,
        [QuoteItemInput(product_id=product.id, quantity=1000)],
        destination="US",
        currency="EUR",
    )

    assert result.currency == "EUR"
    assert result.lines[0].unit_price == Decimal("3.20")
    assert result.lines[0].floor_price == Decimal("2.88")
    assert result.total_amount == Decimal("3200.00")


def test_calculate_quote_uses_confirmed_exchange_rate_cache(db_session):
    inquiry, product = _seed_quote_data(db_session)
    rule = db_session.query(models.PricingRule).filter_by(product_id=product.id).one()
    rule.logistics_template = {
        "unit_cost": "0.20",
        "exchange_rate_cache": {
            "confirmed": True,
            "expires_at": "2999-01-01",
            "rates": {"USD": {"EUR": "0.80"}},
        },
    }
    db_session.flush()

    result = calculate_quote(
        db_session,
        1,
        inquiry.id,
        [QuoteItemInput(product_id=product.id, quantity=1000)],
        currency="EUR",
    )

    assert result.lines[0].unit_price == Decimal("2.80")
    assert result.total_amount == Decimal("2800.00")


def test_exchange_rate_source_refreshes_cache_before_manual_confirmation(db_session):
    inquiry, product = _seed_quote_data(db_session)
    rule = db_session.query(models.PricingRule).filter_by(product_id=product.id).one()
    provider = MappingExchangeRateProvider("demo_bank", {"USD": {"EUR": "0.77"}})

    cache = refresh_exchange_rate_cache(
        rule,
        provider,
        "USD",
        ["EUR"],
        today=date(2999, 1, 1),
        ttl_days=2,
    )
    db_session.flush()

    assert cache["source"] == "demo_bank"
    assert cache["confirmed"] is False
    assert cache["expires_at"] == "2999-01-03"

    with pytest.raises(ValueError, match="manually confirmed"):
        calculate_quote(db_session, 1, inquiry.id, [QuoteItemInput(product_id=product.id, quantity=1000)], currency="EUR")

    confirm_exchange_rate_cache(rule)
    db_session.flush()

    result = calculate_quote(
        db_session,
        1,
        inquiry.id,
        [QuoteItemInput(product_id=product.id, quantity=1000)],
        currency="EUR",
    )

    assert result.lines[0].unit_price == Decimal("2.70")
    assert result.total_amount == Decimal("2700.00")


def test_global_exchange_rate_provider_refreshes_rule_cache(db_session, monkeypatch):
    inquiry, product = _seed_quote_data(db_session)
    rule = db_session.query(models.PricingRule).filter_by(product_id=product.id).one()
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b'{"base":"USD","rates":{"EUR":"0.76"}}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.services.exchange_rate_sources.urlopen", fake_urlopen)
    monkeypatch.setenv("CLOSER_EXCHANGE_RATE_PROVIDER", "http")
    monkeypatch.setenv("CLOSER_EXCHANGE_RATE_SOURCE", "ecb")
    monkeypatch.setenv("CLOSER_EXCHANGE_RATE_ENDPOINT", "https://rates.example/{base}?symbols={symbols}")
    monkeypatch.setenv("CLOSER_EXCHANGE_RATE_AUTH_TOKEN", "token-123")

    refresh_pricing_rule_exchange_rate_cache(
        db_session,
        1,
        rule.id,
        {"source_currency": "USD", "target_currencies": ["EUR"], "ttl_days": 2},
    )

    request, timeout = requests[0]
    cache = db_session.get(models.PricingRule, rule.id).logistics_template["exchange_rate_cache"]
    assert timeout == 5.0
    assert request.full_url == "https://rates.example/USD?symbols=EUR"
    assert request.get_header("Authorization") == "Bearer token-123"
    assert cache["source"] == "ecb"
    assert cache["confirmed"] is False
    assert cache["rates"] == {"USD": {"EUR": "0.76"}}


def test_exchange_rate_provider_config_reports_default_missing_and_http():
    default_config = get_exchange_rate_provider_config({})
    missing_endpoint = get_exchange_rate_provider_config({"CLOSER_EXCHANGE_RATE_PROVIDER": "http"})
    configured = get_exchange_rate_provider_config(
        {
            "CLOSER_EXCHANGE_RATE_PROVIDER": "remote",
            "CLOSER_EXCHANGE_RATE_SOURCE": "ecb",
            "CLOSER_EXCHANGE_RATE_ENDPOINT": "https://rates.example/{base}",
            "CLOSER_EXCHANGE_RATE_AUTH_TOKEN": "token-123",
        }
    )

    assert default_config.status == "warning"
    assert default_config.details()["provider"] == "disabled"
    assert missing_endpoint.status == "failed"
    assert "CLOSER_EXCHANGE_RATE_ENDPOINT" in missing_endpoint.message
    assert configured.status == "ok"
    assert configured.details()["provider"] == "http"
    assert configured.details()["source"] == "ecb"
    assert configured.details()["auth_token_configured"] is True


def test_calculate_quote_rejects_expired_or_unconfirmed_exchange_rate_cache(db_session):
    inquiry, product = _seed_quote_data(db_session)
    rule = db_session.query(models.PricingRule).filter_by(product_id=product.id).one()
    rule.logistics_template = {
        "exchange_rate_cache": {
            "confirmed": True,
            "expires_at": "2000-01-01",
            "rates": {"USD": {"EUR": "0.80"}},
        },
    }
    db_session.flush()

    with pytest.raises(ValueError, match="expired"):
        calculate_quote(db_session, 1, inquiry.id, [QuoteItemInput(product_id=product.id, quantity=1000)], currency="EUR")

    rule.logistics_template = {
        "exchange_rate_cache": {
            "confirmed": False,
            "expires_at": "2999-01-01",
            "rates": {"USD": {"EUR": "0.80"}},
        },
    }
    db_session.flush()

    with pytest.raises(ValueError, match="manually confirmed"):
        calculate_quote(db_session, 1, inquiry.id, [QuoteItemInput(product_id=product.id, quantity=1000)], currency="EUR")


def test_calculate_quote_requires_exchange_rate_for_currency_mismatch(db_session):
    inquiry, product = _seed_quote_data(db_session)

    with pytest.raises(ValueError, match="Missing exchange rate USD->EUR"):
        calculate_quote(
            db_session,
            1,
            inquiry.id,
            [QuoteItemInput(product_id=product.id, quantity=1000)],
            currency="EUR",
        )
