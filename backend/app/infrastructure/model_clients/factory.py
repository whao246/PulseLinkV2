from __future__ import annotations

import os

from app.infrastructure.model_clients.local_fallback_client import LocalFallbackClient
from app.infrastructure.model_clients.minimax_client import MiniMaxClient


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_model_gateway_from_env():
    app_env = os.getenv("APP_ENV", "local")
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        if app_env == "prod":
            raise RuntimeError("LLM_API_KEY is required when APP_ENV=prod")
        return LocalFallbackClient()

    return MiniMaxClient(
        base_url=os.getenv("LLM_API_BASE", "https://api.minimax.chat/v1"),
        api_key=api_key,
        model=os.getenv("LLM_MODEL", "MiniMax-M3"),
        timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        retry_attempts=int(os.getenv("LLM_RETRY_ATTEMPTS", "2")),
        retry_backoff_seconds=float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "1")),
        reasoning_split=_env_bool("LLM_REASONING_SPLIT", True),
    )
