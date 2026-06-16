from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, Request

from app.api.schemas.files import FileRegistrationRequest
from app.core.responses import ok


uploads_router = APIRouter(prefix="/api/uploads", tags=["uploads"])
router = APIRouter(prefix="/api/files", tags=["files"])


@uploads_router.post("/presign")
def create_upload_presign(request: Request):
    return ok({"upload_url": None, "fields": {}}, request)


@router.post("")
def register_file(
    payload: FileRegistrationRequest,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    file_id = f"file_{uuid4().hex}"
    return ok(
        {
            "file_id": file_id,
            "file": {
                "id": file_id,
                "filename": payload.filename,
                "content_type": payload.content_type,
                "size_bytes": payload.size_bytes,
                "storage_uri": payload.storage_uri,
                "idempotency_key": idempotency_key,
            },
        },
        request,
    )
