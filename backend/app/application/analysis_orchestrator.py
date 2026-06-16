from __future__ import annotations

from dataclasses import dataclass

from app.domain.analysis.pipeline import AnalysisContext, PipelineStep


@dataclass
class AnalysisResult:
    task_id: str
    skipped: bool


class AnalysisOrchestrator:
    def __init__(self, *, task_repository, steps: list[PipelineStep]):
        self.task_repository = task_repository
        self.steps = steps

    def run(self, *, task_id: str) -> AnalysisResult:
        task = self.task_repository.get(task_id)
        if task.status == "completed":
            return AnalysisResult(task_id=task_id, skipped=True)

        context = AnalysisContext(task_id=task_id)
        for step in self.steps:
            context = step.run(context)

        return AnalysisResult(task_id=task_id, skipped=False)
