from __future__ import annotations

from pydantic import BaseModel


class ReportSummary(BaseModel):
    task_id: str
    status: str
