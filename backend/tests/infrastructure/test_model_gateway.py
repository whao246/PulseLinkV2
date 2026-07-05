import json
import base64

import httpx
import pytest

from app.infrastructure.model_clients.local_fallback_client import LocalFallbackClient
from app.infrastructure.model_clients.factory import build_model_gateway_from_env
from app.infrastructure.model_clients.minimax_client import MiniMaxClient
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


def test_openai_compatible_client_parses_json_from_markdown_fence():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "```json\n{\"ok\": true, \"score\": 8}\n```"}}
                ]
            },
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.complete_json(messages=[{"role": "user", "content": "hi"}]) == {
        "ok": True,
        "score": 8,
    }


def test_openai_compatible_client_extracts_json_object_from_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Here is the structured result:\n"
                                "{\"ok\": true, \"nested\": {\"value\": 1}}\n"
                                "Please review."
                            )
                        }
                    }
                ]
            },
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.complete_json(messages=[{"role": "user", "content": "hi"}]) == {
        "ok": True,
        "nested": {"value": 1},
    }


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


def test_openai_compatible_client_retries_transient_rate_limit():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"ok\": true}"}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_attempts=2,
        retry_backoff_seconds=0,
    )

    assert client.complete_json(messages=[{"role": "user", "content": "hi"}]) == {"ok": True}
    assert len(calls) == 2


def test_openai_compatible_client_raises_after_rate_limit_retries():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, json={"error": "rate limited"})

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_attempts=1,
        retry_backoff_seconds=0,
    )

    with pytest.raises(httpx.HTTPStatusError, match="429"):
        client.complete_json(messages=[{"role": "user", "content": "hi"}])
    assert len(calls) == 2


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


def test_model_gateway_factory_uses_local_fallback_without_key(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    client = build_model_gateway_from_env()

    assert isinstance(client, LocalFallbackClient)


def test_model_gateway_factory_builds_minimax_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LLM_API_BASE", "https://api.minimax.chat/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M3")

    client = build_model_gateway_from_env()

    assert isinstance(client, MiniMaxClient)
    assert client.base_url == "https://api.minimax.chat/v1"
    assert client.model == "MiniMax-M3"


def test_model_gateway_factory_requires_key_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="LLM_API_KEY is required"):
        build_model_gateway_from_env()
