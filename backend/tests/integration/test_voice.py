from time import monotonic, sleep
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import APIError
from app.models import ChatTurn, VoiceEvent
from tests.integration.test_agents import runtime, simulated_models  # noqa: F401

pytestmark = pytest.mark.integration


class FakeRoom:
    def __init__(self):
        self.local_participant = self

    def on(self, name):
        return lambda fn: fn

    async def connect(self, *args):
        pass

    async def publish_track(self, *args):
        pass

    async def disconnect(self):
        pass


class FakeSource:
    def __init__(self, *args, **kwargs):
        self.frames = []

    def clear_queue(self):
        pass

    async def capture_frame(self, frame):
        self.frames.append(frame)

    async def wait_for_playout(self):
        pass

    async def aclose(self):
        pass


class FakeAPI:
    def __init__(self, *args, **kwargs):
        self.room = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def delete_room(self, *args):
        pass


@pytest.fixture
def voice(runtime, monkeypatch):  # noqa: F811 -- imported fixture
    settings, factory, client, cid, _rid = runtime
    settings.voice_enabled = True
    settings.livekit_url = "ws://127.0.0.1:7880"
    from pydantic import SecretStr

    settings.livekit_api_key = SecretStr("voice-test")
    settings.livekit_api_secret = SecretStr("voice-test-secret-at-least-thirty-two-characters")
    settings.stt_provider = settings.tts_provider = "gemini"
    monkeypatch.setattr("app.services.voice.rtc.Room", FakeRoom)
    monkeypatch.setattr("app.services.voice.rtc.AudioSource", FakeSource)
    monkeypatch.setattr(
        "app.services.voice.rtc.LocalAudioTrack.create_audio_track", lambda *_: None
    )
    monkeypatch.setattr("app.services.voice.api.LiveKitAPI", FakeAPI)
    monkeypatch.setattr(
        "app.services.voice.transcribe",
        lambda *_: ("Show accounts, calculate an EMI, and summarize", {"total_tokens": 10}),
    )
    monkeypatch.setattr(
        "app.services.voice.synthesize", lambda *_: (b"\0\0" * 2400, 24000, {"total_tokens": 5})
    )
    # Locate the real running manager through the protocol runtime's Uvicorn app.
    # Tests call HTTP for authorization, while connection-only seams are replaced.
    from app.services.voice import VoiceManager

    original = VoiceManager.create
    instances = []

    async def capture(self, *args):
        instances.append(self)
        return await original(self, *args)

    monkeypatch.setattr(VoiceManager, "create", capture)
    response = client.post("/api/v1/voice/sessions", json={"conversation_id": str(cid)})
    assert response.status_code == 200, response.text
    join = response.json()
    manager = instances[0]
    try:
        yield settings, factory, client, cid, join, manager
    finally:
        client.post(f"/api/v1/voice/sessions/{join['session_id']}/close", json={})


def wait_ready(client, sid):
    deadline = monotonic() + 20
    while monotonic() < deadline:
        result = client.get(f"/api/v1/voice/sessions/{sid}").json()
        if result["status"] == "ready":
            return result
        sleep(0.05)
    raise AssertionError("Voice turn did not finish")


def test_room_token_scope_owner_capacity_and_close(voice):
    settings, _, client, cid, join, _ = voice
    claims = jwt.decode(
        join["token"],
        settings.livekit_api_secret.get_secret_value(),
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert claims["video"]["room"] == "bankai-voice-" + join["session_id"]
    assert claims["video"]["canPublishSources"] == ["microphone"]
    assert claims["video"]["canPublishData"] is False
    assert claims["exp"] - claims["nbf"] <= 300
    from app.seed.demo_data import DEMO_PASSWORD

    other = client.post(
        "/api/v1/auth/login", json={"email": "demo.ravi@bankai.example", "password": DEMO_PASSWORD}
    ).json()["access_token"]
    other_headers = {"Authorization": "Bearer " + other}
    assert (
        client.get(
            "/api/v1/voice/sessions/" + join["session_id"], headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/voice/sessions/" + join["session_id"] + "/close",
            headers=other_headers,
            json={},
        ).status_code
        == 404
    )
    assert client.get("/api/v1/voice/sessions/" + str(uuid4())).status_code == 404
    assert (
        client.post("/api/v1/voice/sessions", json={"conversation_id": str(uuid4())}).status_code
        == 404
    )
    assert (
        client.post("/api/v1/voice/sessions", json={"conversation_id": str(cid)}).status_code == 429
    )
    sid = join["session_id"]
    assert client.post(f"/api/v1/voice/sessions/{sid}/close", json={}).json()["status"] == "closed"
    assert client.post(f"/api/v1/voice/sessions/{sid}/close", json={}).status_code == 200


def test_voice_uses_real_banking_protocol_workflow_and_saves_provenance(voice, simulated_models):  # noqa: F811
    _, factory, client, cid, join, manager = voice
    sid = join["session_id"]
    turn = str(uuid4())
    for _ in range(2):
        assert (
            client.post(f"/api/v1/voice/sessions/{sid}/listen", json={"turn_id": turn}).status_code
            == 200
        )
    join_id = UUID(sid)
    session = manager.sessions[join_id]
    session.buffer.extend(b"\0\0" * 16000)
    for _ in range(2):
        assert (
            client.post(f"/api/v1/voice/sessions/{sid}/send", json={"turn_id": turn}).status_code
            == 200
        )
    result = wait_ready(client, sid)
    assert {"stt_end", "banking_answer", "tts_end", "turn_end"} <= {
        e["kind"] for e in result["events"]
    }
    assert session.source.frames and not session.buffer
    with factory() as db:
        turns = list(db.scalars(select(ChatTurn).where(ChatTurn.conversation_id == cid)))
        assert len(turns) == 1
        assert {f["tool"] for f in turns[0].response["data"]} == {
            "account_snapshot",
            "calculate_emi",
        }
        assert db.scalar(
            select(VoiceEvent).where(
                VoiceEvent.session_id == join_id, VoiceEvent.kind == "banking_answer"
            )
        ).run_id
    assert (
        client.post(f"/api/v1/voice/sessions/{sid}/listen", json={"turn_id": turn}).json()["status"]
        == "ready"
    )


def test_interruption_and_turn_boundaries(voice):
    _, _, client, _, join, manager = voice
    session = manager.sessions[UUID(join["session_id"])]
    sid = join["session_id"]
    turn = str(uuid4())
    assert client.post(f"/api/v1/voice/sessions/{sid}/listen", json={}).status_code == 422
    client.post(f"/api/v1/voice/sessions/{sid}/listen", json={"turn_id": turn})
    session.buffer.extend(b"\0\0" * 16000)
    assert (
        client.post(
            f"/api/v1/voice/sessions/{sid}/send", json={"turn_id": str(uuid4())}
        ).status_code
        == 409
    )

    assert (
        client.post(f"/api/v1/voice/sessions/{sid}/interrupt", json={}).json()["status"] == "ready"
    )
    assert session.interrupted and not session.buffer
    session.seen = {uuid4() for _ in range(8)}
    assert (
        client.post(
            f"/api/v1/voice/sessions/{sid}/listen", json={"turn_id": str(uuid4())}
        ).status_code
        == 409
    )


def test_playback_failure_preserves_the_saved_banking_answer(voice, simulated_models, monkeypatch):  # noqa: F811
    _, _, client, cid, join, manager = voice

    def unavailable(*_):
        raise APIError(503, "TTS_UNAVAILABLE", "Speech unavailable")

    monkeypatch.setattr("app.services.voice.synthesize", unavailable)
    sid = join["session_id"]
    turn = str(uuid4())
    client.post(f"/api/v1/voice/sessions/{sid}/listen", json={"turn_id": turn})
    manager.sessions[UUID(sid)].buffer.extend(b"\xff\x0f" * 16000)
    client.post(f"/api/v1/voice/sessions/{sid}/send", json={"turn_id": turn})
    result = wait_ready(client, sid)
    assert any(
        e["kind"] == "speech_error" and e["metadata"]["code"] == "TTS_UNAVAILABLE"
        for e in result["events"]
    )
    assert len(client.get("/api/v1/chat/conversations/" + str(cid)).json()["turns"]) == 1


import asyncio
import math
import os
from array import array


@pytest.mark.skipif(
    os.environ.get("BANKAI_LIVEKIT_TESTS") != "1",
    reason="Opt-in needs the configured local LiveKit server",
)
def test_real_webrtc_audio_round_trip(runtime, simulated_models, monkeypatch):  # noqa: F811
    from livekit import rtc

    settings, _, client, cid, _ = runtime
    local = Settings()
    settings.voice_enabled = True
    settings.livekit_url = local.livekit_url
    settings.livekit_internal_url = local.livekit_url
    settings.livekit_api_key, settings.livekit_api_secret = (
        local.livekit_api_key,
        local.livekit_api_secret,
    )
    settings.stt_provider = settings.tts_provider = "gemini"
    incoming = []
    tone = array(
        "h", (int(4000 * math.sin(2 * math.pi * 440 * i / 24000)) for i in range(12000))
    ).tobytes()

    def transcript(_settings, pcm):
        incoming.append(len(pcm))
        return "Show accounts, calculate an EMI, and summarize", {"total_tokens": None}

    monkeypatch.setattr("app.services.voice.transcribe", transcript)
    monkeypatch.setattr(
        "app.services.voice.synthesize", lambda *_: (tone, 24000, {"total_tokens": None})
    )
    join = client.post("/api/v1/voice/sessions", json={"conversation_id": str(cid)})
    assert join.status_code == 200, join.text
    data = join.json()
    sid = data["session_id"]
    received = []
    peaks = []

    async def exchange():
        room = rtc.Room()
        readers = []

        async def read(track):
            stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)
            try:
                async for event in stream:
                    received.append(len(event.frame.data))
                    peaks.append(
                        max((abs(v) for v in array("h", bytes(event.frame.data))), default=0)
                    )
            finally:
                await stream.aclose()

        @room.on("track_subscribed")
        def subscribed(track, publication, participant):
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                readers.append(asyncio.create_task(read(track)))

        try:
            await room.connect(data["url"], data["token"])
            source = rtc.AudioSource(24000, 1)
            track = rtc.LocalAudioTrack.create_audio_track("fixture", source)
            await room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            await asyncio.sleep(0.4)
            turn = str(uuid4())
            assert (
                client.post(
                    f"/api/v1/voice/sessions/{sid}/listen", json={"turn_id": turn}
                ).status_code
                == 200
            )
            for offset in range(0, len(tone), 960):
                frame = tone[offset : offset + 960]
                await source.capture_frame(rtc.AudioFrame(frame, 24000, 1, len(frame) // 2))
            await source.wait_for_playout()
            await asyncio.sleep(0.3)
            client.post(f"/api/v1/voice/sessions/{sid}/send", json={"turn_id": turn})
            for _ in range(200):
                snapshot = client.get(f"/api/v1/voice/sessions/{sid}").json()
                if snapshot["status"] == "ready":
                    break
                await asyncio.sleep(0.05)
            assert snapshot["status"] == "ready"
            await asyncio.sleep(0.2)
            assert sum(received) > 10000 and incoming[0] > 8000
            assert max(peaks) > 200
            assert any(e["kind"] == "banking_answer" and e["run_id"] for e in snapshot["events"])
            await source.aclose()
        finally:
            for task in readers:
                task.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            await room.disconnect()

    try:
        asyncio.run(exchange())
    finally:
        client.post(f"/api/v1/voice/sessions/{sid}/close", json={})


@pytest.mark.skipif(
    os.environ.get("BANKAI_BROWSER_VOICE_TESTS") != "1",
    reason="Opt-in requires Edge, .qa-tools and local LiveKit",
)
def test_voice_browser_controls_and_audio(runtime, simulated_models, monkeypatch):  # noqa: F811
    import shutil
    import socket
    import subprocess
    from pathlib import Path

    import httpx

    from app.seed.demo_data import DEMO_PASSWORD
    from app.services.speech import wav_audio

    browser_api = pytest.importorskip("playwright.sync_api")
    settings, _, _, _, _ = runtime
    local = Settings()
    settings.voice_enabled = True
    settings.livekit_url = settings.livekit_internal_url = local.livekit_url
    settings.livekit_api_key, settings.livekit_api_secret = (
        local.livekit_api_key,
        local.livekit_api_secret,
    )
    settings.stt_provider = settings.tts_provider = "gemini"
    tone = array(
        "h", (int(4000 * math.sin(2 * math.pi * 440 * i / 24000)) for i in range(24000))
    ).tobytes()
    monkeypatch.setattr(
        "app.services.voice.transcribe",
        lambda *_: ("Show accounts, calculate an EMI, and summarize", {"total_tokens": None}),
    )
    monkeypatch.setattr(
        "app.services.voice.synthesize", lambda *_: (tone, 24000, {"total_tokens": None})
    )
    root = Path(__file__).resolve().parents[3]
    audio_path = root / ".artifacts/phase8-browser-tone.wav"
    audio_path.write_bytes(wav_audio(tone, 24000))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            shutil.which("node"),
            str(root / "frontend/node_modules/vite/bin/vite.js"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--strictPort",
        ],
        cwd=root / "frontend",
        env=os.environ | {"API_PROXY_TARGET": settings.agent_base_url},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    origin = f"http://127.0.0.1:{port}"
    try:
        deadline = monotonic() + 20
        while monotonic() < deadline:
            try:
                if httpx.get(origin, timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            sleep(0.2)
        with browser_api.sync_playwright() as browser_tools:
            browser = browser_tools.chromium.launch(
                channel="msedge",
                headless=True,
                args=[
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                    f"--use-file-for-fake-audio-capture={audio_path}",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            page = browser.new_page(
                viewport={"width": 1366, "height": 900}, permissions=["microphone"]
            )
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(origin)
            page.get_by_label("Email address").fill("demo.asha@bankai.example")
            page.get_by_label("Password", exact=True).fill(DEMO_PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.get_by_role("link", name="Text assistant", exact=True).click()
            page.get_by_role("button", name="Start browser voice", exact=True).click()
            browser_api.expect(
                page.get_by_role("button", name="Speak question", exact=True)
            ).to_be_enabled(timeout=20000)
            assert page.get_by_label("Your question").is_disabled()
            page.get_by_role("button", name="Speak question", exact=True).click()
            browser_api.expect(
                page.get_by_role("button", name="Send voice question", exact=True)
            ).to_be_enabled()
            page.wait_for_timeout(1500)
            page.get_by_role("button", name="Send voice question", exact=True).click()
            browser_api.expect(
                page.get_by_text(
                    "Verified results are ready; any pending action requires confirmation.",
                    exact=True,
                )
            ).to_be_visible(timeout=25000)
            browser_api.expect(
                page.get_by_role("button", name="Speak question", exact=True)
            ).to_be_enabled(timeout=10000)
            assert page.locator("audio").count() == 1
            page.wait_for_function("document.querySelector('audio')?.currentTime > 0")
            page.screenshot(path=str(root / ".artifacts/phase8-voice-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(root / ".artifacts/phase8-voice-mobile.png"), full_page=True)
            page.get_by_role("button", name="End voice session", exact=True).click()
            browser_api.expect(
                page.get_by_role("button", name="Start browser voice", exact=True)
            ).to_be_enabled()
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
