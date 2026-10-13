from sqlalchemy import create_engine

from app.core.config import Settings


def build_engine(settings: Settings | None = None):
    config = settings or Settings()
    return create_engine(
        config.database_url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
    )
