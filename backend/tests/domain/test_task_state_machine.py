import pytest

from app.domain.tasks.state_machine import (
    StepStatus,
    TaskStatus,
    can_retry_step,
    can_start_step,
    transition_task,
)


def test_task_can_move_from_queued_to_running():
    assert transition_task(TaskStatus.QUEUED, TaskStatus.RUNNING) == TaskStatus.RUNNING


def test_task_cannot_move_from_completed_to_running():
    with pytest.raises(ValueError, match="invalid task transition"):
        transition_task(TaskStatus.COMPLETED, TaskStatus.RUNNING)


def test_step_can_start_when_pending():
    assert can_start_step(StepStatus.PENDING, locked_until_expired=True)


def test_step_cannot_start_when_running_lock_not_expired():
    assert not can_start_step(StepStatus.RUNNING, locked_until_expired=False)


def test_failed_step_can_retry_when_attempts_remain():
    assert can_retry_step(StepStatus.FAILED, attempt_count=1, max_attempts=3)
