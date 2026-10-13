import pytest

from app.core.config import Settings
from app.seed.demo_data import require_local_demo


def test_seed_rejects_remote_database():
    settings = Settings(
        _env_file=None, database_url="postgresql+psycopg://demo:demo@remote.example/db"
    )
    with pytest.raises(ValueError, match="local development"):
        require_local_demo(settings)


def test_seed_rejects_non_development_mode():
    with pytest.raises(ValueError, match="local development"):
        require_local_demo(Settings(_env_file=None, app_env="test"))
