from __future__ import annotations

from app.infrastructure.db.models import AnalysisTask, Report


class ReportRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def list_reports(self, *, user_id: str) -> list[Report]:
        return (
            self.db_session.query(Report)
            .join(AnalysisTask, AnalysisTask.id == Report.task_id)
            .filter(AnalysisTask.user_id == user_id)
            .order_by(Report.created_at, Report.id)
            .all()
        )
