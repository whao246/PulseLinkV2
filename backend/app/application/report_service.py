from __future__ import annotations

from app.infrastructure.db.repositories.reports import ReportRepository


class ReportService:
    def __init__(self, *, db_session):
        self.reports = ReportRepository(db_session)

    def list_reports(self, *, user_id: str):
        return self.reports.list_reports(user_id=user_id)
