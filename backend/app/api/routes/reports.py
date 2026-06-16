from __future__ import annotations

from fastapi import APIRouter, Request

from app.application.report_service import ReportService
from app.core.responses import ok


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(request: Request):
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        return ok({"items": []}, request)

    db_session = session_factory()
    try:
        reports = ReportService(db_session=db_session).list_reports()
        items = [
            {
                "id": report.id,
                "task_id": report.task_id,
                "title": report.title,
                "status": report.status,
                "storage_uri": report.storage_uri,
                "payload": report.payload,
            }
            for report in reports
        ]
    finally:
        db_session.close()

    return ok({"items": items}, request)
