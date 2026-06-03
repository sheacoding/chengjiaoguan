"""
/* ========================================================================== */
/* GEB L3: 数据导出服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 csv/io/json、SQLAlchemy Session/select 与 app.models 的 Customer/Inquiry/Quotation
 * [OUTPUT]: 对外提供 export_dataset_csv，导出 customers、inquiries、quotations 的租户隔离 CSV
 * [POS]: services 的数据导出边界，为 M10 数据看板导出需求提供确定性机器相
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


ExportDataset = Literal["customers", "inquiries", "quotations"]
Exporter = Callable[[Session, int, int], tuple[list[str], list[list[Any]]]]


def export_dataset_csv(session: Session, seller_id: int, dataset: ExportDataset, *, limit: int = 1000) -> str:
    exporter = _EXPORTERS.get(dataset)
    if exporter is None:
        raise ValueError("Unsupported export dataset")
    headers, rows = exporter(session, seller_id, _limit(limit))
    return _csv_text(headers, rows)


def supported_export_datasets() -> list[str]:
    return sorted(_EXPORTERS)


def _export_customers(session: Session, seller_id: int, limit: int) -> tuple[list[str], list[list[Any]]]:
    customers = session.scalars(
        select(models.Customer)
        .where(models.Customer.seller_id == seller_id)
        .where(models.Customer.deleted_at.is_(None))
        .order_by(models.Customer.id.asc())
        .limit(limit)
    ).all()
    return _CUSTOMER_HEADERS, [
        [
            customer.id,
            customer.company,
            customer.name,
            customer.country,
            customer.email,
            customer.phone,
            customer.grade,
            customer.status,
            _json_cell(customer.channels),
            _json_cell(customer.preferences),
            customer.created_at,
        ]
        for customer in customers
    ]


def _export_inquiries(session: Session, seller_id: int, limit: int) -> tuple[list[str], list[list[Any]]]:
    inquiries = session.scalars(
        select(models.Inquiry)
        .where(models.Inquiry.seller_id == seller_id)
        .where(models.Inquiry.deleted_at.is_(None))
        .order_by(models.Inquiry.id.asc())
        .limit(limit)
    ).all()
    return _INQUIRY_HEADERS, [
        [
            inquiry.id,
            inquiry.customer_id,
            inquiry.source_channel,
            inquiry.grade,
            _number_cell(inquiry.score),
            inquiry.status,
            inquiry.language,
            inquiry.received_at,
            _json_cell(inquiry.parsed),
            inquiry.raw_content,
        ]
        for inquiry in inquiries
    ]


def _export_quotations(session: Session, seller_id: int, limit: int) -> tuple[list[str], list[list[Any]]]:
    quotations = session.scalars(
        select(models.Quotation)
        .where(models.Quotation.seller_id == seller_id)
        .where(models.Quotation.deleted_at.is_(None))
        .order_by(models.Quotation.id.asc())
        .limit(limit)
    ).all()
    return _QUOTATION_HEADERS, [
        [
            quotation.id,
            quotation.inquiry_id,
            quotation.customer_id,
            quotation.currency,
            _number_cell(quotation.total_amount),
            quotation.valid_until,
            quotation.is_pi,
            quotation.status,
            quotation.created_by,
            quotation.hits_floor,
            _json_cell(quotation.terms),
        ]
        for quotation in quotations
    ]


def _csv_text(headers: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows([[_cell(value) for value in row] for row in rows])
    return buffer.getvalue()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _json_cell(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str)


def _number_cell(value: Any) -> str:
    return "" if value is None else str(value)


def _limit(value: int) -> int:
    return min(max(value, 1), 5000)


_CUSTOMER_HEADERS = [
    "id",
    "company",
    "name",
    "country",
    "email",
    "phone",
    "grade",
    "status",
    "channels",
    "preferences",
    "created_at",
]
_INQUIRY_HEADERS = [
    "id",
    "customer_id",
    "source_channel",
    "grade",
    "score",
    "status",
    "language",
    "received_at",
    "parsed",
    "raw_content",
]
_QUOTATION_HEADERS = [
    "id",
    "inquiry_id",
    "customer_id",
    "currency",
    "total_amount",
    "valid_until",
    "is_pi",
    "status",
    "created_by",
    "hits_floor",
    "terms",
]
_EXPORTERS: dict[str, Exporter] = {
    "customers": _export_customers,
    "inquiries": _export_inquiries,
    "quotations": _export_quotations,
}
