from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas.auth import TestLoginRequest
from app.core.responses import ok


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/test-login")
def test_login(payload: TestLoginRequest, request: Request):
    return ok(
        {
            "access_token": f"test-token-{payload.user_id}",
            "token_type": "bearer",
            "user_id": payload.user_id,
        },
        request,
    )
