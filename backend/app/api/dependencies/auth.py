from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Annotated, Any

from fastapi import Header, HTTPException


LOCAL_TEST_TOKEN = "test-token"
LOCAL_TEST_TOKEN_PREFIX = "test-token-"


def get_current_user_id(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    if not authorization:
        raise _unauthorized("Authorization header is required")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Bearer token is required")

    return resolve_user_id_from_token(token)


def resolve_user_id_from_token(token: str) -> str:
    if os.getenv("APP_ENV", "local") != "prod":
        local_user_id = _resolve_local_test_token(token)
        if local_user_id is not None:
            return local_user_id

    payload = _decode_access_token(token)
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise _unauthorized("invalid token subject")
    return user_id


def create_access_token(
    user_id: str,
    *,
    expires_in_seconds: int = 86400,
    now: int | None = None,
) -> str:
    issued_at = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "iat": issued_at,
        "exp": issued_at + expires_in_seconds,
    }
    signing_input = (
        f"{_base64url_json(header)}.{_base64url_json(payload)}"
    ).encode("ascii")
    signature = _sign(signing_input)
    return f"{signing_input.decode('ascii')}.{_base64url_encode(signature)}"


def _resolve_local_test_token(token: str) -> str | None:
    if token == LOCAL_TEST_TOKEN:
        return "local-test-user"
    if token.startswith(LOCAL_TEST_TOKEN_PREFIX):
        user_id = token[len(LOCAL_TEST_TOKEN_PREFIX) :]
        if re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", user_id):
            return user_id
    return None


def _decode_access_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise _unauthorized("invalid token format")

    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected_signature = _base64url_encode(_sign(signing_input))
    if not hmac.compare_digest(expected_signature, parts[2]):
        raise _unauthorized("invalid token signature")

    try:
        header = json.loads(_base64url_decode(parts[0]))
        payload = json.loads(_base64url_decode(parts[1]))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise _unauthorized("invalid token payload") from exc

    if header.get("alg") != "HS256":
        raise _unauthorized("unsupported token algorithm")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or int(time.time()) >= expires_at:
        raise _unauthorized("token expired")

    return payload


def _sign(signing_input: bytes) -> bytes:
    secret = os.getenv("JWT_SECRET", "change-me")
    return hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()


def _base64url_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64url_encode(raw)


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error_code": "UNAUTHORIZED", "message": message},
    )
