from __future__ import annotations


class QueuePublisher:
    def __init__(self, *, queue):
        self.queue = queue

    def publish_analyze_document(self, *, task_id: str) -> None:
        self.queue.enqueue(
            "app.workers.jobs.analyze_document.run",
            task_id=task_id,
        )
