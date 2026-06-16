import importlib

from app.infrastructure.queue.publisher import ANALYZE_DOCUMENT_JOB_PATH
from app.workers.jobs.analyze_document import run


def test_analyze_document_job_invokes_orchestrator(monkeypatch):
    captured = {}

    class FakeOrchestrator:
        def run(self, *, task_id):
            captured["task_id"] = task_id

    monkeypatch.setattr(
        "app.workers.jobs.analyze_document.build_orchestrator",
        lambda: FakeOrchestrator(),
    )

    run(task_id="task_1")

    assert captured["task_id"] == "task_1"


def test_analyze_document_queue_path_is_importable():
    module_name, function_name = ANALYZE_DOCUMENT_JOB_PATH.rsplit(".", 1)

    target = getattr(importlib.import_module(module_name), function_name)

    assert target is run
