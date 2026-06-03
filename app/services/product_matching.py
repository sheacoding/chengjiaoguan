"""
/* ========================================================================== */
/* GEB L3: 产品匹配服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 json/re、SQLAlchemy Session 与 app.models.Product
 * [OUTPUT]: 对外提供 match_product
 * [POS]: services 的产品证据检索器，用字段 token 重叠为 Agent 回复提供可解释 grounding
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)


def match_product(
    session: Session,
    seller_id: int,
    requirement: str | dict[str, Any],
    *,
    limit: int = 5,
) -> list[dict]:
    query_text = _requirement_text(requirement)
    query_tokens = set(_tokens(query_text))
    if not query_tokens:
        raise ValueError("requirement is required")
    limit = min(max(limit, 1), 20)

    products = session.scalars(
        select(models.Product)
        .where(models.Product.seller_id == seller_id)
        .where(models.Product.status == "active")
        .where(models.Product.deleted_at.is_(None))
    ).all()

    matches = []
    for product in products:
        score, fields = _score_product(product, query_tokens, query_text)
        if score > 0:
            matches.append((score, product, fields))
    matches.sort(key=lambda item: (item[0], item[1].id), reverse=True)

    return [
        {
            "product_id": product.id,
            "name": product.name,
            "sku": product.sku,
            "score": round(score, 6),
            "matched_fields": fields,
            "reason": _reason(fields),
        }
        for score, product, fields in matches[:limit]
    ]


def _requirement_text(requirement: str | dict[str, Any]) -> str:
    if isinstance(requirement, str):
        return requirement
    values: list[str] = []
    for value in requirement.values():
        if isinstance(value, (dict, list)):
            values.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        elif value is not None:
            values.append(str(value))
    return " ".join(values)


def _score_product(product: models.Product, query_tokens: set[str], query_text: str) -> tuple[float, list[str]]:
    fields = {
        "name": product.name,
        "sku": product.sku or "",
        "description": product.description or "",
        "specs": json.dumps(product.specs or {}, ensure_ascii=False, sort_keys=True),
    }
    weighted_score = 0.0
    matched_fields: list[str] = []
    weights = {"name": 2.0, "sku": 2.0, "description": 1.0, "specs": 1.5}

    for field_name, field_text in fields.items():
        field_tokens = set(_tokens(field_text))
        if not field_tokens:
            continue
        overlap = query_tokens & field_tokens
        if overlap:
            matched_fields.append(field_name)
            weighted_score += weights[field_name] * (len(overlap) / len(query_tokens))

    if product.sku and product.sku.lower() in query_text.lower():
        weighted_score += 1.0
        if "sku" not in matched_fields:
            matched_fields.append("sku")

    return weighted_score, matched_fields


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def _reason(fields: list[str]) -> str:
    if not fields:
        return "No direct product evidence matched."
    return "Matched " + ", ".join(fields) + "."
