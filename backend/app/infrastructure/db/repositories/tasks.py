from __future__ import annotations

from uuid import uuid4

from app.domain.analysis.pipeline import PIPELINE_STEP_NAMES
from app.infrastructure.db.models import AnalysisTask, TaskStep

QUEUE_PUBLISH_PENDING = "pending"
QUEUE_PUBLISH_PUBLISHING = "publishing"
QUEUE_PUBLISH_PUBLISHED = "published"


class TaskRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_idempotency_key(self, user_id: str, idempotency_key: str):
        return (
            self.db_session.query(AnalysisTask)
            .filter(
                AnalysisTask.user_id == user_id,
                AnalysisTask.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )

    def create_task(
        self,
        *,
        user_id: str,
        file_id: str,
        idempotency_key: str,
        status: str,
        model_profile: str | None,
    ):
        task = AnalysisTask(
            id=uuid4().hex,
            user_id=user_id,
            file_id=file_id,
            idempotency_key=idempotency_key,
            task_type="bp_analysis",
            model_profile=model_profile,
            status=status,
            options={},
            payload={"queue_publish_status": QUEUE_PUBLISH_PENDING},
        )
        self.db_session.add(task)
        return task

    def create_step(self, *, task_id: str, step_name: str, status: str):
        step = TaskStep(
            id=uuid4().hex,
            task_id=task_id,
            step_name=step_name,
            status=status,
            attempt_count=0,
            max_attempts=3,
        )
        self.db_session.add(step)
        return step

    def claim_queue_publish(self, task_id: str) -> bool:
        task = (
            self.db_session.query(AnalysisTask)
            .filter(AnalysisTask.id == task_id)
            .with_for_update()
            .one_or_none()
        )
        if task is None:
            return False

        payload = task.payload or {}
        status = payload.get("queue_publish_status")
        if status in {QUEUE_PUBLISH_PUBLISHING, QUEUE_PUBLISH_PUBLISHED}:
            return False
        if payload.get("queue_published") is True:
            return False

        task.payload = {
            **payload,
            "queue_publish_status": QUEUE_PUBLISH_PUBLISHING,
        }
        self.db_session.add(task)
        self.db_session.commit()
        return True

    def mark_queue_published(self, task_id: str) -> None:
        task = (
            self.db_session.query(AnalysisTask)
            .filter(AnalysisTask.id == task_id)
            .one_or_none()
        )
        if task is None:
            return

        payload = task.payload or {}
        task.payload = {
            **payload,
            "queue_publish_status": QUEUE_PUBLISH_PUBLISHED,
        }
        self.db_session.add(task)
        self.db_session.commit()

    def mark_queue_publish_pending(self, task_id: str) -> None:
        task = (
            self.db_session.query(AnalysisTask)
            .filter(AnalysisTask.id == task_id)
            .one_or_none()
        )
        if task is None:
            return

        payload = task.payload or {}
        task.payload = {
            **payload,
            "queue_publish_status": QUEUE_PUBLISH_PENDING,
        }
        self.db_session.add(task)
        self.db_session.commit()

    def list_steps(self, task_id: str):
        steps = (
            self.db_session.query(TaskStep)
            .filter(TaskStep.task_id == task_id)
            .all()
        )
        order = {step_name: index for index, step_name in enumerate(PIPELINE_STEP_NAMES)}
        return sorted(
            steps,
            key=lambda step: (
                order.get(step.step_name, len(order)),
                step.step_name,
                step.id,
            ),
        )
