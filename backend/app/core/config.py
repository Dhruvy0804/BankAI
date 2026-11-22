from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_env: Literal["development", "test"] = "development"
    database_url: str = Field(
        default="postgresql+psycopg://bankai:bankai_dev_only@127.0.0.1:55432/bankai",
        repr=False,
    )
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    app_secret_key: SecretStr | None = None
    access_token_expire_minutes: int = Field(default=30, ge=1, le=120)
    confirmation_expire_seconds: int = Field(default=300, ge=30, le=900)
    llm_provider: Literal["", "gemini"] = ""
    llm_api_key: SecretStr | None = None
    llm_model: str = Field(default="", max_length=120)
    llm_timeout_seconds: int = Field(default=30, ge=5, le=45)
    llm_max_output_tokens: int = Field(default=1024, ge=256, le=4096)
    chat_mode: Literal["guidance", "agents"] = "guidance"
    agent_base_url: str = "http://127.0.0.1:8000"
    agent_timeout_seconds: int = Field(default=150, ge=30, le=180)
    embedding_provider: Literal["", "gemini"] = ""
    embedding_api_key: SecretStr | None = None
    embedding_model: Literal["", "gemini-embedding-001"] = ""
    voice_enabled: bool = False
    livekit_url: str = ""
    livekit_internal_url: str = ""
    livekit_api_key: SecretStr | None = None
    livekit_api_secret: SecretStr | None = None
    stt_provider: Literal["", "gemini"] = ""
    stt_api_key: SecretStr | None = None
    stt_model: Literal["gemini-3.5-transcribe"] = "gemini-3.5-transcribe"
    tts_provider: Literal["", "gemini"] = ""
    tts_api_key: SecretStr | None = None
    tts_model: Literal["gemini-3.8-flash-lite-tts"] = "gemini-3.8-flash-lite-tts"
    phone_enabled: bool = False
    phone_provider: Literal["twilio", "plivo"] = "twilio"
    phone_owner_customer_id: str = ""
    evaluation_owner_customer_id: str = ""
    evaluation_live_enabled: bool = False
    evaluation_cell_cooldown_seconds: int = Field(default=65, ge=0, le=300)
    phone_allowed_numbers: str = ""
    phone_caller_number: str = ""
    phone_public_base_url: str = ""
    phone_max_duration_seconds: int = Field(default=300, ge=60, le=300)
    twilio_account_sid: SecretStr | None = None
    twilio_auth_token: SecretStr | None = None
    plivo_auth_id: SecretStr | None = None
    plivo_auth_token: SecretStr | None = None

    @property
    def phone_configured(self) -> bool:
        import re
        from urllib.parse import urlsplit

        url = urlsplit(self.phone_public_base_url)
        allowed = [n.strip() for n in self.phone_allowed_numbers.split(",") if n.strip()]
        return bool(
            self.phone_enabled
            and self.chat_mode == "agents"
            and self.llm_configured
            and (self.phone_provider != "plivo" or self.phone_max_duration_seconds >= 100)
            and re.fullmatch(r"[0-9a-fA-F-]{36}", self.phone_owner_customer_id)
            and allowed
            and all(re.fullmatch(r"\+[1-9]\d{7,14}", n) for n in allowed)
            and re.fullmatch(r"\+[1-9]\d{7,14}", self.phone_caller_number)
            and url.scheme == "https"
            and url.hostname
            and not (url.username or url.password or url.query or url.fragment or url.path not in ("", "/"))
            and (
                (
                    self.phone_provider == "twilio"
                    and self.twilio_account_sid
                    and re.fullmatch(r"AC[0-9a-fA-F]{32}", self.twilio_account_sid.get_secret_value())
                    and self.twilio_auth_token
                    and self.twilio_auth_token.get_secret_value().strip()
                )
                or (
                    self.phone_provider == "plivo"
                    and self.plivo_auth_id
                    and self.plivo_auth_id.get_secret_value().strip()
                    and self.plivo_auth_token
                    and self.plivo_auth_token.get_secret_value().strip()
                )
            )
        )

    @field_validator("livekit_url", "livekit_internal_url")
    @classmethod
    def livekit_endpoint(cls, value):
        from urllib.parse import urlsplit

        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("ws", "wss")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("LiveKit URL must be a ws/wss origin without credentials")
        return value.rstrip("/")

    @property
    def voice_configured(self) -> bool:
        return bool(
            self.voice_enabled
            and self.chat_mode == "agents"
            and self.llm_configured
            and self.livekit_url
            and self.livekit_api_key
            and self.livekit_api_secret
            and self.stt_provider == "gemini"
            and self.tts_provider == "gemini"
            and (self.stt_api_key or self.llm_api_key)
            and (self.tts_api_key or self.llm_api_key)
        )

    @property
    def embedding_key(self) -> SecretStr | None:
        return self.embedding_api_key or self.llm_api_key

    @property
    def embedding_configured(self) -> bool:
        key = self.embedding_key
        return bool(
            self.embedding_provider == "gemini"
            and self.embedding_model
            and key
            and key.get_secret_value().strip()
        )

    @field_validator("agent_base_url")
    @classmethod
    def internal_endpoint(cls, value):
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in ("127.0.0.1", "localhost", "backend")
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("AGENT_BASE_URL must be the local/internal backend origin")
        return value.rstrip("/")

    @property
    def llm_configured(self) -> bool:
        key = self.llm_api_key.get_secret_value().strip() if self.llm_api_key else ""
        return self.llm_provider == "gemini" and bool(key and self.llm_model.strip())

    @property
    def auth_configured(self) -> bool:
        key = self.app_secret_key.get_secret_value() if self.app_secret_key else ""
        return len(key) >= 32 and not key.lower().startswith(("replace", "change", "demo"))

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: str) -> str:
        try:
            valid = make_url(value).drivername == "postgresql+psycopg"
        except (ArgumentError, ValueError):
            valid = False
        if not valid:
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
