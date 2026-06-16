from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.responses import ok


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(request: Request):
    return ok({"items": []}, request)
