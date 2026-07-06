from __future__ import annotations

import os

from redis import Redis
from rq import Queue, SimpleWorker, Worker

from app.core.logging import configure_logging
from app.workers.jobs.analyze_document import run as analyze_document


def start_worker(*, burst: bool = False) -> bool:
    configure_logging()
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    queue_name = os.getenv("QUEUE_NAME", "pulselink")
    connection = Redis.from_url(redis_url)
    queue = Queue(queue_name, connection=connection)
    worker_type = SimpleWorker if os.getenv("RQ_WORKER_CLASS") == "simple" else Worker
    worker = worker_type([queue], connection=connection)
    return worker.work(burst=burst)


def main() -> None:
    start_worker()


if __name__ == "__main__":
    main()


__all__ = ["analyze_document", "main", "start_worker"]
