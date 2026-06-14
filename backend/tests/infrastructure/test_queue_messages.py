import pytest

from app.infrastructure.queue.messages import AnalyzeDocumentRequested
from app.infrastructure.queue.publisher import ANALYZE_DOCUMENT_JOB_PATH, QueuePublisher


def test_analyze_document_message_serializes_payload():
    message = AnalyzeDocumentRequested(
        event_id="evt_1",
        task_id="task_1",
        file_id="file_1",
        user_id="usr_1",
        requested_at="2026-06-13T10:00:00Z",
    )

    payload = message.to_dict()

    assert payload == {
        "event_id": "evt_1",
        "task_id": "task_1",
        "file_id": "file_1",
        "user_id": "usr_1",
        "requested_at": "2026-06-13T10:00:00Z",
        "event_type": "AnalyzeDocumentRequested",
        "schema_version": 1,
    }


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("event_type", "Bad"),
        ("schema_version", 2),
    ],
)
def test_analyze_document_message_rejects_protocol_constant_override(field_name, value):
    with pytest.raises(TypeError):
        AnalyzeDocumentRequested(
            event_id="evt_1",
            task_id="task_1",
            file_id="file_1",
            user_id="usr_1",
            requested_at="2026-06-13T10:00:00Z",
            **{field_name: value},
        )


def test_queue_publisher_enqueues_task_id():
    captured = {}

    class FakeQueue:
        def enqueue(self, func_path, **kwargs):
            captured["func_path"] = func_path
            captured["kwargs"] = kwargs

    publisher = QueuePublisher(queue=FakeQueue())
    publisher.publish_analyze_document(task_id="task_1")

    assert captured["func_path"] == ANALYZE_DOCUMENT_JOB_PATH
    assert captured["kwargs"]["task_id"] == "task_1"
