from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import select

from app.api.chat import owned_conversation
from app.api.deps import DB, Actor
from app.core.errors import APIError
from app.models import VoiceEvent, VoiceSession
from app.schemas import Input

router = APIRouter(prefix="/api/v1/voice", tags=["Browser voice"])


class VoiceStart(Input):
    conversation_id: UUID


class VoiceJoin(Input):
    session_id: UUID
    url: str
    token: str = Field(repr=False)
    expires_at: datetime


class VoiceControl(Input):
    turn_id: UUID | None = None


@router.post("/sessions", response_model=VoiceJoin)
async def create(data: VoiceStart, request: Request, db: DB, customer: Actor):
    owned_conversation(db, customer, data.conversation_id)
    request.app.state.voice_limiter.check(str(customer.id))
    bearer = request.headers.get("authorization", "").partition(" ")[2]
    session, expires, token = await request.app.state.voice.create(
        customer.id, data.conversation_id, bearer
    )
    return VoiceJoin(
        session_id=session.id,
        url=request.app.state.settings.livekit_url,
        token=token,
        expires_at=expires,
    )


def owned(db, customer_id, session_id):
    row = db.scalar(
        select(VoiceSession).where(
            VoiceSession.id == session_id, VoiceSession.customer_id == customer_id
        )
    )
    if row is None:
        raise APIError(404, "NOT_FOUND", "Voice session not found.")
    return row


@router.get("/sessions/{session_id}")
def snapshot(session_id: UUID, request: Request, db: DB, customer: Actor):
    row = owned(db, customer.id, session_id)
    connection = request.app.state.voice.sessions.get(session_id)
    events = list(
        db.scalars(
            select(VoiceEvent)
            .where(VoiceEvent.session_id == row.id)
            .order_by(VoiceEvent.created_at.desc(), VoiceEvent.id.desc())
            .limit(100)
        )
    )
    return {
        "session_id": row.id,
        "status": connection.status if connection else "closed",
        "expires_at": row.expires_at,
        "events": [
            {"id": e.id, "kind": e.kind, "run_id": e.run_id, "metadata": e.payload}
            for e in reversed(events)
        ],
    }


@router.post("/sessions/{session_id}/{action}")
async def control(
    session_id: UUID,
    action: Literal["listen", "send", "interrupt", "close"],
    data: VoiceControl,
    request: Request,
    db: DB,
    customer: Actor,
):
    owned(db, customer.id, session_id)
    manager = request.app.state.voice
    connection = manager.sessions.get(session_id)
    if connection is None:
        if action == "close":
            return {"status": "closed"}
        raise APIError(409, "VOICE_CLOSED", "This voice session has ended. Start a new one.")
    if action in ("listen", "send") and data.turn_id is None:
        raise APIError(422, "VOICE_TURN_REQUIRED", "A voice question ID is required.")
    if action == "listen":
        manager.listen(connection, data.turn_id)
    elif action == "send":
        manager.finish(connection, data.turn_id)
    elif action == "interrupt":
        manager.interrupt(connection)
    else:
        await manager.close(connection, "user_ended")
    return {"status": connection.status}
