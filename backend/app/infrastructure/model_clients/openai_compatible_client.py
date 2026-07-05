from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        http_client: httpx.Client | None = None,
        timeout_seconds: int = 60,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds

    def complete_json(
        self, *, messages: list[dict[str, str]], temperature: float = 0
    ) -> dict[str, Any]:
        response = self._post_chat_completions(
            {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }
        )
        return _parse_chat_json_response(response)

    def understand_image_json(
        self, *, prompt: str, image_bytes: bytes
    ) -> dict[str, Any]:
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        response = self._post_chat_completions(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}",
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        )
        return _parse_chat_json_response(response)

    def _post_chat_completions(self, payload: dict[str, Any]) -> httpx.Response:
        last_error: httpx.HTTPStatusError | None = None
        for attempt in range(self.retry_attempts + 1):
            response = self.http_client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
            try:
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if attempt >= self.retry_attempts or not _is_transient_status(
                    exc.response.status_code
                ):
                    raise
                time.sleep(_retry_delay_seconds(response, self.retry_backoff_seconds))
        if last_error is not None:
            raise last_error
        raise RuntimeError("model request failed without response")


def _is_transient_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _retry_delay_seconds(response: httpx.Response, fallback_seconds: float) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            return fallback_seconds
    return fallback_seconds


def _parse_chat_json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise ValueError("invalid model response schema") from exc

    try:
        choices = payload["choices"]
        message = choices[0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("invalid model response schema") from exc

    if not isinstance(content, str):
        raise ValueError("invalid model response schema")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid model JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("invalid model JSON: expected object")

    return parsed
