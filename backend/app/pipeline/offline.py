from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParseSummary:
    page_count: int
    block_count: int
    table_count: int
    evidence_unit_count: int


@dataclass(frozen=True)
class ScoreResult:
    potential_score: float


@dataclass(frozen=True)
class OfflineAnalysisResult:
    parse_summary: ParseSummary
    score_result: ScoreResult


def analyze_pdf_offline(pdf_path: Path, *, artifact_dir: Path) -> OfflineAnalysisResult:
    pdf_bytes = pdf_path.read_bytes()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    page_count = _estimate_page_count(pdf_bytes)
    block_count = max(1, len(pdf_bytes) // 4096)
    table_count = _estimate_table_count(pdf_bytes)
    evidence_unit_count = max(1, min(block_count, page_count * 4))
    potential_score = min(100.0, 40.0 + evidence_unit_count)

    summary_path = artifact_dir / f"{pdf_path.stem}.summary.txt"
    summary_path.write_text(
        "\n".join(
            [
                f"page_count={page_count}",
                f"block_count={block_count}",
                f"table_count={table_count}",
                f"evidence_unit_count={evidence_unit_count}",
                f"potential_score={potential_score}",
            ]
        ),
        encoding="utf-8",
    )

    return OfflineAnalysisResult(
        parse_summary=ParseSummary(
            page_count=page_count,
            block_count=block_count,
            table_count=table_count,
            evidence_unit_count=evidence_unit_count,
        ),
        score_result=ScoreResult(potential_score=potential_score),
    )


def _estimate_page_count(pdf_bytes: bytes) -> int:
    page_markers = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    if page_markers:
        return len(page_markers)
    fallback_markers = re.findall(rb"/Page\b", pdf_bytes)
    return max(1, len(fallback_markers))


def _estimate_table_count(pdf_bytes: bytes) -> int:
    table_hints = len(re.findall(rb"(?i)table|excel|sheet|\brows?\b|\bcolumns?\b", pdf_bytes))
    drawing_hints = pdf_bytes.count(b" re") + pdf_bytes.count(b" l") + pdf_bytes.count(b" m")
    if table_hints or drawing_hints > 100:
        return max(1, table_hints)
    return 1
