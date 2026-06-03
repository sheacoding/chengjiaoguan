"""
/* ========================================================================== */
/* GEB L3: Demo 场景种子服务                                                  */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、channel_gateway、agent_tools、knowledge 与 models
 * [OUTPUT]: 对外提供 seed_demo_scenario，创建或复用演示产品、价格规则、知识、询盘、报价、审批和跟进
 * [POS]: services 的演示数据编排边界，用确定性数据证明 MVP 主链路，不拥有业务规则本身
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import agent_tools, models
from app.schemas import ChannelContact, InboundMessage
from app.services.channel_gateway import ingest_inbound_message
from app.services.knowledge import ingest_knowledge


DEMO_PRODUCT_SKU = "DEMO-LAMP-10W"
DEMO_KNOWLEDGE_REF = "demo-lamp-faq"
DEMO_CHANNEL_MESSAGE_ID = "demo-site-form-001"
DEMO_INQUIRY_CONTENT = "Hi, we need 5000 LED desk lamps shipped to US. Please quote CIF and payment terms."
DEMO_RISKY_REPLY = "We can offer USD 2.80 per unit and guarantee delivery with net 30 payment terms."


def seed_demo_scenario(session: Session, seller_id: int) -> dict[str, Any]:
    seller = _ensure_demo_seller(session, seller_id)
    seller.settings = dict(seller.settings or {}) | {"large_order_approval_threshold": "10000"}
    product = _ensure_demo_product(session, seller_id)
    pricing_rule = _ensure_demo_pricing_rule(session, seller_id, product.id)
    knowledge_chunks = _ensure_demo_knowledge(session, seller_id)
    inquiry, conversation, message, duplicate = _ingest_demo_inquiry(session, seller_id)
    score = agent_tools.score_inquiry(session, seller_id, inquiry.id)
    product_matches = agent_tools.match_product(session, seller_id, inquiry.parsed or DEMO_INQUIRY_CONTENT)
    knowledge = agent_tools.search_knowledge(session, seller_id, "LED desk lamp payment warranty", limit=3)
    quote = _ensure_demo_quote(session, seller_id, inquiry.id, product.id)
    approval = _ensure_demo_approval(session, seller_id, conversation.id)
    followup = _ensure_demo_followup(session, seller_id, inquiry.id, conversation.id)
    return {
        "seller_id": seller_id,
        "scenario": "site_form_quote_guardrail",
        "product_id": product.id,
        "pricing_rule_id": pricing_rule.id,
        "knowledge_chunk_ids": [chunk.id for chunk in knowledge_chunks],
        "customer_id": inquiry.customer_id,
        "inquiry_id": inquiry.id,
        "conversation_id": conversation.id,
        "message_id": message.id,
        "duplicate_inbound": duplicate,
        "score": score,
        "product_matches": product_matches,
        "knowledge": knowledge,
        "quotation": quote,
        "approval": approval,
        "followup": followup,
        "next_steps": [
            "Open /api/v1/conversations/{conversation_id}",
            "Review /api/v1/approvals",
            "Approve or edit the pending message_send approval",
        ],
    }


def _ensure_demo_seller(session: Session, seller_id: int) -> models.Seller:
    seller = session.get(models.Seller, seller_id)
    if seller is None:
        seller = models.Seller(
            id=seller_id,
            name=f"Demo Exporter {seller_id}",
            email=f"owner-{seller_id}@example.com",
        )
        session.add(seller)
        session.flush()
    return seller


def _ensure_demo_product(session: Session, seller_id: int) -> models.Product:
    product = session.scalar(
        select(models.Product)
        .where(models.Product.seller_id == seller_id)
        .where(models.Product.sku == DEMO_PRODUCT_SKU)
    )
    if product is None:
        product = models.Product(seller_id=seller_id, name="LED Desk Lamp 10W", sku=DEMO_PRODUCT_SKU)
        session.add(product)
    product.status = "active"
    product.cost = Decimal("2.10")
    product.currency = "USD"
    product.moq = 500
    product.specs = {"power": "10W", "certification": "CE", "material": "aluminum"}
    product.description = "Adjustable LED desk lamp for B2B bulk orders."
    session.flush()
    return product


def _ensure_demo_pricing_rule(session: Session, seller_id: int, product_id: int) -> models.PricingRule:
    rule = session.scalar(
        select(models.PricingRule)
        .where(models.PricingRule.seller_id == seller_id)
        .where(models.PricingRule.product_id == product_id)
        .where(models.PricingRule.deleted_at.is_(None))
    )
    if rule is None:
        rule = models.PricingRule(seller_id=seller_id, product_id=product_id)
        session.add(rule)
    rule.margin_rate = Decimal("0.30")
    rule.logistics_template = {
        "unit_cost": "0.20",
        "destination_unit_costs": {"US": "0.25"},
        "exchange_rates": {"USD": {"EUR": "0.90"}},
    }
    rule.tiered_prices = [{"min_qty": 1000, "price": "3.30"}, {"min_qty": 5000, "price": "3.05"}]
    rule.valid_days = 14
    rule.floor_price = Decimal("3.00")
    rule.currency = "USD"
    rule.exchange_source = "demo_static"
    session.flush()
    return rule


def _ensure_demo_knowledge(session: Session, seller_id: int) -> list[models.KnowledgeChunk]:
    chunks = session.scalars(
        select(models.KnowledgeChunk)
        .where(models.KnowledgeChunk.seller_id == seller_id)
        .where(models.KnowledgeChunk.source_type == "faq")
        .where(models.KnowledgeChunk.source_ref == DEMO_KNOWLEDGE_REF)
        .order_by(models.KnowledgeChunk.id.asc())
    ).all()
    if chunks:
        return chunks
    return ingest_knowledge(
        session,
        seller_id,
        source_type="faq",
        source_ref=DEMO_KNOWLEDGE_REF,
        content=(
            "LED desk lamp supports CE certification and neutral packaging.\n"
            "Standard payment term is 30% deposit and 70% before shipment.\n"
            "Warranty is 12 months after delivery, subject to normal use."
        ),
    )


def _ingest_demo_inquiry(session: Session, seller_id: int):
    inbound = InboundMessage(
        channel="site_form",
        channel_message_id=f"{DEMO_CHANNEL_MESSAGE_ID}-seller-{seller_id}",
        from_=ChannelContact(
            name="Jane Buyer",
            company="ACME Trading",
            country="US",
            email="jane.demo@example.com",
        ),
        content=DEMO_INQUIRY_CONTENT,
        language="en",
        attachments=[],
    )
    return ingest_inbound_message(session, seller_id, inbound)


def _ensure_demo_quote(session: Session, seller_id: int, inquiry_id: int, product_id: int) -> dict[str, Any]:
    quotation = session.scalar(
        select(models.Quotation)
        .where(models.Quotation.seller_id == seller_id)
        .where(models.Quotation.inquiry_id == inquiry_id)
        .where(models.Quotation.created_by == "ai")
        .order_by(models.Quotation.id.asc())
    )
    if quotation is not None:
        return _quote_snapshot(quotation)
    return agent_tools.calc_quote(
        session,
        seller_id,
        inquiry_id,
        [{"product_id": product_id, "quantity": 5000}],
        destination="US",
    )


def _ensure_demo_approval(session: Session, seller_id: int, conversation_id: int) -> dict[str, Any]:
    approval = session.scalar(
        select(models.Approval)
        .where(models.Approval.seller_id == seller_id)
        .where(models.Approval.conversation_id == conversation_id)
        .where(models.Approval.type == "message_send")
        .where(models.Approval.status == "pending")
        .order_by(models.Approval.id.asc())
    )
    if approval is not None:
        return _approval_snapshot(approval)
    result = agent_tools.send_message(session, seller_id, conversation_id, DEMO_RISKY_REPLY, language="en")
    return {
        "status": result["status"],
        "approval_id": result.get("approval_id"),
        "reason": result.get("reason"),
        "reasons": result.get("reasons", []),
    }


def _ensure_demo_followup(session: Session, seller_id: int, inquiry_id: int, conversation_id: int) -> dict[str, Any]:
    followup = session.scalar(
        select(models.FollowupTask)
        .where(models.FollowupTask.seller_id == seller_id)
        .where(models.FollowupTask.inquiry_id == inquiry_id)
        .order_by(models.FollowupTask.id.asc())
    )
    if followup is not None:
        return {"followup_id": followup.id, "status": followup.status, "next_run_at": followup.next_run_at}
    return agent_tools.create_followup(session, seller_id, inquiry_id, conversation_id=conversation_id, delay_hours=24)


def _quote_snapshot(quotation: models.Quotation) -> dict[str, Any]:
    return {
        "quotation_id": quotation.id,
        "currency": quotation.currency,
        "total_amount": float(quotation.total_amount or 0),
        "valid_until": quotation.valid_until.isoformat() if quotation.valid_until else None,
        "hits_floor": quotation.hits_floor,
        "message": (quotation.terms or {}).get("message"),
    }


def _approval_snapshot(approval: models.Approval) -> dict[str, Any]:
    return {
        "status": "pending_approval",
        "approval_id": approval.id,
        "reason": approval.reason,
        "reasons": (approval.summary or "").replace("AI outbound message paused: ", "").split(", "),
    }
