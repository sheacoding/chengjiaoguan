"""
/* ========================================================================== */
/* GEB L3: 产品导入服务                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 csv/json/zipfile/XML、SQLAlchemy Session、app.models、products.create_product 与 catalog_domain.common
 * [OUTPUT]: 对外提供 ProductImportError、ProductImportResult、ProductImportFailed、import_products、import_products_with_report
 * [POS]: services/catalog_domain 的批量导入边界，解析 CSV/XLSX 并保留行级错误报告
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import csv
from dataclasses import dataclass
import json
from io import BytesIO, StringIO
from typing import Any
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app import models
from app.services.catalog_domain.common import blank_to_none
from app.services.catalog_domain.products import create_product


XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class ProductImportError:
    row_number: int
    code: str
    message: str

    def to_dict(self) -> dict[str, int | str]:
        return {"row_number": self.row_number, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class ProductImportResult:
    products: list[models.Product]
    errors: list[ProductImportError]

    def error_items(self) -> list[dict[str, int | str]]:
        return [error.to_dict() for error in self.errors]


class ProductImportFailed(ValueError):
    def __init__(self, errors: list[ProductImportError]):
        self.errors = errors
        super().__init__(_import_error_message(errors))


def import_products(session: Session, seller_id: int, filename: str, content: bytes) -> list[models.Product]:
    return import_products_with_report(session, seller_id, filename, content).products


def import_products_with_report(session: Session, seller_id: int, filename: str, content: bytes) -> ProductImportResult:
    rows = _xlsx_rows(content) if filename.lower().endswith(".xlsx") else _csv_rows(content)
    products = []
    errors: list[ProductImportError] = []
    for row_number, row in enumerate(rows, start=2):
        normalized, row_errors = _product_row(row, row_number)
        errors.extend(row_errors)
        if normalized is not None:
            products.append(create_product(session, seller_id, normalized))
    if not products:
        raise ProductImportFailed(errors or [ProductImportError(0, "empty_file", "No product rows found")])
    return ProductImportResult(products=products, errors=errors)


def _product_row(row: dict[str, Any], row_number: int) -> tuple[dict[str, Any] | None, list[ProductImportError]]:
    errors: list[ProductImportError] = []
    name = blank_to_none(row.get("name") or row.get("产品名称") or row.get("product"))
    if not name:
        return None, [ProductImportError(row_number, "missing_name", "Product name is required")]
    specs, specs_error = _json_value(row.get("specs") or row.get("规格"), {}, field="specs", row_number=row_number)
    images, images_error = _json_value(row.get("images") or row.get("图片"), [], field="images", row_number=row_number)
    moq, moq_error = _int_value(row.get("moq") or row.get("MOQ"), field="moq", row_number=row_number)
    for error in [specs_error, images_error, moq_error]:
        if error is not None:
            errors.append(error)
    if errors:
        return None, errors
    return {
        "name": name,
        "sku": blank_to_none(row.get("sku") or row.get("货号")),
        "specs": specs,
        "cost": blank_to_none(row.get("cost") or row.get("成本")),
        "currency": blank_to_none(row.get("currency") or row.get("币种")) or "USD",
        "moq": moq,
        "images": images,
        "description": blank_to_none(row.get("description") or row.get("描述")),
        "status": blank_to_none(row.get("status") or row.get("状态")) or "active",
    }, []


def _csv_rows(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig")
    return list(csv.DictReader(StringIO(text)))


def _xlsx_rows(content: bytes) -> list[dict[str, str]]:
    with ZipFile(BytesIO(content)) as archive:
        shared = _shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        by_id = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheet = workbook.find(".//a:sheet", XLSX_NS)
        if sheet is None:
            return []
        rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = by_id[rid]
        sheet_path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
        root = ET.fromstring(archive.read(sheet_path))
    matrix = []
    for row in root.findall(".//a:row", XLSX_NS):
        values = []
        for cell in row.findall("a:c", XLSX_NS):
            value = cell.find("a:v", XLSX_NS)
            text = "" if value is None else value.text or ""
            if cell.attrib.get("t") == "s" and text.isdigit():
                text = shared[int(text)]
            values.append(text)
        if any(values):
            matrix.append(values)
    if not matrix:
        return []
    headers = [header.strip() for header in matrix[0]]
    return [dict(zip(headers, row, strict=False)) for row in matrix[1:]]


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(text.text or "" for text in item.findall(".//a:t", XLSX_NS)) for item in root.findall("a:si", XLSX_NS)]


def _json_value(value: Any, default: Any, *, field: str, row_number: int) -> tuple[Any, ProductImportError | None]:
    if value in (None, ""):
        return default, None
    if isinstance(value, (dict, list)):
        return value, None
    try:
        return json.loads(str(value)), None
    except json.JSONDecodeError:
        return default, ProductImportError(row_number, f"invalid_{field}", f"{field} must be valid JSON")


def _int_value(value: Any, *, field: str, row_number: int) -> tuple[int | None, ProductImportError | None]:
    if value in (None, ""):
        return None, None
    try:
        return int(float(str(value))), None
    except ValueError:
        return None, ProductImportError(row_number, f"invalid_{field}", f"{field} must be a number")


def _import_error_message(errors: list[ProductImportError]) -> str:
    if not errors:
        return "No valid product rows found"
    samples = "; ".join(f"row {error.row_number}: {error.message}" for error in errors[:3])
    return f"No valid product rows found: {samples}"
