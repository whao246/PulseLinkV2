from fastapi.testclient import TestClient

from app.infrastructure.db.models import AnalysisTask, File, Report, User
from app.main import create_app


def test_list_reports_reads_database():
    app = create_app(database_url="sqlite:///:memory:")
    db_session = app.state.db_session_factory()
    try:
        db_session.add(
            User(
                id="usr_report",
                email="usr_report@example.com",
                display_name="Report User",
                is_active=True,
            )
        )
        db_session.add(
            File(
                id="file_report",
                user_id="usr_report",
                sha256="sha_report",
                filename="report.pdf",
                storage_uri="local://report.pdf",
            )
        )
        db_session.add(
            AnalysisTask(
                id="task_report",
                user_id="usr_report",
                file_id="file_report",
                idempotency_key="idem_report",
                task_type="bp_analysis",
                model_profile="default",
                status="completed",
            )
        )
        db_session.add(
            Report(
                id="report_1",
                task_id="task_report",
                title="Report One",
                status="ready",
                storage_uri="local://report.json",
                payload={"score": 88},
            )
        )
        db_session.commit()
    finally:
        db_session.close()

    response = TestClient(app).get("/api/reports")

    assert response.status_code == 200
    assert response.json()["data"]["items"] == [
        {
            "id": "report_1",
            "task_id": "task_report",
            "title": "Report One",
            "status": "ready",
            "storage_uri": "local://report.json",
            "payload": {"score": 88},
        }
    ]
