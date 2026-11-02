import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID, uuid4

import httpx
from aiohttp import ClientTimeout
from livekit import api, rtc
from sqlalchemy import update

from app.chat_schemas import ChatReply
from app.core.errors import APIError
from app.models import VoiceEvent, VoiceSession
from app.services.speech import MAX_INPUT_BYTES, SAMPLE_RATE, spoken_answer, synthesize, transcribe


@dataclass
class Connection:
    id: UUID
    customer_id: UUID
    conversation_id: UUID
    bearer: str = field(repr=False)
    room: object = None
    source: object = None
    status: str = "connecting"
    buffer: bytearray = field(default_factory=bytearray, repr=False)
    turn_id: UUID | None = None
    seen: set = field(default_factory=set)
    task: object = None
    readers: set = field(default_factory=set)
    timer: object = None
    joined: bool = False
    closed: bool = False
    interrupted: bool = False

    @property
    def room_name(self):
        return "bankai-voice-" + str(self.id)

    @property
    def identity(self):
        return "browser-" + str(self.id)


def room_token(settings, session, *, worker=False):
    return (
        api.AccessToken(
            settings.livekit_api_key.get_secret_value(),
            settings.livekit_api_secret.get_secret_value(),
        )
        .with_identity("worker-" + str(session.id) if worker else session.identity)
        .with_ttl(timedelta(minutes=5))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=session.room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=False,
                can_update_own_metadata=False,
                can_publish_sources=["microphone"],
            )
        )
        .to_jwt()
    )


class VoiceManager:
    """Single API process owns at most two ephemeral media connections; evidence persists in DB."""

    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings
        self.sessions = {}
        self.lock = asyncio.Lock()

    def event(self, session, kind, *, run_id=None, **payload):
        with self.factory() as db, db.begin():
            db.add(VoiceEvent(session_id=session.id, kind=kind, run_id=run_id, payload=payload))
            db.execute(
                update(VoiceSession)
                .where(VoiceSession.id == session.id)
                .values(status=session.status)
            )

    async def start(self):
        # No media connection survives an API restart; never silently resume a recording.
        with self.factory() as db, db.begin():
            db.execute(
                update(VoiceSession).where(VoiceSession.status != "closed").values(status="closed")
            )

    async def shutdown(self):
        await asyncio.gather(
            *(self.close(s, "server_shutdown") for s in list(self.sessions.values())),
            return_exceptions=True,
        )

    async def create(self, customer_id, conversation_id, bearer):
        if not self.settings.voice_configured:
            raise APIError(
                503,
                "VOICE_NOT_CONFIGURED",
                "Browser voice is not configured. Text chat remains available.",
            )
        async with self.lock:
            if len(self.sessions) >= 2 or any(
                s.customer_id == customer_id for s in self.sessions.values()
            ):
                raise APIError(
                    429,
                    "VOICE_BUSY",
                    "An active voice session already exists or voice capacity is full.",
                )
            session = Connection(uuid4(), customer_id, conversation_id, bearer)
            expires = datetime.now(UTC) + timedelta(minutes=5)
            with self.factory() as db, db.begin():
                db.add(
                    VoiceSession(
                        id=session.id,
                        customer_id=customer_id,
                        conversation_id=conversation_id,
                        expires_at=expires,
                        status="connecting",
                    )
                )
            self.sessions[session.id] = session
            session.room = rtc.Room()

            @session.room.on("participant_connected")
            def connected(participant):
                if participant.identity == session.identity:
                    session.joined = True

            @session.room.on("participant_disconnected")
            def disconnected(participant):
                if participant.identity == session.identity:
                    asyncio.create_task(self.close(session, "client_disconnected"))

            @session.room.on("disconnected")
            def room_disconnected(*_):
                if not session.closed:
                    asyncio.create_task(self.close(session, "transport_disconnected"))

            @session.room.on("track_subscribed")
            def subscribed(track, publication, participant):
                if (
                    participant.identity == session.identity
                    and track.kind == rtc.TrackKind.KIND_AUDIO
                ):
                    task = asyncio.create_task(self.read_audio(session, track))
                    session.readers.add(task)
                    task.add_done_callback(session.readers.discard)

            try:
                await asyncio.wait_for(
                    session.room.connect(
                        self.settings.livekit_internal_url or self.settings.livekit_url,
                        room_token(self.settings, session, worker=True),
                    ),
                    timeout=12,
                )
                session.source = rtc.AudioSource(24000, 1, queue_size_ms=100)
                track = rtc.LocalAudioTrack.create_audio_track("BankAI answer", session.source)
                await session.room.local_participant.publish_track(
                    track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
                )
                session.status = "ready"
                self.event(
                    session,
                    "session_connected",
                    max_seconds=300,
                    max_turns=8,
                    recording_stored=False,
                )
                session.timer = asyncio.create_task(self.expire(session))
                return session, expires, room_token(self.settings, session)
            except Exception as exc:
                await self.close(session, "connection_failed")
                raise APIError(
                    503,
                    "LIVEKIT_UNAVAILABLE",
                    "The voice connection could not start. Use text chat or try again.",
                ) from exc

    async def expire(self, session):
        await asyncio.sleep(20)
        if not session.joined:
            await self.close(session, "client_did_not_join")
            return
        await asyncio.sleep(280)
        await self.close(session, "time_limit")

    async def read_audio(self, session, track):
        stream = rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1, capacity=50)
        try:
            async for event in stream:
                if session.closed:
                    break
                if session.status == "listening":
                    data = bytes(event.frame.data)
                    if len(session.buffer) + len(data) > MAX_INPUT_BYTES:
                        session.buffer.clear()
                        session.status = "ready"
                        self.event(session, "speech_error", code="VOICE_AUDIO_LENGTH")
                    else:
                        session.buffer.extend(data)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- transport boundary must close the session on SDK failures
            if not session.closed:
                await self.close(session, "audio_disconnected")
        finally:
            await stream.aclose()

    def listen(self, session, turn_id):
        if turn_id in session.seen:
            return
        if session.status != "ready" or len(session.seen) >= 8:
            raise APIError(
                409,
                "VOICE_TURN_LIMIT",
                "Wait for this answer or start a new voice session after the turn limit.",
            )
        session.turn_id = turn_id
        session.seen.add(turn_id)
        session.buffer.clear()
        session.interrupted = False
        session.status = "listening"
        self.event(session, "speech_start", message_id=str(turn_id))

    def finish(self, session, turn_id):
        if session.turn_id != turn_id:
            raise APIError(409, "VOICE_TURN_CONFLICT", "This is not the active voice question.")
        if session.status != "listening":
            return
        session.status = "processing"
        pcm = bytes(session.buffer)
        session.buffer.clear()
        session.task = asyncio.create_task(self.process(session, turn_id, pcm))

    async def process(self, session, turn_id, pcm):
        started, run_id = monotonic(), None
        try:
            self.event(
                session,
                "stt_start",
                message_id=str(turn_id),
                audio_ms=len(pcm) * 1000 // (SAMPLE_RATE * 2),
            )
            transcript, usage = await asyncio.to_thread(transcribe, self.settings, pcm)
            pcm = b""
            if session.closed or session.interrupted:
                return
            self.event(
                session,
                "stt_end",
                message_id=str(turn_id),
                model=self.settings.stt_model,
                usage=usage,
            )
            async with httpx.AsyncClient(timeout=190) as client:
                response = await client.post(
                    self.settings.agent_base_url + "/api/v1/chat",
                    headers={"Authorization": "Bearer " + session.bearer},
                    json={
                        "conversation_id": str(session.conversation_id),
                        "message_id": str(turn_id),
                        "message": transcript,
                    },
                )
            if response.status_code != 200:
                raise APIError(
                    503,
                    "VOICE_AGENT_UNAVAILABLE",
                    "The banking assistant could not complete this voice question. Check history before retrying.",
                )
            reply = ChatReply.model_validate(response.json())
            run_id = reply.run_id
            self.event(
                session,
                "banking_answer",
                run_id=run_id,
                message_id=str(turn_id),
                interrupted=session.interrupted,
            )
            if session.closed or session.interrupted:
                return
            self.event(session, "tts_start", run_id=run_id, model=self.settings.tts_model)
            audio, rate, usage = await asyncio.to_thread(
                synthesize, self.settings, spoken_answer(reply)
            )
            if session.closed or session.interrupted:
                return
            if rate != 24000:
                raise APIError(503, "TTS_FORMAT", "Unsupported speech rate; read the saved answer.")
            session.status = "speaking"
            self.event(
                session,
                "tts_end",
                run_id=run_id,
                usage=usage,
                audio_ms=len(audio) * 1000 // (rate * 2),
            )
            for offset in range(0, len(audio), 960):
                if session.closed or session.interrupted:
                    break
                frame = audio[offset : offset + 960]
                await session.source.capture_frame(rtc.AudioFrame(frame, rate, 1, len(frame) // 2))
            await session.source.wait_for_playout()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 -- report safe codes and leave a recoverable voice state
            if not session.closed:
                self.event(
                    session,
                    "speech_error",
                    run_id=run_id,
                    code=getattr(exc, "code", "VOICE_UNAVAILABLE"),
                )
        finally:
            if not session.closed:
                session.status = "ready"
                self.event(
                    session,
                    "turn_end",
                    run_id=run_id,
                    message_id=str(turn_id),
                    duration_ms=int((monotonic() - started) * 1000),
                    interrupted=session.interrupted,
                )

    def interrupt(self, session):
        if session.interrupted or session.status == "ready":
            return
        session.interrupted = True
        audio_ms = len(session.buffer) * 1000 // (SAMPLE_RATE * 2)
        session.buffer.clear()
        if session.source:
            session.source.clear_queue()
        if session.status == "listening":
            session.status = "ready"
        # An in-flight banking request may still finish and save its answer; never replay it.
        self.event(
            session,
            "interrupted",
            message_id=str(session.turn_id) if session.turn_id else None,
            discarded_audio_ms=audio_ms,
        )

    async def close(self, session, reason):
        if session.closed:
            return
        session.closed, session.status = True, "closed"
        session.bearer = ""
        session.buffer.clear()
        if session.source:
            session.source.clear_queue()
        current = asyncio.current_task()
        tasks = [t for t in [session.task, session.timer, *session.readers] if t and t != current]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if session.room:
                await session.room.disconnect()
            async with api.LiveKitAPI(
                self.settings.livekit_internal_url or self.settings.livekit_url,
                self.settings.livekit_api_key.get_secret_value(),
                self.settings.livekit_api_secret.get_secret_value(),
                timeout=ClientTimeout(total=5),
            ) as client:
                await client.room.delete_room(api.DeleteRoomRequest(room=session.room_name))
        except Exception as exc:  # noqa: BLE001 -- cleanup must release memory even if the server is gone
            self.event(session, "cleanup_error", error_type=type(exc).__name__)
        finally:
            if session.source:
                await session.source.aclose()
            self.event(session, "session_closed", reason=reason)
            self.sessions.pop(session.id, None)
