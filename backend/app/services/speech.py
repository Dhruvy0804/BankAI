"""Speech conversion only; the existing five banking agents remain authoritative."""

import base64
import io
import re
import wave
from array import array

from google import genai
from google.genai import types
from pydantic import Field

from app.core.errors import APIError
from app.schemas import Input

SAMPLE_RATE = 16000
MAX_INPUT_BYTES = SAMPLE_RATE * 2 * 30


class Transcript(Input):
    speech_detected: bool
    text: str = Field(max_length=2000)


def wav_audio(pcm, rate=SAMPLE_RATE):
    if not pcm or len(pcm) % 2:
        raise ValueError("Audio must be nonempty mono PCM16")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def client(settings, key):
    return genai.Client(
        api_key=(key or settings.llm_api_key).get_secret_value(),
        http_options=types.HttpOptions(
            timeout=40000, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    )


def transcribe(settings, pcm):
    if not 8000 <= len(pcm) <= MAX_INPUT_BYTES or len(pcm) % 2:
        raise APIError(
            422, "VOICE_AUDIO_LENGTH", "Speak for between a quarter second and 30 seconds."
        )
    samples = array("h", pcm)
    if sum(value * value for value in samples) / len(samples) < 2500:
        raise APIError(422, "VOICE_NO_SPEECH", "No clear speech was heard. Please try again.")
    try:
        with client(settings, settings.stt_api_key) as provider:
            response = provider.interactions.create(
                model=settings.stt_model,
                input=[
                    {
                        "type": "audio",
                        "data": base64.b64encode(wav_audio(pcm)).decode(),
                        "mime_type": "audio/wav",
                    }
                ],
                generation_config={"transcription_config": {"mode": {"type": "verbatim"}}},
                store=False,
            )
        text = response.output_text or ""
        result = Transcript(speech_detected=bool(text.strip()), text=text)
        if not result.speech_detected or not result.text.strip():
            raise APIError(422, "VOICE_NO_SPEECH", "No clear speech was heard. Please try again.")
        return result.text.strip(), speech_usage(getattr(response, "usage", None))
    except APIError:
        raise
    except Exception as exc:
        raise APIError(
            503,
            "STT_UNAVAILABLE",
            "Speech recognition is unavailable. You can still type your question.",
        ) from exc


def spoken_answer(reply):
    text = re.sub(r"\[P-[^\]]+\]", "", reply.answer)
    text = re.sub(r"<[^>]*>|[*_`#]", "", text).strip()
    if reply.pending_actions:
        text = (
            "This is a simulated request. Review and confirm the exact action in the app; saying yes does not confirm it. "
            + text
        )
    if len(text) > 1000:
        text = text[:1000].rsplit(" ", 1)[0] + ". Full details are shown in the conversation."
    if reply.sources:
        text += " Supporting fictional policy sources are shown in the app."
    return text


def speech_usage(usage):
    if usage is None:
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    return {
        "input_tokens": getattr(usage, "total_input_tokens", None),
        "output_tokens": getattr(usage, "total_output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def synthesize(settings, text):
    try:
        with client(settings, settings.tts_api_key) as provider:
            response = provider.interactions.create(
                model=settings.tts_model,
                input=[{"type": "user_input", "content": [{"type": "text", "text": text}]}],
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": "Kore"}]},
                store=False,
            )
        audio = response.output_audio
        if not audio:
            raise ValueError("Missing speech output")
        data = base64.b64decode(audio.data, validate=True)
        with wave.open(io.BytesIO(data), "rb") as wav:
            if (
                wav.getnchannels() != 1
                or wav.getsampwidth() != 2
                or wav.getframerate() not in (24000, 48000)
            ):
                raise ValueError("Unsupported speech format")
            rate = wav.getframerate()
            if not 0 < wav.getnframes() <= rate * 90:
                raise ValueError("Speech length out of bounds")
            pcm = wav.readframes(wav.getnframes())
        # Interactions usage is separate from the banking model's usage and is not guessed.
        usage = getattr(response, "usage", None)
        return pcm, rate, speech_usage(usage)
    except Exception as exc:
        raise APIError(
            503,
            "TTS_UNAVAILABLE",
            "Audio playback is unavailable. Read the saved answer in the app.",
        ) from exc
