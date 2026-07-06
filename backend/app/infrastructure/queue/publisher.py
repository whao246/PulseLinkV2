from __future__ import annotations

import os


ANALYZE_DOCUMENT_JOB_PATH = "app.workers.jobs.analyze_document.run"


class QueuePublisher:
    def __init__(self, *, queue):
        self.queue = queue

    def publish_analyze_document(self, *, task_id: str) -> None:
        self.queue.enqueue(
            ANALYZE_DOCUMENT_JOB_PATH,
            task_id=task_id,
            job_timeout=int(os.getenv("RQ_JOB_TIMEOUT_SECONDS", "600")),
        )
