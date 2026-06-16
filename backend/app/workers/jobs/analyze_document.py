from __future__ import annotations


def build_orchestrator():
    raise RuntimeError("orchestrator wiring is configured in the worker composition root")


def run(*, task_id: str) -> None:
    orchestrator = build_orchestrator()
    orchestrator.run(task_id=task_id)
