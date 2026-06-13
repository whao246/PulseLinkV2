from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.responses import ok


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request):
    return ok({"status": "ok", "version": "0.1.0"}, request)
