from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas.auth import TestLoginRequest
from app.application.auth_service import AuthService
from app.core.responses import ok


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/test-login")
def test_login(payload: TestLoginRequest, request: Request):
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is not None:
        db_session = session_factory()
        try:
            AuthService(db_session=db_session).ensure_test_user(user_id=payload.user_id)
        finally:
            db_session.close()

    return ok(
        {
            "access_token": f"test-token-{payload.user_id}",
            "token_type": "bearer",
            "user_id": payload.user_id,
        },
        request,
    )
