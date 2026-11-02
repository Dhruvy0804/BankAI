import asyncio
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
        twilio_account_sid=SecretStr("AC" + "a" * 32),
        twilio_auth_token=SecretStr("test-token"),
    )
    with pytest.raises(APIError) as raised:
        asyncio.run(phone.PhoneManager(None, settings).provider("POST", data={}))
    assert raised.value.code == "TWILIO_UNAVAILABLE"
    assert "HTTP 400, Twilio error 10002" in raised.value.message
    assert "Secret token" not in raised.value.message
