from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.api.schemas.auth import TestLoginRequest, WechatLoginRequest
from app.api.dependencies.auth import create_access_token
from app.application.auth_service import AuthService
from app.core.responses import ok


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/test-login")
def test_login(payload: TestLoginRequest, request: Request):
    if os.getenv("APP_ENV", "local") == "prod":
        raise HTTPException(status_code=404, detail="Not Found")

    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is not None:
        db_session = session_factory()
        try:
            AuthService(db_session=db_session).ensure_test_user(user_id=payload.user_id)
        finally:
            db_session.close()

    return ok(
        {
            "access_token": create_access_token(payload.user_id),
            "token_type": "bearer",
            "user_id": payload.user_id,
        },
        request,
    )


@router.post("/wechat-login")
def wechat_login(payload: WechatLoginRequest, request: Request):
    app_id = os.getenv("WECHAT_APP_ID")
    app_secret = os.getenv("WECHAT_APP_SECRET")
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "WECHAT_CONFIG_MISSING",
                "message": "WECHAT_APP_ID and WECHAT_APP_SECRET are required",
            },
        )

    wechat_payload = _exchange_wechat_code(
        app_id=app_id,
        app_secret=app_secret,
        code=payload.code,
    )
    openid = wechat_payload.get("openid")
    if not isinstance(openid, str) or not openid:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "WECHAT_LOGIN_FAILED",
                "message": wechat_payload.get("errmsg") or "invalid wechat code",
            },
        )

    user_id = f"wechat:{openid}"
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is not None:
        db_session = session_factory()
        try:
            AuthService(db_session=db_session).ensure_wechat_user(openid=openid)
        finally:
            db_session.close()

    return ok(
        {
            "access_token": create_access_token(user_id),
            "token_type": "bearer",
            "user_id": user_id,
        },
        request,
    )


def _exchange_wechat_code(*, app_id: str, app_secret: str, code: str) -> dict:
    try:
        response = httpx.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": app_id,
                "secret": app_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "error_code": "WECHAT_UPSTREAM_ERROR",
                    "message": "wechat login upstream request failed",
                },
            )
        payload = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "WECHAT_UPSTREAM_ERROR",
                "message": "wechat login upstream request failed",
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "WECHAT_UPSTREAM_ERROR",
                "message": "wechat login upstream response is invalid",
            },
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "WECHAT_UPSTREAM_ERROR",
                "message": "wechat login upstream response is invalid",
            },
        )
    return payload
