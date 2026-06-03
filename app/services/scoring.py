"""
/* ========================================================================== */
/* GEB L3: 询盘打分服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models 与 Decimal 规则权重
 * [OUTPUT]: 对外提供 InquiryScore、score_inquiry_record、score_inquiry
 * [POS]: services 的询盘分级核心，以可解释 signals 输出 A/B/C
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models


PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "hotmail.com",
    "outlook.com",
    "yahoo.com",
    "qq.com",
    "163.com",
}
SPAM_KEYWORDS = {"seo", "casino", "loan", "crypto", "free traffic"}
COMPETITOR_KEYWORDS = {"price list only", "competitor", "benchmark price", "market research"}


@dataclass(frozen=True)
class InquiryScore:
    grade: str
    score: Decimal
    signals: list[str]


def score_inquiry_record(inquiry: models.Inquiry, customer: models.Customer | None = None) -> InquiryScore:
    raw = (inquiry.raw_content or "").lower()
    parsed = inquiry.parsed or {}
    score = Decimal("35")
    signals: list[str] = []

    if customer and customer.company:
        score += Decimal("18")
        signals.append("real_company")
    if customer and customer.email and _is_corporate_domain(customer.email):
        score += Decimal("12")
        signals.append("verified_domain")
    if parsed.get("quantity"):
        score += Decimal("18")
        signals.append("specific_quantity")
    if parsed.get("product"):
        score += Decimal("15")
        signals.append("specific_product")
    if parsed.get("destination") or (customer and customer.country):
        score += Decimal("8")
        signals.append("destination_known")
    if any(keyword in raw for keyword in SPAM_KEYWORDS):
        score -= Decimal("35")
        signals.append("spam_keyword")
    if any(keyword in raw for keyword in COMPETITOR_KEYWORDS):
        score -= Decimal("35")
        signals.append("possible_competitor")
    if len(raw.strip()) < 24:
        score -= Decimal("15")
        signals.append("too_short")

    score = max(Decimal("0"), min(Decimal("100"), score))
    if score >= Decimal("75"):
        grade = "A"
    elif score >= Decimal("45"):
        grade = "B"
    else:
        grade = "C"
    return InquiryScore(grade=grade, score=score, signals=signals)


def score_inquiry(session: Session, seller_id: int, inquiry_id: int) -> InquiryScore:
    inquiry = session.get(models.Inquiry, inquiry_id)
    if inquiry is None or inquiry.seller_id != seller_id:
        raise LookupError("Inquiry not found")
    customer = session.get(models.Customer, inquiry.customer_id)
    result = score_inquiry_record(inquiry, customer)
    inquiry.grade = result.grade
    inquiry.score = result.score
    if customer:
        customer.grade = result.grade
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="system",
            action_type="inquiry_scored",
            target_type="inquiry",
            target_id=inquiry.id,
            is_auto=True,
            snapshot={"grade": result.grade, "score": str(result.score), "signals": result.signals},
        )
    )
    return result


def _is_corporate_domain(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower()
    return domain not in PUBLIC_EMAIL_DOMAINS and "." in domain
