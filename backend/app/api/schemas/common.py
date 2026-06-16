from __future__ import annotations

from pydantic import BaseModel


class ErrorData(BaseModel):
    error_code: str
    message: str
