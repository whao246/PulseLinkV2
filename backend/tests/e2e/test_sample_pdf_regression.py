from pathlib import Path

from app.pipeline.offline import analyze_pdf_offline


ROOT = Path(__file__).resolve().parents[3]


def test_sample_pdfs_produce_pages_tables_and_scores(tmp_path):
    pdfs = [
        ROOT / "多线程DSP智能终端芯片_202603_副本.pdf",
        ROOT / "追光科技A+轮融资商业计划书260226_副本.pdf",
    ]

    for pdf in pdfs:
        result = analyze_pdf_offline(pdf, artifact_dir=tmp_path)
        assert result.parse_summary.page_count > 0
        assert result.parse_summary.block_count > 0
        assert result.parse_summary.table_count > 0
        assert result.score_result.potential_score > 0
