from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.responses import ok


uploads_router = APIRouter(prefix="/api/uploads", tags=["uploads"])
router = APIRouter(prefix="/api/files", tags=["files"])


@uploads_router.post("/presign")
def create_upload_presign(request: Request):
    return ok({"upload_url": None, "fields": {}}, request)


@router.post("")
def register_file(request: Request):
    return ok({"file_id": None}, request)
