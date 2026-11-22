"""Bounded provider calling for an explicitly approved synthetic demo."""

import asyncio
import base64
import hashlib
import hmac
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from uuid import UUID, uuid4
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import func, select, update

from app.chat_schemas import ChatReply
from app.core.errors import APIError
from app.models import PhoneCall, PhoneEvent
from app.services.speech import spoken_answer

TERMINAL = {"completed", "canceled", "busy", "failed", "no-answer", "ended", "error"}
DAILY_CALL_LIMIT = 7
SID = re.compile(r"CA[0-9a-fA-F]{32}\Z")
PLIVO_ID = re.compile(r"[0-9a-fA-F-]{36}\Z")


def twiml(*parts):
    root = ET.Element("Response")
    for tag, attributes, message in parts:
        node = ET.SubElement(root, tag, attributes)
        if message:
            node.text = message
    return ET.tostring(root, encoding="unicode")


def say_and_hangup(message, provider="twilio"):
    return twiml(("Speak" if provider == "plivo" else "Say", {}, message), ("Hangup", {}, ""))


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


def verify_plivo(settings, path, params, signature, nonce):
    """Plivo Voice V3 signs the public URL, sorted POST fields, and a nonce."""
    if not signature or not nonce or len(nonce) > 128:
        return False
    parsed = urlsplit(settings.phone_public_base_url.rstrip("/") + path)
    query = "&".join(f"{key}={value}" for key, value in sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    value = base + "?" + query + ("." if query else "")
    value += "".join(key + params[key] for key in sorted(params)) + "." + nonce
    digest = hmac.new(
        settings.plivo_auth_token.get_secret_value().encode(), value.encode(), hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode()
    return any(hmac.compare_digest(expected, candidate.strip()) for candidate in signature.split(","))


@dataclass
class ActiveCall:
    id: UUID
    customer_id: UUID
    conversation_id: UUID
    bearer: str = field(repr=False)
    sid: str = ""
    request_uuid: str = ""
    pending_message: str = ""
    pending_run_id: UUID | None = None
    pending_message_id: UUID | None = None
    status: str = "dialing"
    consented: bool = False
    turns: int = 0
    speech_timeouts: int = 0
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

    async def callback_ready(self):
        url = self.settings.phone_public_base_url.rstrip("/") + "/ready"
        try:
            async with httpx.AsyncClient(timeout=6) as client:
                response = await client.get(url)
            ready = response.status_code == 200 and response.json().get("status") == "ready"
        except (httpx.HTTPError, ValueError, AttributeError):
            ready = False
        if not ready:
            raise APIError(503, "PHONE_CALLBACK_UNAVAILABLE",
                           "The public phone callback address is offline. Start the HTTPS tunnel and update PHONE_PUBLIC_BASE_URL before calling.")

    async def provider(self, method, sid="", *, data=None, request_id=False):
        if self.settings.phone_provider == "plivo":
            account = self.settings.plivo_auth_id.get_secret_value()
            token = self.settings.plivo_auth_token.get_secret_value()
            resource = "Request" if request_id else "Call"
            url = f"https://api.plivo.com/v1/Account/{account}/{resource}/{sid + '/' if sid else ''}"
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.request(method, url, auth=(account, token), json=data)
            if response.status_code >= 400:
                if method == "DELETE" and request_id and response.status_code == 404:
                    raise APIError(404, "PLIVO_REQUEST_GONE", "Plivo has no pending request to cancel.")
                raise APIError(503, "PLIVO_UNAVAILABLE", f"Plivo rejected the phone request (HTTP {response.status_code}).")
            return response.json() if response.content else {}
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
        await self.callback_ready()
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
                if active or daily >= DAILY_CALL_LIMIT:
                    raise APIError(429, "PHONE_LIMIT", f"A test call is active or today's {DAILY_CALL_LIMIT}-call limit is reached.")
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
                if self.settings.phone_provider == "plivo":
                    response = await self.provider("POST", data={
                        "from": self.settings.phone_caller_number,
                        "to": number,
                        "answer_url": self.url(call, "intro"),
                        "answer_method": "POST",
                        "hangup_url": self.url(call, "status"),
                        "hangup_method": "POST",
                        "time_limit": self.settings.phone_max_duration_seconds,
                    })
                    request_uuid = response.get("request_uuid", "")
                    if not PLIVO_ID.fullmatch(request_uuid):
                        raise APIError(503, "PLIVO_RESPONSE", "Plivo did not return a valid request ID.")
                    if call.request_uuid and call.request_uuid != request_uuid:
                        raise APIError(503, "PLIVO_RESPONSE", "Plivo call identity changed.")
                    call.request_uuid = request_uuid
                else:
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

    def bind(self, call_id, sid, request_uuid=""):
        call = self.calls.get(call_id)
        pattern = PLIVO_ID if self.settings.phone_provider == "plivo" else SID
        if call is None or call.closed or not pattern.fullmatch(sid):
            raise APIError(404, "PHONE_NOT_FOUND", "Phone call unavailable.")
        if self.settings.phone_provider == "plivo":
            if not PLIVO_ID.fullmatch(request_uuid) or (call.request_uuid and call.request_uuid != request_uuid):
                raise APIError(403, "PHONE_IDENTITY", "Phone call identity mismatch.")
            call.request_uuid = request_uuid
        if call.sid and call.sid != sid:
            raise APIError(403, "PHONE_IDENTITY", "Phone call identity mismatch.")
        if not call.sid:
            call.sid = sid
        return call

    def ask_prompt(self, call, message="Please ask your demo banking question."):
        if call.turns >= 3:
            return say_and_hangup(message + " The three-question demo is complete. Goodbye.", self.settings.phone_provider)
        root = ET.Element("Response")
        if self.settings.phone_provider == "plivo":
            gather = ET.SubElement(root, "GetInput", {
                "inputType": "speech", "action": self.url(call, "ask", call.turns),
                "method": "POST", "executionTimeout": "25",
                "language": "en-IN", "log": "false",
            })
        else:
            gather = ET.SubElement(root, "Gather", {
                "input": "speech", "action": self.url(call, "ask", call.turns),
                "method": "POST", "timeout": "8", "speechTimeout": "2",
            })
        tag = "Speak" if self.settings.phone_provider == "plivo" else "Say"
        ET.SubElement(gather, tag).text = message
        if self.settings.phone_provider == "plivo":
            ET.SubElement(root, "Redirect", {"method": "POST"}).text = self.url(call, "retry")
        else:
            ET.SubElement(root, tag).text = "No question was heard. Goodbye."
            ET.SubElement(root, "Hangup")
        return ET.tostring(root, encoding="unicode")

    def retry(self, call):
        if not call.consented:
            return say_and_hangup("Consent is required. Goodbye.", self.settings.phone_provider)
        call.speech_timeouts += 1
        self.event(call, "speech_timeout", attempt=call.speech_timeouts)
        if call.speech_timeouts >= 2:
            return say_and_hangup("I still could not hear a question. Please try again later. Goodbye.", self.settings.phone_provider)
        return self.ask_prompt(call, "I did not catch that. Please ask your demo banking question again.")

    def intro(self, call):
        if call.consented:
            return self.ask_prompt(call)
        root = ET.Element("Response")
        if self.settings.phone_provider == "plivo":
            gather = ET.SubElement(root, "GetInput", {
                "inputType": "dtmf", "numDigits": "1", "executionTimeout": "15",
                "action": self.url(call, "consent"), "method": "POST", "log": "false",
            })
        else:
            gather = ET.SubElement(root, "Gather", {
                "input": "dtmf", "numDigits": "1", "timeout": "8",
                "action": self.url(call, "consent"), "method": "POST",
            })
        ET.SubElement(gather, "Speak" if self.settings.phone_provider == "plivo" else "Say").text = (
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
            return say_and_hangup("The demonstration has ended. Goodbye.", self.settings.phone_provider)
        if not call.consented:
            call.consented = True
            call.status = "ready"
            self.event(call, "consent_accepted")
        return self.ask_prompt(call)

    def ask(self, call, step, speech):
        if not call.consented:
            return say_and_hangup("Consent is required. Goodbye.", self.settings.phone_provider)
        if step != call.turns or call.status == "processing":
            if call.status == "processing":
                tag = "Wait" if self.settings.phone_provider == "plivo" else "Pause"
                return twiml(*[(tag, {"length": "60"}, "")] * 3)
            return say_and_hangup("This question has already been received. Goodbye.", self.settings.phone_provider)
        speech = speech.strip()
        if not speech or len(speech) > 2000:
            return self.ask_prompt(call, "I could not understand that question. Please try again.")
        call.speech_timeouts = 0
        call.turns += 1
        call.status = "processing"
        message_id = uuid4()
        self.event(call, "question_received", message_id=str(message_id), characters=len(speech))
        call.task = asyncio.create_task(self.answer(call, message_id, speech))
        tag = "Speak" if self.settings.phone_provider == "plivo" else "Say"
        wait = "Wait" if self.settings.phone_provider == "plivo" else "Pause"
        return twiml((tag, {}, "Please wait while BankAI checks the demo information."),
                     *[(wait, {"length": "60"}, "")] * 3)

    def playback(self, call):
        if not call.consented or not call.pending_message:
            return say_and_hangup("The answer is unavailable. Goodbye.", self.settings.phone_provider)
        if call.status == "processing":
            return twiml(("Wait", {"length": "30"}, ""))
        message = call.pending_message
        call.status = "ready" if call.turns < 3 else "speaking"
        if call.pending_message_id:
            self.event(call, "answer_spoken", run_id=call.pending_run_id, message_id=str(call.pending_message_id))
            call.pending_run_id = call.pending_message_id = None
        return self.ask_prompt(call, message)

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
            if self.settings.phone_provider == "plivo":
                call.pending_message = message
                call.pending_run_id = run_id
                call.pending_message_id = message_id
                call.status = "speaking"
                await self.provider("POST", call.sid, data={
                    "legs": "aleg", "aleg_url": self.url(call, "playback"), "aleg_method": "POST",
                })
            else:
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
        request_gone = False
        try:
            if call.status not in TERMINAL:
                if self.settings.phone_provider == "plivo":
                    if call.sid:
                        await self.provider("DELETE", call.sid)
                    elif call.request_uuid:
                        await self.provider("DELETE", call.request_uuid, request_id=True)
                elif call.sid:
                    await self.provider("POST", call.sid, data={"Status": "completed"})
        except APIError as error:
            if error.code != "PLIVO_REQUEST_GONE":
                self.event(call, "hangup_failed")
                raise
            request_gone = True
        except Exception:
            self.event(call, "hangup_failed")
            raise
        call.closed = True
        call.bearer = ""
        if call.timer and call.timer is not asyncio.current_task():
            call.timer.cancel()
        call.status = "error" if request_gone else "ended"
        self.event(call, "request_unavailable" if request_gone else "call_ended", reason=reason)
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
