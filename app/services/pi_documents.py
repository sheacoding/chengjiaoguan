"""
/* ========================================================================== */
/* GEB L3: PI 文档产物                                                        */
/* ========================================================================== */
/**
 * [INPUT]: 依赖对象存储边界、PI 编号/文档文本与最小 PDF 生成器
 * [OUTPUT]: 对外提供 write_pi_document_file、write_pi_document_pdf，把 PI 文本/PDF 写入对象存储并返回文件元数据
 * [POS]: services 的文档产物边界，让报价审批生成可追踪的 PI 文本与 PDF 文件而非只停留在 JSON 字段
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

from app.services.object_storage import store_document_object


PI_DOCUMENT_MIME = "text/plain; charset=utf-8"
PI_PDF_MIME = "application/pdf"


def write_pi_document_file(seller_id: int, pi_number: str, content: str) -> dict[str, str | int | None]:
    filename = f"{_safe_name(pi_number)}.txt"
    return store_document_object(f"seller_{seller_id}/{filename}", content.encode("utf-8"), PI_DOCUMENT_MIME)


def write_pi_document_pdf(seller_id: int, pi_number: str, content: str) -> dict[str, str | int | None]:
    filename = f"{_safe_name(pi_number)}.pdf"
    return store_document_object(f"seller_{seller_id}/{filename}", _minimal_pdf(content), PI_PDF_MIME)


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def _minimal_pdf(content: str) -> bytes:
    lines = _pdf_lines(content)
    commands = ["q", "1 1 1 rg", "0 0 612 792 re f", "Q", "0 0 0 rg", "BT", "/F1 11 Tf", "72 750 Td", "14 TL"]
    for index, line in enumerate(lines):
        if index:
            commands.append("T*")
        commands.append(f"({_pdf_text(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _pdf_lines(content: str) -> list[str]:
    lines = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        while len(line) > 88:
            lines.append(line[:88])
            line = line[88:]
        lines.append(line)
    return lines[:48] or [""]


def _pdf_text(value: str) -> str:
    safe = value.encode("ascii", errors="replace").decode("ascii")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
