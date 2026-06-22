from __future__ import annotations

from app.infrastructure.model_clients.openai_compatible_client import (
    OpenAICompatibleClient,
)


class MiniMaxClient(OpenAICompatibleClient):
    """MiniMax chat completions client using the OpenAI-compatible API shape."""
