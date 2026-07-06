from __future__ import annotations

import os
import re
from typing import Annotated
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.dependencies.auth import get_current_user_id
from app.api.schemas.files import FileRegistrationRequest, UploadPresignRequest
from app.application.file_service import FileService
from app.core.responses import ok
from app.infrastructure.storage.cos_presign import create_cos_put_presign


uploads_router = APIRouter(prefix="/api/uploads", tags=["uploads"])
router = APIRouter(prefix="/api/files", tags=["files"])


@uploads_router.post("/pdf/presign")
def create_pdf_upload_presign(
    payload: UploadPresignRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    _validate_pdf_upload(payload)
    bucket = os.getenv("COS_BUCKET", "pulselink-local")
    endpoint = os.getenv("COS_ENDPOINT", "http://minio:9000")
    expires_in = int(os.getenv("UPLOAD_PRESIGN_EXPIRES_SECONDS", "900"))
    today = datetime.now(timezone.utc)
    safe_name = _safe_filename(payload.file_name)
    object_key = (
        f"uploads/{user_id}/{today:%Y/%m}/file_{uuid4().hex}_{safe_name}"
    )
    presign = create_cos_put_presign(
        endpoint=endpoint,
        bucket=bucket,
        object_key=object_key,
        content_type=payload.content_type,
        expires_in=expires_in,
        secret_id=os.getenv("COS_SECRET_ID"),
        secret_key=os.getenv("COS_SECRET_KEY"),
    )

    return ok(
        {
            "upload": {
                "method": "PUT",
                "url": presign.url,
                "headers": presign.headers,
                "expires_in": expires_in,
            },
            "object": {
                "bucket": bucket,
                "key": object_key,
                "content_type": payload.content_type,
                "size_bytes": payload.file_size,
                "sha256": payload.sha256,
            },
            "storage_uri": f"cos://{bucket}/{object_key}",
        },
        request,
    )


@uploads_router.post("/presign")
def create_upload_presign(
    payload: UploadPresignRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    return create_pdf_upload_presign(payload, request, user_id)


@router.post("")
def register_file(
    payload: FileRegistrationRequest,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    user_id: str = Depends(get_current_user_id),
):
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise RuntimeError("database is not configured")

    db_session = session_factory()
    try:
        file = FileService(db_session=db_session).register_file(
            user_id=user_id,
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


def _validate_pdf_upload(payload: UploadPresignRequest) -> None:
    if not payload.file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="file_name must end with .pdf")
    if payload.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="content_type must be application/pdf")
    max_size = int(os.getenv("PDF_MAX_SIZE_MB", "50")) * 1024 * 1024
    if payload.file_size <= 0 or payload.file_size > max_size:
        raise HTTPException(status_code=422, detail="file_size is out of range")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", payload.sha256):
        raise HTTPException(status_code=422, detail="sha256 must be 64 hex characters")


def _safe_filename(file_name: str) -> str:
    basename = file_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    return cleaned or "upload.pdf"
