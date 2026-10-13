import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.db.session import build_engine


@pytest.fixture
def migrated_db():
    if os.environ.get("BANKAI_RUN_DB_TESTS") != "1":
        pytest.skip("Set BANKAI_RUN_DB_TESTS=1 to run isolated PostgreSQL integration tests")
    engine = build_engine()
    schema = f"bankai_test_{uuid4().hex}"
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with engine.connect() as connection:
        # Generated identifier only; no user-provided schema can be dropped.
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}", public'))
        connection.commit()
        engine.dialect.default_schema_name = schema
        config.attributes["connection"] = connection
        config.attributes["schema"] = schema
        try:
            command.upgrade(config, "head")
            connection.commit()
            yield connection, config
        finally:
            connection.rollback()
            connection.execute(text("SET search_path TO public"))
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            connection.commit()
    engine.dispose()
