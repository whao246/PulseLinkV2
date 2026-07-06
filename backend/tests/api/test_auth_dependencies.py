import time

import pytest
from fastapi import HTTPException

from app.api.dependencies.auth import create_access_token, resolve_user_id_from_token


def test_local_test_token_resolves_local_user(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")

    assert resolve_user_id_from_token("test-token") == "local-test-user"
    assert resolve_user_id_from_token("test-token-usr_123") == "usr_123"


def test_prod_rejects_test_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    with pytest.raises(HTTPException) as exc:
        resolve_user_id_from_token("test-token")

    assert exc.value.status_code == 401


def test_signed_access_token_round_trips_user_id(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    token = create_access_token("usr_prod", expires_in_seconds=60)

    assert resolve_user_id_from_token(token) == "usr_prod"


def test_expired_access_token_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    token = create_access_token("usr_prod", now=int(time.time()) - 120, expires_in_seconds=1)

    with pytest.raises(HTTPException) as exc:
        resolve_user_id_from_token(token)

    assert exc.value.status_code == 401
