"""Owner-only outbound demo call and signed provider callbacks."""

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from app.api.deps import DB, Actor
from app.core.errors import APIError
from app.core.security import issue_token
from app.models import Account, ChatTurn, Conversation, Customer, PhoneCall, PhoneEvent
from app.schemas import Input
from app.seed.demo_data import demo_id
from app.services.phone import DAILY_CALL_LIMIT, TERMINAL, verify_plivo, verify_twilio

router = APIRouter(prefix="/api/v1/phone", tags=["Phone test"])


class PhoneStart(Input):
    demo_customer: Literal["owner", "asha", "ravi", "mira"]
    number: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    recipient_agreed: bool


def owner(request, customer):
    settings = request.app.state.settings
    if not settings.phone_configured:
        raise APIError(503, "PHONE_NOT_CONFIGURED", "Phone testing is not configured.")
    if str(customer.id) != settings.phone_owner_customer_id or customer.email.endswith("@bankai.example"):
        raise APIError(403, "PHONE_OWNER_ONLY", "Only the configured project owner can test calls.")


def own_call(db, customer, call_id):
    row = db.scalar(select(PhoneCall).where(PhoneCall.id == call_id, PhoneCall.customer_id == customer.id))
    if row is None:
        raise APIError(404, "PHONE_NOT_FOUND", "Phone call not found.")
    return row


def output(row):
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "demo_customer": row.demo_customer,
        "destination_hint": row.destination_hint,
        "status": "expired" if row.status not in TERMINAL and row.expires_at <= datetime.now(UTC) else row.status,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
    }


@router.get("/config")
def config(request: Request, customer: Actor):
    owner(request, customer)
    return {"allowed_numbers": [n.strip() for n in request.app.state.settings.phone_allowed_numbers.split(",") if n.strip()], "max_duration_seconds": request.app.state.settings.phone_max_duration_seconds, "max_daily_attempts": DAILY_CALL_LIMIT, "provider": request.app.state.settings.phone_provider}


@router.post("/calls", status_code=201)
async def create(data: PhoneStart, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    if not data.recipient_agreed:
        raise APIError(422, "CONSENT_REQUIRED", "Confirm the recipient agreed before dialing.")
    if data.demo_customer == "owner":
        demo_customer_id = customer.id
    else:
        demo_index = {"asha": 1, "ravi": 2, "mira": 3}[data.demo_customer]
        demo_customer_id = demo_id(f"customer-{demo_index}")
    demo = db.get(Customer, demo_customer_id)
    if demo is None or not demo.is_active:
        raise APIError(503, "DEMO_ACCOUNT_MISSING", "The selected fictional account is unavailable.")
    if data.demo_customer == "owner" and db.scalar(select(Account.id).where(Account.customer_id == customer.id)) is None:
        raise APIError(503, "DEMO_ACCOUNT_MISSING", "Your fictional owner account is unavailable.")
    conversation = Conversation(customer_id=demo_customer_id, title="Phone demonstration")
    db.add(conversation)
    db.flush()
    db.commit()
    bearer = issue_token(demo_customer_id, request.app.state.settings)
    call = await request.app.state.phone.create(customer.id, conversation.id, bearer, data.number, data.demo_customer)
    row = db.get(PhoneCall, call.id)
    db.refresh(row)
    return output(row)


@router.get("/calls")
def calls(request: Request, db: DB, customer: Actor):
    owner(request, customer)
    rows = db.scalars(select(PhoneCall).where(PhoneCall.customer_id == customer.id).order_by(PhoneCall.created_at.desc()).limit(20)).all()
    return [output(row) for row in rows]


@router.get("/calls/{call_id}")
def snapshot(call_id: UUID, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    row = own_call(db, customer, call_id)
    events = db.scalars(select(PhoneEvent).where(PhoneEvent.call_id == row.id).order_by(PhoneEvent.created_at, PhoneEvent.id).limit(100)).all()
    turns = db.scalars(select(ChatTurn).where(ChatTurn.conversation_id == row.conversation_id).order_by(ChatTurn.position).limit(3)).all()
    return {**output(row), "events": [{"kind": e.kind, "run_id": e.run_id, "metadata": e.payload} for e in events], "turns": [{"question": t.user_text, "answer": t.response["answer"], "status": t.response["status"], "run_id": t.response["run_id"]} for t in turns]}


@router.post("/calls/{call_id}/end")
async def end(call_id: UUID, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    row = own_call(db, customer, call_id)
    call = request.app.state.phone.calls.get(call_id)
    if call:
        await request.app.state.phone.end(call)
    elif row.status not in TERMINAL:
        if not row.provider_sid:
            raise APIError(409, "PHONE_SESSION_LOST", "Call control is unavailable after a restart.")
        if request.app.state.settings.phone_provider == "plivo":
            await request.app.state.phone.provider("DELETE", row.provider_sid)
        else:
            await request.app.state.phone.provider("POST", row.provider_sid, data={"Status": "completed"})
        row.status = "ended"
        db.add(PhoneEvent(call_id=row.id, kind="call_ended", payload={"reason": "owner_ended_after_restart"}))
    return {"status": call.status if call else "ended"}


@router.post("/hooks/{call_id}/{action}", include_in_schema=False)
async def webhook(call_id: UUID, action: str, request: Request):
    settings = request.app.state.settings
    if not settings.phone_configured:
        raise APIError(404, "PHONE_NOT_FOUND", "Phone call unavailable.")
    raw = await request.body()
    if len(raw) > 16384 or not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        raise APIError(400, "PHONE_WEBHOOK_INPUT", "Invalid provider callback.")
    try:
        pairs = parse_qsl(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True)
    except (UnicodeError, ValueError) as exc:
        raise APIError(400, "PHONE_WEBHOOK_INPUT", "Invalid provider callback.") from exc
    params = dict(pairs)
    if len(params) != len(pairs):
        raise APIError(403, "PHONE_WEBHOOK_SIGNATURE", "Invalid provider callback signature.")
    path = request.url.path + ("?" + request.url.query if request.url.query else "")
    if settings.phone_provider == "plivo":
        valid = verify_plivo(
            settings, path, params,
            request.headers.get("x-plivo-signature-v3", ""),
            request.headers.get("x-plivo-signature-v3-nonce", ""),
        )
    else:
        valid = verify_twilio(settings, path, params, request.headers.get("x-twilio-signature", ""))
    if not valid:
        raise APIError(403, "PHONE_WEBHOOK_SIGNATURE", "Invalid provider callback signature.")
    if settings.phone_provider == "twilio" and params.get("AccountSid") != settings.twilio_account_sid.get_secret_value():
        raise APIError(403, "PHONE_WEBHOOK_ACCOUNT", "Provider account mismatch.")
    manager = request.app.state.phone
    call = manager.calls.get(call_id)
    if call is None:
        return Response(content="<Response><Hangup/></Response>", media_type="application/xml")
    call = manager.bind(
        call_id,
        params.get("CallUUID", "") if settings.phone_provider == "plivo" else params.get("CallSid", ""),
        params.get("RequestUUID", "") if settings.phone_provider == "plivo" else "",
    )
    with manager.factory() as db:
        row = db.get(PhoneCall, call_id)
        expired = row is None or row.expires_at <= datetime.now(UTC)
    if expired:
        await manager.end(call, "time_limit")
        return Response(content="<Response><Hangup/></Response>", media_type="application/xml")
    if action == "status":
        state = params.get("CallStatus", "")
        if state in TERMINAL:
            call.closed, call.status, call.bearer = True, state, ""
            if call.timer:
                call.timer.cancel()
            manager.event(call, "provider_finished", provider_status=state)
            manager.calls.pop(call.id, None)
        return Response(status_code=204)
    if action == "intro":
        xml = manager.intro(call)
    elif action == "consent":
        xml = manager.consent(call, params.get("Digits", ""))
    elif action == "retry" and settings.phone_provider == "plivo":
        xml = manager.retry(call)
    elif action == "ask":
        try:
            step = int(request.query_params.get("step", "-1"))
        except ValueError as exc:
            raise APIError(400, "PHONE_TURN", "Invalid phone question.") from exc
        xml = manager.ask(call, step, params.get("Speech", "") if settings.phone_provider == "plivo" else params.get("SpeechResult", ""))
    elif action == "playback" and settings.phone_provider == "plivo":
        xml = manager.playback(call)
    else:
        raise APIError(404, "PHONE_WEBHOOK_ACTION", "Unknown phone callback.")
    return Response(content=xml, media_type="application/xml")
