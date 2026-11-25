import pytest

from app.core.config import Settings
from app.seed.demo_data import require_demo_seed


def test_seed_rejects_remote_database():
    settings = Settings(
        _env_file=None, database_url="postgresql+psycopg://demo:demo@remote.example/db"
    )
    with pytest.raises(ValueError, match="local database host"):
        require_demo_seed(settings)


def test_seed_rejects_non_development_mode():
    with pytest.raises(ValueError, match="development or cloud_demo"):
        require_demo_seed(Settings(_env_file=None, app_env="test"))


def test_seed_allows_explicit_cloud_demo_on_internal_database():
    require_demo_seed(Settings(_env_file=None, app_env="cloud_demo", database_url="postgresql+psycopg://demo:demo@db/bankai"))
