import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from threading import BoundedSemaphore
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException

from app.api.chat import router as chat_router
from app.api.phone import router as phone_router
from app.api.routes import router
from app.api.voice import router as voice_router
from app.core.config import Settings
from app.core.errors import APIError
from app.core.security import LoginLimiter
from app.services.llm import GeminiProvider
from app.services.phone import PhoneManager
from app.services.voice import VoiceManager


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "bankai-api"
    version: str = "0.1.0"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["connected"] = "connected"


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def create_app(
    settings: Settings | None = None,
    database_probe: Callable[[], None] | None = None,
    session_factory=None,
) -> FastAPI:
    config = settings or Settings()
    engine = create_engine(
        config.database_url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not config.auth_configured:
            logging.getLogger("bankai").warning(
                "Authentication disabled: configure APP_SECRET_KEY."
            )
        if config.voice_enabled:
            await app.state.voice.start()
        try:
            protocol_tools = getattr(app.state, "protocol_tools", None)
            if protocol_tools:
                async with protocol_tools.session_manager.run():
                    yield
            else:
                yield
        finally:
            await app.state.phone.shutdown()
            await app.state.voice.shutdown()
            engine.dispose()

    app = FastAPI(
        title="BankAI API",
        description="BankSim APIs using fictional banking data. Sensitive actions require explicit confirmation.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.session_factory = session_factory or sessionmaker(engine, expire_on_commit=False)
    app.state.login_limiter = LoginLimiter()
    app.state.chat_limiter = LoginLimiter(
        attempts=10, message="Too many chat requests. Try again later."
    )
    app.state.llm_provider = GeminiProvider(config)
    app.state.agent_slots = BoundedSemaphore(2)
    app.state.voice = VoiceManager(app.state.session_factory, config)
    app.state.phone = PhoneManager(app.state.session_factory, config)
    app.state.voice_limiter = LoginLimiter(
        attempts=3, message="Too many voice connection attempts. Try again later."
    )
    if config.chat_mode == "agents":
        from app.agents.protocols import mount_protocols

        app.state.protocol_tools = mount_protocols(app, config, app.state.session_factory)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(voice_router)
    app.include_router(phone_router)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def error_response(request, status, code, message):
        identifier = getattr(request.state, "request_id", str(uuid4()))
        headers = {"X-Request-ID": identifier}
        if status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if status == 429:
            headers["Retry-After"] = "60"
        return JSONResponse(
            status_code=status,
            headers=headers,
            content={"error": {"code": code, "message": message, "request_id": identifier}},
        )

    @app.exception_handler(APIError)
    async def api_error(request, error):
        return error_response(request, error.status, error.code, error.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Validation inputs can include passwords; never echo them.
        return error_response(
            request, 422, "INVALID_INPUT", "Request validation failed. Check the API schema."
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, error):
        return error_response(request, 409, "CONFLICT", "Request conflicts with the current data.")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        return error_response(
            request, 503, "DATABASE_UNAVAILABLE", "Database operation could not be completed."
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return error_response(
            request, error.status_code, "HTTP_ERROR", "Request could not be completed."
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        return error_response(
            request, 500, "INTERNAL_ERROR", "Unexpected error. Use the request ID for support."
        )

    app.include_router(router)
    app.include_router(chat_router)

    @app.get("/health", response_model=HealthResponse, tags=["Infrastructure"])
    def health():
        return HealthResponse()

    @app.get(
        "/ready",
        response_model=ReadyResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["Infrastructure"],
    )
    def ready(request: Request):
        try:
            if database_probe is not None:
                database_probe()
            else:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content=ErrorResponse(
                    error=ErrorDetail(
                        code="DATABASE_UNAVAILABLE",
                        message="Database is unavailable. Check the local database service.",
                        request_id=request.state.request_id,
                    )
                ).model_dump(),
            )
        return ReadyResponse()

    return app


app = create_app()
