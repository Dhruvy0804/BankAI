import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.evaluation import load_pilot
from evals.run_comparison import execute_case, isolated_runtime

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.integration.test_agents",)


def test_isolated_pilot_records_real_protocol_trace_without_provider_calls(simulated_models):
    settings = Settings(
        _env_file=None, app_env="test", chat_mode="agents",
        app_secret_key="evaluation-pilot-test-signing-secret-at-least-32-bytes",
        llm_provider="gemini", llm_model="test-model", llm_api_key="fake-test-key",
    )
    case = next(case for case in load_pilot()[0] if case.id == "loan-emi-fixed")
    from app.agents.configuration import AgentConfiguration

    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            before = connection.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'bankai_eval_%'"))
        with isolated_runtime(settings) as (isolated_settings, factory):
            result = execute_case(isolated_settings, factory, case, AgentConfiguration(), 1)
            assert result["status"] == "completed"
            assert result["score"]["passed"]
            assert result["model_calls"] > 0 and result["tool_calls"] > 0
            assert any(event["kind"] == "a2a_result" for event in result["events"])
        with engine.connect() as connection:
            after = connection.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'bankai_eval_%'"))
        assert after == before
    finally:
        engine.dispose()
