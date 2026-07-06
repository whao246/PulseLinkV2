from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        http_client: httpx.Client | None = None,
        timeout_seconds: int = 360,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 1,
        reasoning_split: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.reasoning_split = reasoning_split

    def complete_json(
        self, *, messages: list[dict[str, str]], temperature: float = 0
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        self._apply_reasoning_options(payload)
        response = self._post_chat_completions(payload)
        return _parse_chat_json_response(response)

    def understand_image_json(
        self, *, prompt: str, image_bytes: bytes
    ) -> dict[str, Any]:
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        payload = {
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
        self._apply_reasoning_options(payload)
        response = self._post_chat_completions(payload)
        return _parse_chat_json_response(response)

    def _apply_reasoning_options(self, payload: dict[str, Any]) -> None:
        if self.reasoning_split:
            payload["reasoning_split"] = True

    def _post_chat_completions(self, payload: dict[str, Any]) -> httpx.Response:
        last_error: httpx.HTTPStatusError | None = None
        for attempt in range(self.retry_attempts + 1):
            attempt_number = attempt + 1
            started_at = time.monotonic()
            logger.info(
                "llm request start model=%s base_url=%s attempt=%s/%s timeout=%s message_count=%s",
                self.model,
                self.base_url,
                attempt_number,
                self.retry_attempts + 1,
                self.timeout_seconds,
                len(payload.get("messages", [])),
            )
            try:
                response = self.http_client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException:
                logger.exception(
                    "llm request timeout model=%s attempt=%s elapsed=%.2fs",
                    self.model,
                    attempt_number,
                    time.monotonic() - started_at,
                )
                raise
            except httpx.HTTPError:
                logger.exception(
                    "llm request failed model=%s attempt=%s elapsed=%.2fs",
                    self.model,
                    attempt_number,
                    time.monotonic() - started_at,
                )
                raise
            logger.info(
                "llm response received model=%s attempt=%s status_code=%s elapsed=%.2fs",
                self.model,
                attempt_number,
                response.status_code,
                time.monotonic() - started_at,
            )
            response_preview = _response_log_preview(response)
            if response_preview is not None:
                logger.info(
                    "llm response body model=%s attempt=%s preview=%s",
                    self.model,
                    attempt_number,
                    response_preview,
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
                delay_seconds = _retry_delay_seconds(
                    response, self.retry_backoff_seconds
                )
                logger.warning(
                    "llm request retry scheduled model=%s attempt=%s status_code=%s delay=%.2fs",
                    self.model,
                    attempt_number,
                    exc.response.status_code,
                    delay_seconds,
                )
                time.sleep(delay_seconds)
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


def _response_log_preview(response: httpx.Response) -> str | None:
    limit = int(os.getenv("LLM_RESPONSE_LOG_MAX_CHARS", "2000"))
    if limit <= 0:
        return None
    body = " ".join(response.text.split())
    if len(body) > limit:
        return f"{body[:limit]}..."
    return body


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

    return _parse_model_json_content(content)


def _parse_model_json_content(content: str) -> dict[str, Any]:
    stripped = _strip_think_blocks(content.strip()).strip()
    candidates = [stripped]

    fenced = _strip_markdown_fence(stripped)
    if fenced != stripped:
        candidates.append(fenced)

    embedded_object = _extract_first_json_object(stripped)
    if embedded_object is not None:
        candidates.append(embedded_object)

    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(parsed, dict):
            raise ValueError("invalid model JSON: expected object")
        return parsed

    message = f"invalid model JSON: {_preview_content(stripped)}"
    if last_error is not None:
        raise ValueError(message) from last_error
    raise ValueError(message)


def _strip_markdown_fence(content: str) -> str:
    if not content.startswith("```"):
        return content

    lines = content.splitlines()
    if len(lines) < 2:
        return content

    first_line = lines[0].strip().lower()
    if first_line not in {"```", "```json"}:
        return content

    if lines[-1].strip() == "```":
        lines = lines[1:-1]
    else:
        lines = lines[1:]

    return "\n".join(lines).strip()


def _strip_think_blocks(content: str) -> str:
    without_closed_blocks = re.sub(
        r"<think\b[^>]*>.*?</think>",
        "",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not re.match(r"^\s*<think\b", without_closed_blocks, flags=re.IGNORECASE):
        return without_closed_blocks

    first_json_start = without_closed_blocks.find("{")
    if first_json_start == -1:
        return without_closed_blocks
    return without_closed_blocks[first_json_start:]


def _extract_first_json_object(content: str) -> str | None:
    start = content.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(content)):
        char = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[start : index + 1]

    return None


def _preview_content(content: str, limit: int = 120) -> str:
    preview = " ".join(content.split())
    if len(preview) > limit:
        return f"{preview[:limit]}..."
    return preview
