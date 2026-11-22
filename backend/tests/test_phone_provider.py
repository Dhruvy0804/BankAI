import asyncio
import base64
import hashlib
import hmac
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.core.errors import APIError
from app.services import phone


def test_twilio_rejection_shows_only_safe_error_code(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, *_args, **_kwargs):
            return SimpleNamespace(
                status_code=400,
                json=lambda: {"code": 10002, "message": "Secret token and phone number"},
            )

    monkeypatch.setattr(phone.httpx, "AsyncClient", lambda **_kwargs: Client())
    settings = SimpleNamespace(
        phone_provider="twilio",
        twilio_account_sid=SecretStr("AC" + "a" * 32),
        twilio_auth_token=SecretStr("test-token"),
    )
    with pytest.raises(APIError) as raised:
        asyncio.run(phone.PhoneManager(None, settings).provider("POST", data={}))
    assert raised.value.code == "TWILIO_UNAVAILABLE"
    assert "HTTP 400, Twilio error 10002" in raised.value.message
    assert "Secret token" not in raised.value.message


def test_plivo_v3_signature_and_voice_xml():
    settings = SimpleNamespace(
        phone_public_base_url="https://bankai.example.org",
        plivo_auth_token=SecretStr("test-plivo-token"),
        phone_provider="plivo",
    )
    path = "/api/v1/phone/hooks/123/ask?step=0"
    params = {"CallUUID": "call-id", "Speech": "balance"}
    nonce = "unique-nonce"
    value = settings.phone_public_base_url + path + "." + "".join(k + params[k] for k in sorted(params)) + "." + nonce
    signature = base64.b64encode(hmac.new(b"test-plivo-token", value.encode(), hashlib.sha256).digest()).decode()
    assert phone.verify_plivo(settings, path, params, signature, nonce)
    assert not phone.verify_plivo(settings, path, {**params, "Speech": "transfer"}, signature, nonce)
    assert not phone.verify_plivo(settings, path, params, signature, "")
    intro_path = "/api/v1/phone/hooks/123/intro"
    intro_value = settings.phone_public_base_url + intro_path + "?" + "".join(k + params[k] for k in sorted(params)) + "." + nonce
    intro_signature = base64.b64encode(hmac.new(b"test-plivo-token", intro_value.encode(), hashlib.sha256).digest()).decode()
    assert phone.verify_plivo(settings, intro_path, params, intro_signature, nonce)
    manager = phone.PhoneManager(None, settings)
    call = phone.ActiveCall(phone.uuid4(), phone.uuid4(), phone.uuid4(), "token")
    assert 'GetInput' in manager.intro(call) and 'inputType="dtmf"' in manager.intro(call)
    assert '<Speak>' in manager.ask_prompt(call) and 'inputType="speech"' in manager.ask_prompt(call)
    speech = ET.fromstring(manager.ask_prompt(call)).find("GetInput")
    assert speech is not None
    assert speech.attrib["executionTimeout"] == "25"
    assert speech.attrib["language"] == "en-IN"
    assert "speechModel" not in speech.attrib
    assert speech.attrib["action"].endswith(f"/{call.id}/ask?step=0")
    assert ET.fromstring(manager.ask_prompt(call)).findtext("Redirect") == manager.url(call, "retry")

    recorded = []
    manager.event = lambda _call, kind, **payload: recorded.append((kind, payload))
    call.consented = True
    assert "GetInput" in manager.retry(call)
    assert "GetInput" not in manager.retry(call)
    assert recorded == [("speech_timeout", {"attempt": 1}), ("speech_timeout", {"attempt": 2})]


def test_plivo_provider_request_and_safe_failure(monkeypatch):
    requests = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, **kwargs):
            requests.append((method, url, kwargs))
            return SimpleNamespace(status_code=400, content=b'error', json=lambda: {"message": "secret"})

    monkeypatch.setattr(phone.httpx, "AsyncClient", lambda **_kwargs: Client())
    settings = SimpleNamespace(phone_provider="plivo", plivo_auth_id=SecretStr("id"), plivo_auth_token=SecretStr("token"))
    with pytest.raises(APIError) as raised:
        asyncio.run(phone.PhoneManager(None, settings).provider("POST", data={"to": "+919876543210"}))
    assert raised.value.code == "PLIVO_UNAVAILABLE"
    assert "secret" not in raised.value.message
    assert requests[0][1] == "https://api.plivo.com/v1/Account/id/Call/"
    assert requests[0][2]["json"] == {"to": "+919876543210"}


def test_public_callback_must_be_ready_before_dialing(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url):
            return SimpleNamespace(status_code=404, json=lambda: {"status": "offline"})

    monkeypatch.setattr(phone.httpx, "AsyncClient", lambda **_kwargs: Client())
    manager = phone.PhoneManager(None, SimpleNamespace(
        phone_public_base_url="https://example.org", phone_configured=True,
        phone_allowed_numbers="+919876543210",
    ))
    with pytest.raises(APIError) as raised:
        asyncio.run(manager.create(phone.uuid4(), phone.uuid4(), "test-token",
                                   "+919876543210", "owner"))
    assert raised.value.code == "PHONE_CALLBACK_UNAVAILABLE"
    assert manager.calls == {}
