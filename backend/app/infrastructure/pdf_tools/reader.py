from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PageTextExtraction:
    page_number: int
    text: str | None
    status: str
    metadata: dict[str, Any]


def extract_page_texts(pdf_path: Path, *, page_count: int) -> list[PageTextExtraction]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return _unavailable_pages(page_count, reason="pypdf_not_installed")

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        return _unavailable_pages(page_count, reason=exc.__class__.__name__)

    pages: list[PageTextExtraction] = []
    for index in range(page_count):
        text: str | None = None
        status = "parser_unavailable"
        metadata: dict[str, Any] = {"source": "pypdf"}
        try:
            if index < len(reader.pages):
                extracted = reader.pages[index].extract_text()
                text = extracted.strip() if extracted else None
                status = "extracted" if text else "parser_unavailable"
        except Exception as exc:
            metadata["error"] = exc.__class__.__name__
        pages.append(
            PageTextExtraction(
                page_number=index + 1,
                text=text,
                status=status,
                metadata=metadata,
            )
        )
    return pages


def _unavailable_pages(page_count: int, *, reason: str) -> list[PageTextExtraction]:
    return [
        PageTextExtraction(
            page_number=page_number,
            text=None,
            status="parser_unavailable",
            metadata={"reason": reason},
        )
        for page_number in range(1, page_count + 1)
    ]
