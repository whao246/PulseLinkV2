from __future__ import annotations

from pydantic import BaseModel


class FileRegistrationRequest(BaseModel):
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    storage_uri: str
    sha256: str | None = None
