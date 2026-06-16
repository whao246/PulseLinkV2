from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@dataclass
class SamplePdfFile:
    registration_payload: dict


@pytest.fixture
def test_client():
    return TestClient(create_app(database_url="sqlite:///:memory:"))


@pytest.fixture
def sample_pdf_file():
    return SamplePdfFile(
        registration_payload={
            "filename": "sample.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
            "storage_uri": "local://sample.pdf",
        }
    )


def test_api_to_report_flow(test_client, sample_pdf_file):
    token = test_client.post(
        "/api/auth/test-login",
        json={"user_id": "usr_e2e"},
    ).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    file_response = test_client.post(
        "/api/files",
        headers={**headers, "Idempotency-Key": "file-e2e-1"},
        json=sample_pdf_file.registration_payload,
    )
    file_id = file_response.json()["data"]["file"]["id"]

    task_response = test_client.post(
        "/api/analysis-tasks",
        headers={**headers, "Idempotency-Key": "task-e2e-1"},
        json={"file_id": file_id, "options": {"enable_vision": True}},
    )

    assert task_response.status_code == 200
    assert task_response.json()["data"]["task"]["id"]
