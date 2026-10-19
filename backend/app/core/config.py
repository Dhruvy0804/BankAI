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
