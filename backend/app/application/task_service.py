from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.domain.analysis.pipeline import PIPELINE_STEP_NAMES
from app.domain.tasks.state_machine import StepStatus, TaskStatus
from app.infrastructure.db.repositories.tasks import TaskRepository


class TaskService:
    def __init__(self, *, db_session, queue_publisher):
        self.db_session = db_session
        self.queue_publisher = queue_publisher
        self.tasks = TaskRepository(db_session)

    def create_task(
        self,
        *,
        user_id: str,
        file_id: str,
        idempotency_key: str,
        options: dict | None,
    ):
        existing = self.tasks.get_by_idempotency_key(user_id, idempotency_key)
        if existing is not None:
            self._publish_if_needed(existing)
            return existing

        options = options or {}
        task = self.tasks.create_task(
            user_id=user_id,
            file_id=file_id,
            idempotency_key=idempotency_key,
            status=TaskStatus.QUEUED.value,
            model_profile=options.get("model_profile"),
        )
        for step_name in PIPELINE_STEP_NAMES:
            self.tasks.create_step(
                task_id=task.id,
                step_name=step_name,
                status=StepStatus.PENDING.value,
            )

        try:
            self.db_session.commit()
        except IntegrityError:
            self.db_session.rollback()
            existing = self.tasks.get_by_idempotency_key(user_id, idempotency_key)
            if existing is not None:
                return existing
            raise

        self._publish_if_needed(task)
        return task

    def _publish_if_needed(self, task):
        if self.queue_publisher is None:
            return

        task_id = task.id
        if not self.tasks.claim_queue_publish(task_id):
            return

        try:
            self.queue_publisher.publish_analyze_document(task_id=task_id)
        except Exception:
            self.tasks.mark_queue_publish_pending(task_id)
            raise

        # This claim prevents duplicate enqueue from concurrent API retries. The
        # worker should still handle task_id idempotently for end-to-end safety.
        self.tasks.mark_queue_published(task_id)

    def list_steps(self, task_id: str):
        return self.tasks.list_steps(task_id)
