import base64
import hashlib
import hmac
from time import monotonic, sleep
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.models import PhoneCall, PhoneEvent
from app.services.phone import PhoneManager
from tests.integration.test_agents import runtime, simulated_models  # noqa: F401

pytestmark = pytest.mark.integration
ACCOUNT = "AC" + "a" * 32
CALL = "CA" + "b" * 32
NUMBER = "+919876543210"


def signed(client, settings, call_id, action, **fields):
    path = f"/api/v1/phone/hooks/{call_id}/{action}"
    form = {"AccountSid": ACCOUNT, "CallSid": CALL, **fields}
    value = settings.phone_public_base_url + path + "".join(k + v for k, v in sorted(form.items()))
    signature = base64.b64encode(
        hmac.new(settings.twilio_auth_token.get_secret_value().encode(), value.encode(), hashlib.sha1).digest()
    ).decode()
    return client.post(path, content=urlencode(form), headers={"Content-Type": "application/x-www-form-urlencoded", "X-Twilio-Signature": signature})


@pytest.fixture
def phone(runtime, monkeypatch):  # noqa: F811
    settings, factory, client, _, _ = runtime
    password = "A-unique-owner-password-123"
    email = f"owner-{uuid4().hex}@example.org"
    registered = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Project Owner"})
    assert registered.status_code == 201, registered.text
    owner_id = registered.json()["id"]
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    settings.phone_enabled = True
    settings.phone_owner_customer_id = owner_id
    settings.phone_allowed_numbers = NUMBER
    settings.phone_caller_number = "+12025550123"
    settings.phone_public_base_url = "https://bankai-phone.example.org"
    settings.twilio_account_sid = SecretStr(ACCOUNT)
    settings.twilio_auth_token = SecretStr("test-only-twilio-auth-token")
    assert settings.phone_configured
    sent = []

    async def fake_provider(self, method, sid="", *, data=None):
        sent.append((method, sid, data))
        return {"sid": CALL}

    monkeypatch.setattr(PhoneManager, "provider", fake_provider)
    owner = client.post("/api/v1/chat/conversations", headers={"Authorization": "Bearer " + token}).json()
    headers = {"Authorization": "Bearer " + token}
    yield settings, factory, client, owner["id"], headers, sent


def test_owner_consent_signed_callbacks_and_agent_answer(phone, simulated_models):  # noqa: F811
    settings, factory, client, _cid, headers, sent = phone
    assert client.get("/api/v1/phone/config").status_code == 403
    assert client.post("/api/v1/phone/calls", headers=headers, json={"demo_customer": "asha", "number": NUMBER, "recipient_agreed": False}).status_code == 422
    assert client.post("/api/v1/phone/calls", headers=headers, json={"demo_customer": "asha", "number": "+919876543211", "recipient_agreed": True}).status_code == 403
    created = client.post("/api/v1/phone/calls", headers=headers, json={"demo_customer": "asha", "number": NUMBER, "recipient_agreed": True})
    assert created.status_code == 201, created.text
    call_id = created.json()["id"]
    assert created.json()["destination_hint"] == "…3210"
    assert sent[0][2]["Record"] == "false"
    assert sent[0][2]["TimeLimit"] == "300"
    assert client.post(f"/api/v1/phone/hooks/{call_id}/intro", data={"CallSid": CALL}).status_code == 403
    assert "Press 1" in signed(client, settings, call_id, "intro").text
    assert "Consent is required" in signed(client, settings, call_id, "ask", SpeechResult="Show accounts").text
    assert "Gather" in signed(client, settings, call_id, "consent", Digits="1").text
    assert "Pause" in signed(client, settings, call_id, "ask?step=0", SpeechResult="Show accounts, calculate an EMI, and summarize").text
    deadline = monotonic() + 25
    while monotonic() < deadline and not any(
        event["kind"] == "answer_spoken"
        for event in client.get(f"/api/v1/phone/calls/{call_id}", headers=headers).json()["events"]
    ):
        sleep(0.1)
    assert any(item[2] and "Twiml" in item[2] for item in sent)
    with factory() as db:
        row = db.get(PhoneCall, call_id)
        assert row.provider_sid == CALL
        kinds = {event.kind for event in db.query(PhoneEvent).filter(PhoneEvent.call_id == call_id)}
        assert {"consent_accepted", "question_received", "banking_answer", "answer_spoken"} <= kinds
    answer = client.get(f"/api/v1/phone/calls/{call_id}", headers=headers).json()
    assert len(answer["turns"]) == 1
    assert answer["turns"][0]["question"].startswith("Show accounts")
    assert client.get(f"/api/v1/chat/conversations/{answer['conversation_id']}", headers=headers).status_code == 404
    assert client.post(f"/api/v1/phone/calls/{call_id}/end", headers=headers, json={}).status_code == 200


def test_webhook_identity_and_duplicate_question(phone):
    settings, _, client, _cid, headers, _ = phone
    created = client.post("/api/v1/phone/calls", headers=headers, json={"demo_customer": "asha", "number": NUMBER, "recipient_agreed": True}).json()
    call_id = created["id"]
    assert signed(client, settings, call_id, "consent", Digits="1").status_code == 200
    wrong = signed(client, settings, call_id, "intro", CallSid="CA" + "c" * 32)
    assert wrong.status_code == 403
    first = signed(client, settings, call_id, "ask?step=0", SpeechResult="How much is my EMI?")
    duplicate = signed(client, settings, call_id, "ask?step=0", SpeechResult="How much is my EMI?")
    assert first.status_code == duplicate.status_code == 200
    assert "Pause" in duplicate.text
    assert client.post(f"/api/v1/phone/calls/{call_id}/end", headers=headers, json={}).status_code == 200


def test_declined_consent_never_starts_banking(phone):
    settings, factory, client, _cid, headers, _ = phone
    created = client.post("/api/v1/phone/calls", headers=headers, json={"demo_customer": "asha", "number": NUMBER, "recipient_agreed": True}).json()
    call_id = created["id"]
    assert "Hangup" in signed(client, settings, call_id, "consent", Digits="2").text
    assert "Hangup" in signed(client, settings, call_id, "ask?step=0", SpeechResult="Show my balance").text
    with factory() as db:
        assert db.get(PhoneCall, call_id).status == "ended"
    assert client.get(f"/api/v1/phone/calls/{call_id}", headers=headers).json()["turns"] == []
