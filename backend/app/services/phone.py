"""Bounded Twilio trial calling for an explicitly approved synthetic demo."""

import asyncio
import base64
import hashlib
import hmac
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import func, select, update

from app.chat_schemas import ChatReply
from app.core.errors import APIError
from app.models import PhoneCall, PhoneEvent
from app.services.speech import spoken_answer

TERMINAL = {"completed", "canceled", "busy", "failed", "no-answer", "ended", "error"}
SID = re.compile(r"CA[0-9a-fA-F]{32}\Z")


def twiml(*parts):
    root = ET.Element("Response")
    for tag, attributes, message in parts:
        node = ET.SubElement(root, tag, attributes)
        if message:
            node.text = message
    return ET.tostring(root, encoding="unicode")


def say_and_hangup(message):
    return twiml(("Say", {}, message), ("Hangup", {}, ""))


def verify_twilio(settings, path, params, signature):
    """Twilio's form webhook signature over the configured public URL and every POST field."""
    if not signature or len(params) != len(set(params)):
        return False
    value = settings.phone_public_base_url.rstrip("/") + path
    value += "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(
        settings.twilio_auth_token.get_secret_value().encode(), value.encode(), hashlib.sha1
    ).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


@dataclass
class ActiveCall:
    id: UUID
    customer_id: UUID
    conversation_id: UUID
    bearer: str = field(repr=False)
    sid: str = ""
    status: str = "dialing"
    consented: bool = False
    turns: int = 0
    task: asyncio.Task | None = None
    timer: asyncio.Task | None = None
    closed: bool = False


class PhoneManager:
    """One local API process handles at most one outbound call; call evidence is durable."""

    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings
        self.calls: dict[UUID, ActiveCall] = {}
        self.lock = asyncio.Lock()

    def url(self, call, action, step=None):
        path = f"/api/v1/phone/hooks/{call.id}/{action}"
        return self.settings.phone_public_base_url.rstrip("/") + path + (
            f"?step={step}" if step is not None else ""
        )

    def event(self, call, kind, *, run_id=None, **payload):
        with self.factory() as db, db.begin():
            db.add(PhoneEvent(call_id=call.id, kind=kind, run_id=run_id, payload=payload))
            db.execute(
                update(PhoneCall)
                .where(PhoneCall.id == call.id)
                .values(status=call.status, provider_sid=call.sid or None)
            )

    async def provider(self, method, sid="", *, data=None):
        account = self.settings.twilio_account_sid.get_secret_value()
        token = self.settings.twilio_auth_token.get_secret_value()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account}/Calls"
        if sid:
            url += f"/{sid}"
        url += ".json"
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.request(method, url, auth=(account, token), data=data)
        if response.status_code >= 400:
            try:
                code = response.json().get("code")
            except (ValueError, AttributeError):
                code = None
            detail = f", Twilio error {code}" if type(code) is int else ""
            raise APIError(503, "TWILIO_UNAVAILABLE", f"Twilio rejected the phone request (HTTP {response.status_code}{detail}).")
        return response.json()

    async def create(self, customer_id, conversation_id, bearer, number, demo_customer):
        if not self.settings.phone_configured:
            raise APIError(503, "PHONE_NOT_CONFIGURED", "Phone testing is not configured.")
        allowed = {n.strip() for n in self.settings.phone_allowed_numbers.split(",")}
        if number not in allowed:
            raise APIError(403, "PHONE_NOT_ALLOWED", "This test number is not approved.")
        async with self.lock:
            if self.calls:
                raise APIError(429, "PHONE_LIMIT", "A test call is already active.")
            now = datetime.now(UTC)
            with self.factory() as db, db.begin():
                active = db.scalar(
                    select(func.count()).select_from(PhoneCall).where(
                        PhoneCall.status.not_in(TERMINAL), PhoneCall.expires_at > now
                    )
                )
                daily = db.scalar(
                    select(func.count()).select_from(PhoneCall).where(
                        PhoneCall.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)
                    )
                )
                if active or daily >= 2:
                    raise APIError(429, "PHONE_LIMIT", "A test call is active or today's two-call limit is reached.")
                call = ActiveCall(uuid4(), customer_id, conversation_id, bearer)
                db.add(
                    PhoneCall(
                        id=call.id,
                        customer_id=customer_id,
                        conversation_id=conversation_id,
                        demo_customer=demo_customer,
                        destination_hint="…" + number[-4:],
                        status="dialing",
                        expires_at=now + timedelta(seconds=self.settings.phone_max_duration_seconds),
                    )
                )
            self.calls[call.id] = call
            try:
                response = await self.provider(
                    "POST",
                    data={
                        "To": number,
                        "From": self.settings.phone_caller_number,
                        "Url": self.url(call, "intro"),
                        "Method": "POST",
                        "StatusCallback": self.url(call, "status"),
                        "StatusCallbackMethod": "POST",
                        "StatusCallbackEvent": "completed",
                        "TimeLimit": str(self.settings.phone_max_duration_seconds),
                        "Record": "false",
                    },
                )
                if not SID.fullmatch(response.get("sid", "")):
                    raise APIError(503, "TWILIO_RESPONSE", "Twilio did not return a valid call ID.")
                if call.sid and call.sid != response["sid"]:
                    raise APIError(503, "TWILIO_RESPONSE", "Twilio call identity changed.")
                call.sid = response["sid"]
                self.event(call, "dial_requested", duration_limit_seconds=self.settings.phone_max_duration_seconds)
                call.timer = asyncio.create_task(self.expire(call))
                return call
            except Exception:
                call.status = "error"
                call.closed = True
                call.bearer = ""
                self.event(call, "dial_failed")
                self.calls.pop(call.id, None)
                raise

    def bind(self, call_id, sid):
        call = self.calls.get(call_id)
        if call is None or call.closed or not SID.fullmatch(sid):
            raise APIError(404, "PHONE_NOT_FOUND", "Phone call unavailable.")
        if call.sid and call.sid != sid:
            raise APIError(403, "PHONE_IDENTITY", "Phone call identity mismatch.")
        if not call.sid:
            call.sid = sid
        return call

    def ask_prompt(self, call, message="Please ask your demo banking question."):
        if call.turns >= 3:
            return say_and_hangup(message + " The three-question demo is complete. Goodbye.")
        root = ET.Element("Response")
        gather = ET.SubElement(
            root,
            "Gather",
            {"input": "speech", "action": self.url(call, "ask", call.turns), "method": "POST", "timeout": "8", "speechTimeout": "2"},
        )
        ET.SubElement(gather, "Say").text = message
        ET.SubElement(root, "Say").text = "No question was heard. Goodbye."
        ET.SubElement(root, "Hangup")
        return ET.tostring(root, encoding="unicode")

    def intro(self, call):
        if call.consented:
            return self.ask_prompt(call)
        root = ET.Element("Response")
        gather = ET.SubElement(
            root,
            "Gather",
            {"input": "dtmf", "numDigits": "1", "timeout": "8", "action": self.url(call, "consent"), "method": "POST"},
        )
        ET.SubElement(gather, "Say").text = (
            "Hello. This is an educational BankAI demonstration using fictional accounts. "
            "Your questions and answers will be saved for the demonstration, but call audio is not recorded. "
            "Press 1 if you agree to continue. Otherwise hang up."
        )
        ET.SubElement(root, "Hangup")
        return ET.tostring(root, encoding="unicode")

    def consent(self, call, digit):
        if call.consented:
            return self.ask_prompt(call)
        if digit != "1":
            call.status = "ended"
            call.closed = True
            call.bearer = ""
            if call.timer:
                call.timer.cancel()
            self.event(call, "consent_declined")
            self.calls.pop(call.id, None)
            return say_and_hangup("The demonstration has ended. Goodbye.")
        if not call.consented:
            call.consented = True
            call.status = "ready"
            self.event(call, "consent_accepted")
        return self.ask_prompt(call)

    def ask(self, call, step, speech):
        if not call.consented:
            return say_and_hangup("Consent is required. Goodbye.")
        if step != call.turns or call.status == "processing":
            if call.status == "processing":
                return twiml(*[("Pause", {"length": "60"}, "")] * 3)
            return say_and_hangup("This question has already been received. Goodbye.")
        speech = speech.strip()
        if not speech or len(speech) > 2000:
            return self.ask_prompt(call, "I could not understand that question. Please try again.")
        call.turns += 1
        call.status = "processing"
        message_id = uuid4()
        self.event(call, "question_received", message_id=str(message_id), characters=len(speech))
        call.task = asyncio.create_task(self.answer(call, message_id, speech))
        return twiml(
            ("Say", {}, "Please wait while BankAI checks the demo information."),
            ("Pause", {"length": "60"}, ""),
            ("Pause", {"length": "60"}, ""),
            ("Pause", {"length": "60"}, ""),
        )

    async def answer(self, call, message_id, speech):
        run_id = None
        try:
            async with httpx.AsyncClient(timeout=190) as client:
                response = await client.post(
                    self.settings.agent_base_url + "/api/v1/chat",
                    headers={"Authorization": "Bearer " + call.bearer},
                    json={"conversation_id": str(call.conversation_id), "message_id": str(message_id), "message": speech},
                )
            if response.status_code != 200:
                raise APIError(503, "PHONE_AGENT_UNAVAILABLE", "The banking answer is unavailable.")
            reply = ChatReply.model_validate(response.json())
            run_id = reply.run_id
            message = spoken_answer(reply)
            self.event(call, "banking_answer", run_id=run_id, message_id=str(message_id))
        except Exception:  # noqa: BLE001 -- provider and agent errors never enter speech or logs
            message = "BankAI could not answer this question. Check the saved conversation or try again."
            self.event(call, "answer_failed", message_id=str(message_id))
        if call.closed:
            return
        try:
            following = self.ask_prompt(call, message)
            await self.provider("POST", call.sid, data={"Twiml": following})
            call.status = "ready" if call.turns < 3 else "speaking"
            self.event(call, "answer_spoken", run_id=run_id, message_id=str(message_id))
        except Exception:  # noqa: BLE001 -- Twilio failures are recorded without credentials or transcript
            call.status = "error"
            self.event(call, "playback_failed", run_id=run_id)

    async def end(self, call, reason="owner_ended"):
        if call.closed:
            return
        try:
            if call.sid and call.status not in TERMINAL:
                await self.provider("POST", call.sid, data={"Status": "completed"})
        except Exception:
            self.event(call, "hangup_failed")
            raise
        call.closed = True
        call.bearer = ""
        if call.timer and call.timer is not asyncio.current_task():
            call.timer.cancel()
        call.status = "ended"
        self.event(call, "call_ended", reason=reason)
        self.calls.pop(call.id, None)

    async def expire(self, call):
        await asyncio.sleep(self.settings.phone_max_duration_seconds)
        if not call.closed:
            try:
                await self.end(call, "time_limit")
            except Exception:  # noqa: BLE001 -- Twilio TimeLimit is the second enforcement boundary
                self.event(call, "time_limit_hangup_failed")

    async def shutdown(self):
        await asyncio.gather(*(self.end(c, "server_shutdown") for c in list(self.calls.values())), return_exceptions=True)
