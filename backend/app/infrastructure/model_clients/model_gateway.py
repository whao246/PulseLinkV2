from __future__ import annotations

from typing import Any, Protocol


class ModelGateway(Protocol):
    def complete_json(
        self, *, messages: list[dict[str, str]], temperature: float = 0
    ) -> dict[str, Any]:
        ...

    def understand_image_json(
        self, *, prompt: str, image_bytes: bytes
    ) -> dict[str, Any]:
        ...
