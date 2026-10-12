from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings


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
        yield
        engine.dispose()

    app = FastAPI(
        title="BankAI API",
        description="Local prototype using fictional banking data. Phase 1 infrastructure only.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

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
