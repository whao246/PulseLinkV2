from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EvidenceSourceType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    VISION = "vision"


@dataclass(frozen=True)
class EvidenceUnit:
    id: str
    task_id: str
    page_number: int
    source_type: EvidenceSourceType
    source_ref: str
    category: str
    content: str
    structured_data: dict[str, Any]
    confidence_score: float

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number must be greater than or equal to 1")
        if not 0 <= self.confidence_score <= 1:
            raise ValueError("confidence_score must be between 0 and 1")
        if not self.content.strip():
            raise ValueError("content must not be empty")
