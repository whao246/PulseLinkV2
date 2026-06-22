from __future__ import annotations

import base64
import json
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds

    def complete_json(
        self, *, messages: list[dict[str, str]], temperature: float = 0
    ) -> dict[str, Any]:
        response = self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return _parse_chat_json_response(response)

    def understand_image_json(
        self, *, prompt: str, image_bytes: bytes
    ) -> dict[str, Any]:
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        response = self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
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
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return _parse_chat_json_response(response)


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
