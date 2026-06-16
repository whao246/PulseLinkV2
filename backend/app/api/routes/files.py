from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Header, Request

from app.api.schemas.files import FileRegistrationRequest
from app.application.file_service import FileService
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
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise RuntimeError("database is not configured")

    db_session = session_factory()
    try:
        file = FileService(db_session=db_session).register_file(
            user_id="local-test-user",
            filename=payload.filename,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            storage_uri=payload.storage_uri,
            sha256=payload.sha256,
            idempotency_key=idempotency_key,
        )
    finally:
        db_session.close()

    return ok(
        {
            "file_id": file.id,
            "file": {
                "id": file.id,
                "filename": file.filename,
                "content_type": file.content_type,
                "size_bytes": file.size_bytes,
                "storage_uri": file.storage_uri,
                "sha256": file.sha256,
                "idempotency_key": idempotency_key,
            },
        },
        request,
    )
