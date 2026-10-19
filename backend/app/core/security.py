from collections import deque
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import APIError

passwords = PasswordHash.recommended()
# Equal password work for unknown and known login identifiers.
DUMMY_HASH = passwords.hash("unusable-dummy-password-for-login-timing")


def signing_key(settings: Settings) -> str:
    if not settings.auth_configured:
        raise APIError(503, "AUTH_NOT_CONFIGURED", "Configure a strong APP_SECRET_KEY locally.")
    return settings.app_secret_key.get_secret_value()


def issue_token(customer_id: UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(customer_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
            "iss": "bankai",
            "aud": "bankai-api",
            "token_type": "access",
        },
        signing_key(settings),
        algorithm="HS256",
    )


def decode_token(token: str, settings: Settings) -> UUID:
    key = signing_key(settings)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            issuer="bankai",
            audience="bankai-api",
            options={"require": ["exp", "iat", "sub", "iss", "aud", "token_type"]},
        )
        if claims["token_type"] != "access":
            raise ValueError("Wrong token type")
        return UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise APIError(
            401,
            "UNAUTHENTICATED",
            "A valid access token is required.",
            action="authentication_failed",
        ) from exc


class LoginLimiter:
    """Local single-process throttle; bounded memory, no forwarded-IP trust."""

    def __init__(
        self,
        attempts: int = 10,
        window: int = 60,
        message: str = "Too many login attempts. Try again later.",
    ):
        self.attempts = attempts
        self.window = window
        self.message = message
        self.entries: dict[str, deque] = {}
        self.lock = Lock()

    def check(self, key: str):
        now = monotonic()
        with self.lock:
            self.entries = {
                k: v for k, v in self.entries.items() if v and v[-1] > now - self.window
            }
            if key not in self.entries and len(self.entries) >= 10000:
                raise APIError(429, "RATE_LIMITED", self.message)
            times = self.entries.setdefault(key, deque())
            while times and times[0] <= now - self.window:
                times.popleft()
            if len(times) >= self.attempts:
                raise APIError(429, "RATE_LIMITED", self.message)
            times.append(now)
