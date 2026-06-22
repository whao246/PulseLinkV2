from __future__ import annotations

from pydantic import BaseModel


class UploadPresignRequest(BaseModel):
    file_name: str
    file_size: int
    sha256: str
    content_type: str


class FileRegistrationRequest(BaseModel):
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    storage_uri: str
    sha256: str | None = None
