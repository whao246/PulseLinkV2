from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.pipeline.offline import analyze_pdf_offline

PDFS = [
    ROOT / "多线程DSP智能终端芯片_202603_副本.pdf",
    ROOT / "追光科技A+轮融资商业计划书260226_副本.pdf",
]


def main() -> int:
    artifact_dir = ROOT / ".artifacts" / "pdf-verification"
    for pdf in PDFS:
        result = analyze_pdf_offline(pdf, artifact_dir=artifact_dir)
        summary = result.parse_summary
        if summary.page_count <= 0:
            raise RuntimeError(f"{pdf.name}: page count is zero")
        if summary.table_count <= 0:
            raise RuntimeError(f"{pdf.name}: table count is zero")
        if summary.evidence_unit_count <= 0:
            raise RuntimeError(f"{pdf.name}: evidence units missing")
        if result.score_result.potential_score <= 0:
            raise RuntimeError(f"{pdf.name}: potential score missing")
        print(
            f"{pdf.name}: pages={summary.page_count} "
            f"blocks={summary.block_count} tables={summary.table_count} "
            f"evidence={summary.evidence_unit_count} "
            f"potential={result.score_result.potential_score}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
