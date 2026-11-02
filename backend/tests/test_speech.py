import base64
import io
import wave
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.errors import APIError
from app.services.speech import MAX_INPUT_BYTES, spoken_answer, synthesize, transcribe, wav_audio


def test_audio_bounds_without_provider_calls():
    with wave.open(io.BytesIO(wav_audio(b"\0\0" * 8000)), "rb") as wav:
        assert (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) == (1, 16000, 2)
    for data in (b"", b"a"):
        with pytest.raises(ValueError):
            wav_audio(data)
    for data in (b"\0\0", b"\0" * (MAX_INPUT_BYTES + 2)):
        with pytest.raises(APIError) as error:
            transcribe(Settings(_env_file=None), data)
        assert error.value.code == "VOICE_AUDIO_LENGTH"


def test_speech_does_not_read_uuid_citations_and_keeps_confirmation_warning():
    reply = SimpleNamespace(
        answer="**A pending request** [P-1234]", pending_actions=[1], sources=[1]
    )
    spoken = spoken_answer(reply)
    assert "P-1234" not in spoken and "**" not in spoken
    assert "saying yes does not confirm" in spoken
    assert "policy sources" in spoken


def test_provider_contracts_and_failure(monkeypatch):
    settings = Settings(_env_file=None, llm_api_key="fake-key", llm_model="test-model")

    class Provider:
        def __init__(self):
            self.models = self.interactions = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def create(self, **kwargs):
            if kwargs["model"] == settings.stt_model:
                assert kwargs["input"][0]["mime_type"] == "audio/wav"
                assert (
                    kwargs["generation_config"]["transcription_config"]["mode"]["type"]
                    == "verbatim"
                )
                assert kwargs["store"] is False
                return SimpleNamespace(output_text="Calculate an EMI")
            assert kwargs["store"] is False and kwargs["response_format"] == {"type": "audio"}
            assert kwargs["input"][0]["content"][0]["text"] == "Hello"
            return SimpleNamespace(
                output_audio=SimpleNamespace(
                    data=base64.b64encode(wav_audio(b"\0\0" * 2400, 24000)).decode()
                )
            )

    monkeypatch.setattr("app.services.speech.client", lambda *_: Provider())
    transcript, usage = transcribe(settings, b"\xff\x0f" * 8000)
    assert transcript == "Calculate an EMI" and usage["total_tokens"] is None
    pcm, rate, usage = synthesize(settings, "Hello")
    assert len(pcm) == 4800 and rate == 24000 and usage["total_tokens"] is None
    with pytest.raises(APIError) as no_speech:
        transcribe(settings, b"\0\0" * 8000)
    assert no_speech.value.code == "VOICE_NO_SPEECH"
    monkeypatch.setattr(
        Provider, "create", lambda *args, **kwargs: SimpleNamespace(output_audio=None)
    )
    with pytest.raises(APIError) as unavailable:
        synthesize(settings, "Hello")
    assert unavailable.value.code == "TTS_UNAVAILABLE"
