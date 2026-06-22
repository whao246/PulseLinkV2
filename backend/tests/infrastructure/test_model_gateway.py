import json
import base64

import httpx
import pytest

from app.infrastructure.model_clients.local_fallback_client import LocalFallbackClient
from app.infrastructure.model_clients.openai_compatible_client import OpenAICompatibleClient


def test_local_fallback_returns_json_object():
    client = LocalFallbackClient()

    result = client.complete_json(messages=[{"role": "user", "content": "hi"}])

    assert result["fallback"] is True


def test_local_fallback_understands_image_json():
    client = LocalFallbackClient()

    result = client.understand_image_json(prompt="describe", image_bytes=b"image")

    assert result == {"fallback": True, "prompt": "describe", "image_size": 5}


def test_openai_compatible_client_parses_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://models.example.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer key"
        payload = request.read()
        assert payload
        json_payload = json.loads(payload)
        assert json_payload["model"] == "MiniMax-M3"
        assert json_payload["messages"] == [{"role": "user", "content": "hi"}]
        assert json_payload["temperature"] == 0
        assert json_payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"ok\": true}"}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1/",
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


def test_openai_compatible_client_rejects_non_object_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "[]"}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ValueError, match="expected object"):
        client.complete_json(messages=[{"role": "user", "content": "hi"}])


def test_openai_compatible_client_rejects_invalid_response_schema():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {}}]})

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ValueError, match="invalid model response schema"):
        client.complete_json(messages=[{"role": "user", "content": "hi"}])


def test_openai_compatible_client_sends_image_as_data_url_and_parses_json():
    image_bytes = b"fake-image"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://models.example.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer key"
        json_payload = json.loads(request.read())
        assert json_payload["model"] == "MiniMax-M3"
        assert json_payload["response_format"] == {"type": "json_object"}
        content = json_payload["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "extract table"}
        assert content[1]["type"] == "image_url"
        expected = base64.b64encode(image_bytes).decode("ascii")
        assert content[1]["image_url"]["url"] == f"data:image/png;base64,{expected}"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"tables\": 2}"}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.understand_image_json(prompt="extract table", image_bytes=image_bytes) == {
        "tables": 2
    }
