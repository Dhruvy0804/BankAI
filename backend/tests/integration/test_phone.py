import base64
import hashlib
import hmac
from time import monotonic, sleep
from urllib.parse import urlencode
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr

from app.models import Conversation, PhoneCall, PhoneEvent
from app.seed.demo_data import seed_owner_demo
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


def signed_plivo(client, settings, call_id, action, request_uuid, call_uuid, **fields):
    path = f"/api/v1/phone/hooks/{call_id}/{action}"
    form = {"RequestUUID": request_uuid, "CallUUID": call_uuid, **fields}
    nonce = "test-nonce"
    value = settings.phone_public_base_url + path + ("." if "?" in path else "?")
    value += "".join(k + v for k, v in sorted(form.items())) + "." + nonce
    signature = base64.b64encode(
        hmac.new(settings.plivo_auth_token.get_secret_value().encode(), value.encode(), hashlib.sha256).digest()
    ).decode()
    return client.post(path, content=urlencode(form), headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Plivo-Signature-V3": signature,
        "X-Plivo-Signature-V3-Nonce": nonce,
    })


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
    async def callback_ready(self):
        return None
    monkeypatch.setattr(PhoneManager, "callback_ready", callback_ready)
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


def test_owner_phone_profile_uses_owner_banking_records(phone):
    settings, factory, client, _cid, headers, _ = phone
    payload = {"demo_customer": "owner", "number": NUMBER, "recipient_agreed": True}
    assert client.post("/api/v1/phone/calls", headers=headers, json=payload).status_code == 503
    with factory() as db, db.begin():
        seed_owner_demo(db, UUID(settings.phone_owner_customer_id))
    created = client.post("/api/v1/phone/calls", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    with factory() as db:
        conversation = db.get(Conversation, created.json()["conversation_id"])
        assert conversation.customer_id == UUID(settings.phone_owner_customer_id)
    assert client.post(f"/api/v1/phone/calls/{created.json()['id']}/end", headers=headers, json={}).status_code == 200


def test_ten_daily_attempts_are_allowed_but_eleventh_is_rejected(phone):
    from datetime import UTC, datetime, timedelta

    settings, factory, client, conversation_id, headers, _sent = phone
    assert client.get("/api/v1/phone/config", headers=headers).json()["max_daily_attempts"] == 10
    with factory() as db, db.begin():
        for _ in range(9):
            db.add(PhoneCall(
                customer_id=UUID(settings.phone_owner_customer_id),
                conversation_id=UUID(conversation_id), demo_customer="asha",
                destination_hint="…3210", status="ended",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            ))
    payload = {"demo_customer": "asha", "number": NUMBER, "recipient_agreed": True}
    tenth = client.post("/api/v1/phone/calls", headers=headers, json=payload)
    assert tenth.status_code == 201
    assert client.post(f"/api/v1/phone/calls/{tenth.json()['id']}/end", headers=headers, json={}).status_code == 200
    eleventh = client.post("/api/v1/phone/calls", headers=headers, json=payload)
    assert eleventh.status_code == 429
    assert "10-call limit" in eleventh.json()["error"]["message"]


def test_plivo_signed_consent_question_and_playback(phone, simulated_models, monkeypatch):  # noqa: F811
    settings, factory, client, _cid, headers, sent = phone
    settings.phone_provider = "plivo"
    settings.plivo_auth_id = SecretStr("TESTPLIVOAUTHID")
    settings.plivo_auth_token = SecretStr("test-only-plivo-token")
    request_uuid, call_uuid = str(uuid4()), str(uuid4())

    async def fake_plivo(self, method, sid="", *, data=None, request_id=False):
        sent.append((method, sid, data, request_id))
        return {"request_uuid": request_uuid} if not sid else {}

    monkeypatch.setattr(PhoneManager, "provider", fake_plivo)
    assert settings.phone_configured
    created = client.post("/api/v1/phone/calls", headers=headers, json={
        "demo_customer": "asha", "number": NUMBER, "recipient_agreed": True,
    })
    assert created.status_code == 201, created.text
    call_id = created.json()["id"]
    assert sent[0][2]["time_limit"] == 300
    assert sent[0][2]["answer_url"].endswith(f"/{call_id}/intro")
    assert client.post(f"/api/v1/phone/hooks/{call_id}/intro", data={"CallUUID": call_uuid}).status_code == 403
    assert "GetInput" in signed_plivo(client, settings, call_id, "intro", request_uuid, call_uuid).text
    assert "GetInput" in signed_plivo(client, settings, call_id, "consent", request_uuid, call_uuid, Digits="1").text
    asked = signed_plivo(client, settings, call_id, "ask?step=0", request_uuid, call_uuid, Speech="Show my demo balance")
    assert asked.status_code == 200 and "<Wait" in asked.text
    deadline = monotonic() + 25
    while monotonic() < deadline and not any(item[2] and item[2].get("aleg_url") for item in sent):
        sleep(0.1)
    assert any(item[2] and item[2].get("aleg_url") for item in sent)
    playback = signed_plivo(client, settings, call_id, "playback", request_uuid, call_uuid)
    assert playback.status_code == 200 and "<Speak>" in playback.text
    retry = signed_plivo(client, settings, call_id, "playback", request_uuid, call_uuid)
    assert retry.status_code == 200 and retry.text == playback.text
    with factory() as db:
        assert db.get(PhoneCall, call_id).provider_sid == call_uuid
        assert db.query(PhoneEvent).filter(PhoneEvent.call_id == call_id, PhoneEvent.kind == "answer_spoken").count() == 1
    assert client.post(f"/api/v1/phone/calls/{call_id}/end", headers=headers, json={}).status_code == 200
    assert any(item[0] == "DELETE" and item[1] == call_uuid for item in sent)


def test_plivo_request_gone_clears_stale_dialing_call(phone, monkeypatch):
    settings, factory, client, _cid, headers, _sent = phone
    settings.phone_provider = "plivo"
    settings.plivo_auth_id = SecretStr("TESTPLIVOAUTHID")
    settings.plivo_auth_token = SecretStr("test-only-plivo-token")
    request_uuid = str(uuid4())

    async def fake_plivo(self, method, sid="", *, data=None, request_id=False):
        if method == "DELETE" and request_id:
            from app.core.errors import APIError
            raise APIError(404, "PLIVO_REQUEST_GONE", "No pending request")
        return {"request_uuid": request_uuid}

    monkeypatch.setattr(PhoneManager, "provider", fake_plivo)
    created = client.post("/api/v1/phone/calls", headers=headers, json={
        "demo_customer": "asha", "number": NUMBER, "recipient_agreed": True,
    })
    assert created.status_code == 201
    call_id = created.json()["id"]
    ended = client.post(f"/api/v1/phone/calls/{call_id}/end", headers=headers, json={})
    assert ended.status_code == 200 and ended.json()["status"] == "error"
    assert client.get(f"/api/v1/phone/calls/{call_id}", headers=headers).json()["status"] == "error"
    with factory() as db:
        assert db.query(PhoneEvent).filter(PhoneEvent.call_id == call_id,
                                           PhoneEvent.kind == "request_unavailable").count() == 1
