from fastapi.testclient import TestClient

from app.infrastructure.db.models import AnalysisTask, File, Report, User
from app.main import create_app


def test_list_reports_reads_current_user_database():
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
            User(
                id="usr_other",
                email="usr_other@example.com",
                display_name="Other User",
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
            File(
                id="file_other",
                user_id="usr_other",
                sha256="sha_other",
                filename="other.pdf",
                storage_uri="local://other.pdf",
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
            AnalysisTask(
                id="task_other",
                user_id="usr_other",
                file_id="file_other",
                idempotency_key="idem_other",
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
        db_session.add(
            Report(
                id="report_other",
                task_id="task_other",
                title="Other Report",
                status="ready",
                storage_uri="local://other.json",
                payload={"score": 66},
            )
        )
        db_session.commit()
    finally:
        db_session.close()

    response = TestClient(app).get(
        "/api/reports",
        headers={"Authorization": "Bearer test-token-usr_report"},
    )

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


def test_list_reports_requires_authentication():
    app = create_app(database_url="sqlite:///:memory:")

    response = TestClient(app).get("/api/reports")

    assert response.status_code == 401
