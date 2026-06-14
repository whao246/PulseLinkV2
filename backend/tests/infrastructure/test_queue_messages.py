from app.infrastructure.queue.messages import AnalyzeDocumentRequested
from app.infrastructure.queue.publisher import QueuePublisher


def test_analyze_document_message_serializes_schema_version():
    message = AnalyzeDocumentRequested(
        event_id="evt_1",
        task_id="task_1",
        file_id="file_1",
        user_id="usr_1",
        requested_at="2026-06-13T10:00:00Z",
    )

    payload = message.to_dict()

    assert payload["event_type"] == "AnalyzeDocumentRequested"
    assert payload["schema_version"] == 1


def test_queue_publisher_enqueues_task_id():
    captured = {}

    class FakeQueue:
        def enqueue(self, func_path, **kwargs):
            captured["func_path"] = func_path
            captured["kwargs"] = kwargs

    publisher = QueuePublisher(queue=FakeQueue())
    publisher.publish_analyze_document(task_id="task_1")

    assert captured["kwargs"]["task_id"] == "task_1"
