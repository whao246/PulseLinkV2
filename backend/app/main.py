from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import auth, files, health, reports, tasks


def create_app(
    *,
    database_url: str | None = None,
    run_analysis_inline: bool = False,
) -> FastAPI:
    app = FastAPI(title="PulseLinkV2 API")
    app.state.database_url = database_url
    app.state.run_analysis_inline = run_analysis_inline
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


app = create_app()
