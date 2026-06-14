import httpx
import pytest

from app.infrastructure.model_clients.local_fallback_client import LocalFallbackClient
from app.infrastructure.model_clients.openai_compatible_client import OpenAICompatibleClient


def test_local_fallback_returns_json_object():
    client = LocalFallbackClient()

    result = client.complete_json(messages=[{"role": "user", "content": "hi"}])

    assert result["fallback"] is True


def test_openai_compatible_client_parses_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"ok\": true}"}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.complete_json(messages=[{"role": "user", "content": "hi"}]) == {"ok": True}


def test_openai_compatible_client_rejects_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ValueError, match="invalid model JSON"):
        client.complete_json(messages=[{"role": "user", "content": "hi"}])
