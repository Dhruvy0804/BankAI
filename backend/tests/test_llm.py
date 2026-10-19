import json

import httpx
import pytest
from google import genai
from google.genai import types

from app.core.config import Settings
from app.core.errors import APIError
from app.services.llm import GeminiProvider


def configured(**kwargs):
    return Settings(
        _env_file=None,
        llm_provider="gemini",
        llm_api_key="test-secret-not-real",
        llm_model="test-model",
        **kwargs,
    )


def install_transport(monkeypatch, handler):
    real_client = genai.Client

    def client(**kwargs):
        options = kwargs["http_options"]
        assert options.timeout == 30000
        assert options.retry_options.attempts == 1
        return real_client(
            api_key=kwargs["api_key"],
            http_options=types.HttpOptions(
                timeout=options.timeout,
                retry_options=options.retry_options,
                client_args={"transport": httpx.MockTransport(handler)},
            ),
        )

    monkeypatch.setattr("app.services.llm.genai.Client", client)


def provider_json(text):
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {
            "promptTokenCount": 18,
            "candidatesTokenCount": 12,
            "totalTokenCount": 30,
        },
    }


def test_real_sdk_serializes_history_schema_and_usage(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert body["contents"][-1]["parts"][0]["text"] == "What is an EMI?"
        assert body["contents"][0]["role"] == "user"
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseSchema" not in body["generationConfig"]
        assert body["generationConfig"]["responseJsonSchema"]["additionalProperties"] is False
        assert "tools" not in body
        assert "NO tools" in str(body["systemInstruction"])
        return httpx.Response(
            200,
            json=provider_json('{"status":"guidance","answer":"An EMI is a monthly instalment."}'),
        )

    install_transport(monkeypatch, handler)
    result = GeminiProvider(configured()).generate([("user", "What is an EMI?")])
    assert result.guidance.status == "guidance"
    assert result.total_tokens == 30
    assert result.input_tokens == 18


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "",
        '{"status":"executed","answer":"Done"}',
        '{"status":"guidance","answer":"OK","balance":999}',
    ],
)
def test_invalid_provider_output_is_rejected(monkeypatch, text):
    install_transport(monkeypatch, lambda request: httpx.Response(200, json=provider_json(text)))
    with pytest.raises(APIError) as failure:
        GeminiProvider(configured()).generate([("user", "Hello")])
    assert failure.value.code == "LLM_INVALID_OUTPUT"
    assert "999" not in failure.value.message


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_provider_errors_are_sanitized_and_not_retried(monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": {"code": status, "message": "secret-provider-detail"}}
        )

    install_transport(monkeypatch, handler)
    with pytest.raises(APIError) as failure:
        GeminiProvider(configured()).generate([("user", "Hello")])
    assert failure.value.code == "LLM_UNAVAILABLE"
    assert "secret" not in failure.value.message
    assert len(calls) == 1


def test_timeout_is_sanitized(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("secret timeout details", request=request)

    install_transport(monkeypatch, handler)
    with pytest.raises(APIError) as failure:
        GeminiProvider(configured()).generate([("user", "Hello")])
    assert failure.value.code == "LLM_TIMEOUT"


def test_missing_configuration_never_opens_client(monkeypatch):
    monkeypatch.setattr("app.services.llm.genai.Client", lambda **kwargs: pytest.fail("No network"))
    with pytest.raises(APIError) as failure:
        GeminiProvider(Settings(_env_file=None)).generate([("user", "Hello")])
    assert failure.value.code == "LLM_NOT_CONFIGURED"
