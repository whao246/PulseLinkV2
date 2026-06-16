import pytest

from app.application.analysis_orchestrator import AnalysisOrchestrator


class FakeTask:
    def __init__(self, status):
        self.status = status


class FakeTaskRepository:
    status = "queued"

    def get(self, task_id):
        return FakeTask(self.status)


@pytest.fixture
def fake_task_repository():
    return FakeTaskRepository()


def test_orchestrator_skips_completed_task(fake_task_repository):
    fake_task_repository.status = "completed"
    orchestrator = AnalysisOrchestrator(task_repository=fake_task_repository, steps=[])

    result = orchestrator.run(task_id="task_1")

    assert result.skipped is True


def test_orchestrator_runs_steps_in_order(fake_task_repository):
    calls = []

    class Step:
        name = "load_document"

        def run(self, context):
            calls.append(self.name)
            return context

    fake_task_repository.status = "queued"
    orchestrator = AnalysisOrchestrator(
        task_repository=fake_task_repository,
        steps=[Step()],
    )

    result = orchestrator.run(task_id="task_1")

    assert result.skipped is False
    assert calls == ["load_document"]
