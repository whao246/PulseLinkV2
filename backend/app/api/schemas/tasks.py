from __future__ import annotations

from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    file_id: str
    options: dict = Field(default_factory=dict)
