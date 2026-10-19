from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pydantic import ValidationError
from starlette.responses import JSONResponse

from app.agents.contracts import ProtocolGrant
from app.agents.state import Blackboard
from app.core.errors import APIError
from app.core.security import signing_key
from app.models import Customer

current_grant: ContextVar[ProtocolGrant] = ContextVar("bankai_protocol_grant")


def issue_grant(settings, customer_id, run_id, role):
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(customer_id),
            "run_id": str(run_id),
            "role": role,
            "iat": now,
            "exp": now + timedelta(seconds=settings.agent_timeout_seconds),
            "iss": "bankai",
            "aud": "bankai-protocol",
            "jti": str(uuid4()),
        },
        signing_key(settings),
        algorithm="HS256",
    )


def decode_grant(settings, token):
    try:
        claims = jwt.decode(
            token,
            signing_key(settings),
            algorithms=["HS256"],
            issuer="bankai",
            audience="bankai-protocol",
            options={"require": ["sub", "exp", "iat", "run_id", "role", "jti"]},
        )
        return ProtocolGrant.model_validate(
            {key: claims[key] for key in ProtocolGrant.model_fields}
        )
    except (jwt.InvalidTokenError, ValidationError, KeyError, ValueError) as exc:
        raise APIError(401, "INVALID_GRANT", "A valid service grant is required.") from exc


class ProtocolAuth:
    """Protect the whole mounted protocol app, including Agent Card discovery."""

    def __init__(self, app, settings, factory, role=None):
        self.app, self.settings, self.factory, self.role = app, settings, factory, role

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            headers = dict(scope["headers"])
            authorization = headers.get(b"authorization", b"").decode()
            if not authorization.startswith("Bearer "):
                raise APIError(401, "INVALID_GRANT", "A service grant is required.")
            grant = decode_grant(self.settings, authorization[7:])
            if self.role and grant.role != self.role:
                raise APIError(403, "ROLE_DENIED", "Service grant does not authorize this role.")
            board = Blackboard(self.factory, grant.run_id, grant.sub)
            with self.factory() as db:
                board.owned(db, active=True)
                customer = db.get(Customer, grant.sub)
                if customer is None or not customer.is_active:
                    raise APIError(401, "INVALID_GRANT", "Inactive service identity.")
        except APIError as error:
            await JSONResponse(
                {"error": {"code": error.code, "message": error.message}}, status_code=error.status
            )(scope, receive, send)
            return
        marker = current_grant.set(grant)
        try:
            await self.app(scope, receive, send)
        finally:
            current_grant.reset(marker)
