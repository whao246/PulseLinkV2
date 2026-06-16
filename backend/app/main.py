from __future__ import annotations

import os

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.api.routes import auth, files, health, reports, tasks
from app.infrastructure.db.base import Base
import app.infrastructure.db.models  # noqa: F401
from app.infrastructure.queue.publisher import QueuePublisher


def create_app(
    *,
    database_url: str | None = None,
    run_analysis_inline: bool = False,
) -> FastAPI:
    app = FastAPI(title="PulseLinkV2 API")
    resolved_database_url = database_url or os.getenv("DATABASE_URL")
    app.state.database_url = resolved_database_url
    app.state.run_analysis_inline = run_analysis_inline
    if resolved_database_url:
        engine_kwargs = {}
        if resolved_database_url == "sqlite:///:memory:":
            engine_kwargs = {
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            }
        engine = create_engine(resolved_database_url, **engine_kwargs)
        app.state.db_engine = engine
        app.state.db_session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        if resolved_database_url.startswith("sqlite"):
            Base.metadata.create_all(engine)

    queue_publisher = _build_queue_publisher(database_url=resolved_database_url)
    if queue_publisher is not None:
        app.state.queue_publisher = queue_publisher
    for router in [
        health.router,
        auth.router,
        files.uploads_router,
        files.router,
        tasks.router,
        reports.router,
    ]:
        app.include_router(router)
    return app


def _build_queue_publisher(*, database_url: str | None):
    if database_url and database_url.startswith("sqlite"):
        return None
    redis_url = os.getenv("REDIS_URL")
    queue_name = os.getenv("QUEUE_NAME", "pulselink")
    if not redis_url:
        return None
    try:
        from redis import Redis
        from rq import Queue
    except ImportError:
        return None
    return QueuePublisher(queue=Queue(queue_name, connection=Redis.from_url(redis_url)))


app = create_app()
