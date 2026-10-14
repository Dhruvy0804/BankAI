from sqlalchemy import create_engine, pool

from alembic import context
from app import models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def run(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table_schema=config.attributes.get("schema"),
        include_object=lambda obj, name, kind, reflected, compare_to: name != "alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    engine = create_engine(Settings().database_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
