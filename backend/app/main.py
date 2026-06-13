from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import health


def create_app(
    *,
    database_url: str | None = None,
    run_analysis_inline: bool = False,
) -> FastAPI:
    app = FastAPI(title="PulseLinkV2 API")
    app.state.database_url = database_url
    app.state.run_analysis_inline = run_analysis_inline
    app.include_router(health.router)
    return app


app = create_app()
