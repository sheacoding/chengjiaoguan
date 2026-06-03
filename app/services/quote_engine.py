"""
/* ========================================================================== */
/* GEB L3: 报价计算核心                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models、Decimal、日期有效期规则与 exchange_rates.resolve_exchange_rate
 * [OUTPUT]: 对外提供 QuoteItemInput、QuoteLine、QuoteResult、calculate_quote
 * [POS]: services 的报价算法真源，统一 MOQ、阶梯价、利润、物流、汇率换算、地板价判断
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.exchange_rates import resolve_exchange_rate


Money = Decimal


@dataclass(frozen=True)
class QuoteItemInput:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class QuoteLine:
    product_id: int
    quantity: int
    unit_price: Money
    amount: Money
    floor_price: Money
    hits_floor: bool


@dataclass(frozen=True)
class QuoteResult:
    inquiry_id: int
    currency: str
    total_amount: Money
    valid_until: date
    hits_floor: bool
    lines: list[QuoteLine]


def calculate_quote(
    session: Session,
    seller_id: int,
    inquiry_id: int,
    items: list[QuoteItemInput],
    *,
    destination: str | None = None,
    currency: str = "USD",
) -> QuoteResult:
    inquiry = session.get(models.Inquiry, inquiry_id)
    if inquiry is None or inquiry.seller_id != seller_id:
        raise LookupError("Inquiry not found")
    if not items:
        raise ValueError("At least one quote item is required")

    lines: list[QuoteLine] = []
    total = Decimal("0")
    valid_days = 14

    for item in items:
        product = _require_product(session, seller_id, item.product_id)
        if product.moq and item.quantity < product.moq:
            raise ValueError(f"Quantity {item.quantity} is below MOQ {product.moq} for product {product.id}")
        rule = _require_pricing_rule(session, seller_id, product.id)
        valid_days = rule.valid_days or valid_days
        base_currency = _currency(rule.currency or product.currency or currency)
        unit_price = _convert_money(
            _unit_price(product, rule, item.quantity, destination),
            base_currency,
            currency,
            rule,
        )
        floor_price = _convert_money(_money(rule.floor_price), base_currency, currency, rule)
        hits_floor = unit_price < floor_price
        amount = _money(unit_price * Decimal(item.quantity))
        total += amount
        lines.append(
            QuoteLine(
                product_id=product.id,
                quantity=item.quantity,
                unit_price=unit_price,
                amount=amount,
                floor_price=floor_price,
                hits_floor=hits_floor,
            )
        )

    return QuoteResult(
        inquiry_id=inquiry.id,
        currency=currency,
        total_amount=_money(total),
        valid_until=date.today() + timedelta(days=valid_days),
        hits_floor=any(line.hits_floor for line in lines),
        lines=lines,
    )


def _require_product(session: Session, seller_id: int, product_id: int) -> models.Product:
    product = session.get(models.Product, product_id)
    if product is None or product.seller_id != seller_id:
        raise LookupError("Product not found")
    return product


def _require_pricing_rule(session: Session, seller_id: int, product_id: int) -> models.PricingRule:
    product_rule = session.scalar(
        select(models.PricingRule).where(
            models.PricingRule.seller_id == seller_id,
            models.PricingRule.product_id == product_id,
        )
    )
    if product_rule:
        return product_rule
    global_rule = session.scalar(
        select(models.PricingRule).where(
            models.PricingRule.seller_id == seller_id,
            models.PricingRule.product_id.is_(None),
        )
    )
    if global_rule:
        return global_rule
    raise LookupError("Pricing rule not found")


def _unit_price(product: models.Product, rule: models.PricingRule, quantity: int, destination: str | None) -> Money:
    tier_price = _tier_price(rule.tiered_prices or [], quantity)
    if tier_price is not None:
        base_price = tier_price
    else:
        cost = _convert_money(
            _money(product.cost or Decimal("0")),
            _currency(product.currency or rule.currency),
            _currency(rule.currency or product.currency),
            rule,
        )
        margin = _money(rule.margin_rate or Decimal("0"))
        base_price = cost * (Decimal("1") + margin)

    logistics = rule.logistics_template or {}
    unit_logistics = _money(logistics.get("unit_cost", 0))
    destination_overrides = logistics.get("destination_unit_costs") or {}
    if destination and destination in destination_overrides:
        unit_logistics = _money(destination_overrides[destination])
    return _money(base_price + unit_logistics)


def _tier_price(tiers: list[dict], quantity: int) -> Money | None:
    eligible = [
        tier
        for tier in tiers
        if tier.get("min_qty") is not None and quantity >= int(tier["min_qty"])
    ]
    if not eligible:
        return None
    tier = max(eligible, key=lambda item: int(item["min_qty"]))
    return _money(tier["price"])


def _convert_money(value: Money, source_currency: str, target_currency: str, rule: models.PricingRule) -> Money:
    source_currency = _currency(source_currency)
    target_currency = _currency(target_currency)
    if source_currency == target_currency:
        return _money(value)
    return _money(value * _exchange_rate(source_currency, target_currency, rule))


def _exchange_rate(source_currency: str, target_currency: str, rule: models.PricingRule) -> Decimal:
    return resolve_exchange_rate(source_currency, target_currency, rule)


def _currency(value: str | None) -> str:
    return (value or "USD").upper()


def _money(value) -> Money:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
