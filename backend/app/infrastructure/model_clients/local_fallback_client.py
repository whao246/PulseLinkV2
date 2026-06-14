from __future__ import annotations

from typing import Any


class LocalFallbackClient:
    def complete_json(
        self, *, messages: list[dict[str, str]], temperature: float = 0
    ) -> dict[str, Any]:
        return {"fallback": True, "message_count": len(messages)}

    def understand_image_json(
        self, *, prompt: str, image_bytes: bytes
    ) -> dict[str, Any]:
        return {
            "fallback": True,
            "prompt": prompt,
            "image_size": len(image_bytes),
        }
