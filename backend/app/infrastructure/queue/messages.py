from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AnalyzeDocumentRequested:
    event_id: str
    task_id: str
    file_id: str
    user_id: str
    requested_at: str
    event_type: str = "AnalyzeDocumentRequested"
    schema_version: int = 1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
