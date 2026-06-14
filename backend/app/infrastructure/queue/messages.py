from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class AnalyzeDocumentRequested:
    event_id: str
    task_id: str
    file_id: str
    user_id: str
    requested_at: str
    event_type: str = field(init=False, default="AnalyzeDocumentRequested")
    schema_version: int = field(init=False, default=1)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
