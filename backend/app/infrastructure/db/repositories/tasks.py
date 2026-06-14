from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.analysis.pipeline import PIPELINE_STEP_NAMES
from app.infrastructure.db.models import AnalysisTask, TaskStep

QUEUE_PUBLISH_PENDING = "pending"
QUEUE_PUBLISH_PUBLISHING = "publishing"
QUEUE_PUBLISH_PUBLISHED = "published"


class TaskRepository:
    def __init__(
        self,
        db_session,
        *,
        now_provider=None,
        claim_lease_seconds: int = 60,
    ):
        self.db_session = db_session
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.claim_lease_seconds = claim_lease_seconds

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

    def claim_queue_publish(self, task_id: str) -> str | None:
        task = (
            self.db_session.query(AnalysisTask)
            .filter(AnalysisTask.id == task_id)
            .with_for_update()
            .one_or_none()
        )
        if task is None:
            self.db_session.commit()
            return None

        payload = task.payload or {}
        status = payload.get("queue_publish_status")
        if status == QUEUE_PUBLISH_PUBLISHED:
            self.db_session.commit()
            return None
        if payload.get("queue_published") is True:
            self.db_session.commit()
            return None
        now = self._as_utc(self.now_provider())
        if status == QUEUE_PUBLISH_PUBLISHING:
            claimed_at = self._parse_claimed_at(payload.get("queue_publish_claimed_at"))
            if claimed_at is not None:
                lease_expires_at = claimed_at + timedelta(
                    seconds=self.claim_lease_seconds
                )
                if now < lease_expires_at:
                    self.db_session.commit()
                    return None

        claim_token = uuid4().hex
        task.payload = {
            **payload,
            "queue_publish_status": QUEUE_PUBLISH_PUBLISHING,
            "queue_publish_claimed_at": now.isoformat(),
            "queue_publish_token": claim_token,
        }
        self.db_session.add(task)
        self.db_session.commit()
        return claim_token

    @staticmethod
    def _parse_claimed_at(value):
        if not isinstance(value, str):
            return None
        try:
            claimed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return TaskRepository._as_utc(claimed_at)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def mark_queue_published(self, task_id: str, *, claim_token: str) -> bool:
        task = (
            self.db_session.query(AnalysisTask)
            .filter(AnalysisTask.id == task_id)
            .with_for_update()
            .one_or_none()
        )
        if task is None:
            self.db_session.commit()
            return False

        payload = dict(task.payload or {})
        if payload.get("queue_publish_token") != claim_token:
            self.db_session.commit()
            return False
        payload["queue_publish_status"] = QUEUE_PUBLISH_PUBLISHED
        payload.pop("queue_publish_claimed_at", None)
        payload.pop("queue_publish_token", None)
        task.payload = payload
        self.db_session.add(task)
        self.db_session.commit()
        return True

    def mark_queue_publish_pending(self, task_id: str, *, claim_token: str) -> bool:
        task = (
            self.db_session.query(AnalysisTask)
            .filter(AnalysisTask.id == task_id)
            .with_for_update()
            .one_or_none()
        )
        if task is None:
            self.db_session.commit()
            return False

        payload = dict(task.payload or {})
        if payload.get("queue_publish_token") != claim_token:
            self.db_session.commit()
            return False
        payload["queue_publish_status"] = QUEUE_PUBLISH_PENDING
        payload.pop("queue_publish_claimed_at", None)
        payload.pop("queue_publish_token", None)
        task.payload = payload
        self.db_session.add(task)
        self.db_session.commit()
        return True

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
