from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


PIPELINE_STEP_NAMES = (
    "load_document",
    "parse_text_layout",
    "detect_tables_and_figures",
    "render_candidate_pages",
    "vision_understanding",
    "build_evidence_units",
    "score_and_judge",
    "assemble_report",
)


@dataclass
class AnalysisContext:
    task_id: str


class PipelineStep(Protocol):
    name: str

    def run(self, context: AnalysisContext) -> AnalysisContext:
        ...
