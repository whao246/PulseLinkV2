from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


ALLOWED_TASK_TRANSITIONS = {
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def transition_task(current: TaskStatus, target: TaskStatus) -> TaskStatus:
    if target not in ALLOWED_TASK_TRANSITIONS[current]:
        raise ValueError(f"invalid task transition: {current} -> {target}")
    return target


def can_start_step(status: StepStatus, *, locked_until_expired: bool) -> bool:
    if status in {StepStatus.PENDING, StepStatus.RETRYING}:
        return True
    if status == StepStatus.RUNNING:
        return locked_until_expired
    return False


def can_retry_step(
    status: StepStatus, *, attempt_count: int, max_attempts: int
) -> bool:
    return status == StepStatus.FAILED and attempt_count < max_attempts
