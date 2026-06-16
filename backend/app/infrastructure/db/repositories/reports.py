from __future__ import annotations

from app.infrastructure.db.models import Report


class ReportRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def list_reports(self) -> list[Report]:
        return self.db_session.query(Report).order_by(Report.created_at, Report.id).all()
