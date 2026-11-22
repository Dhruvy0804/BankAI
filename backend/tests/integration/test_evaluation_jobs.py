"""Owner authorization and saved plan lifecycle without provider calls."""

from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.models import EvaluationAttempt, EvaluationJob

pytestmark = pytest.mark.integration


def test_owner_plan_review_export_and_no_paid_start(api):
    client, connection = api
    registration = client.post("/api/v1/auth/register", json={
        "email": f"evaluation-owner-{uuid4().hex}@example.org",
        "password": "Evaluation-owner-test-password-123", "full_name": "Evaluation Owner",
    })
    assert registration.status_code == 201
    owner_id = registration.json()["id"]
    login = client.post("/api/v1/auth/login", json={
        "email": registration.json()["email"], "password": "Evaluation-owner-test-password-123",
    })
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/api/v1/evaluation/config").status_code == 401
    assert client.get("/api/v1/evaluation/config", headers=headers).status_code == 403
    client.app.state.settings.evaluation_owner_customer_id = owner_id
    config = client.get("/api/v1/evaluation/config", headers=headers)
    assert config.status_code == 200 and len(config.json()["datasets"]["benchmark"]) == 60
    payload = {"dataset": "pilot", "case_ids": ["loan-emi-fixed"], "cells": ["2", "5"],
               "repeats": 2, "max_attempts": 4, "input_usd_per_million": "1",
               "output_usd_per_million": "2", "price_source": "test fixture", "price_date": "2026-11-20"}
    preview = client.post("/api/v1/evaluation/preview", headers=headers, json=payload)
    assert preview.status_code == 200 and preview.json()["attempt_count"] == 4
    assert preview.json()["runtime"]["agent_code_sha256"]
    assert client.post("/api/v1/evaluation/preview", headers=headers,
                       json={**payload, "max_attempts": 3}).status_code == 422
    saved = client.post("/api/v1/evaluation/jobs", headers=headers, json=payload)
    assert saved.status_code == 201 and saved.json()["status"] == "planned"
    job_id = saved.json()["id"]
    assert client.get("/api/v1/evaluation/jobs", headers=headers).json()[0]["id"] == job_id
    assert client.post(f"/api/v1/evaluation/jobs/{job_id}/start", headers=headers,
                       json={"acknowledge_provider_cost": True}).status_code == 503
    client.app.state.settings.evaluation_live_enabled = True
    client.app.state.settings.llm_provider = "gemini"
    client.app.state.settings.llm_api_key = SecretStr("test-only-fake-key")
    client.app.state.settings.llm_model = "changed-model"
    client.app.state.settings.chat_mode = "agents"
    drift = client.post(f"/api/v1/evaluation/jobs/{job_id}/start", headers=headers,
                        json={"acknowledge_provider_cost": True})
    assert drift.status_code == 409 and drift.json()["error"]["code"] == "EVALUATION_RUNTIME_CHANGED"
    client.app.state.settings.evaluation_live_enabled = False
    with Session(connection) as db, db.begin():
        attempt = EvaluationAttempt(job_id=UUID(job_id), position=1, result={
            "case_id": "loan-emi-fixed", "repeat": 1, "status": "completed",
            "configuration": {"agent_count": 2, "architecture": "blackboard", "prompt_strategy": "react"},
            "score": {"passed": True}, "duration_ms": 123,
            "usage": {"input_tokens": 20, "output_tokens": 10},
            "model_calls": 3, "tool_calls": 1,
        })
        db.add(attempt)
        db.flush()
        attempt_id = str(attempt.id)
    connection.commit()
    detail = client.get(f"/api/v1/evaluation/jobs/{job_id}", headers=headers)
    assert detail.status_code == 200 and detail.json()["passed_count"] == 1
    assert detail.json()["cell_metrics"]["2 / blackboard / react"]["duration_ms"] == 123
    assert detail.json()["cell_metrics"]["2 / blackboard / react"]["model_calls"] == 3
    assert detail.json()["cell_metrics"]["2 / blackboard / react"]["tool_calls"] == 1
    assert detail.json()["cell_metrics"]["2 / blackboard / react"]["calls_complete"] is True
    assert detail.json()["projected_cost_usd"] == "0.00016"
    comparison = client.get(f"/api/v1/evaluation/jobs/{job_id}/compare?case_id=loan-emi-fixed", headers=headers)
    assert comparison.status_code == 200 and len(comparison.json()["attempts"]) == 1
    assert client.get(f"/api/v1/evaluation/jobs/{job_id}/compare?case_id=card-status", headers=headers).status_code == 404
    reviewed = client.post(f"/api/v1/evaluation/jobs/{job_id}/attempts/{attempt_id}/review",
                           headers=headers, json={"quality": 4, "notes": "Accurate demo result"})
    assert reviewed.status_code == 200
    for format in ("json", "csv", "md"):
        exported = client.get(f"/api/v1/evaluation/jobs/{job_id}/export?format={format}", headers=headers)
        assert exported.status_code == 200 and "loan-emi-fixed" in exported.json()["content"]
        if format != "json":
            assert "model_calls" in exported.json()["content"].lower() or "model calls" in exported.json()["content"].lower()
    cancelled = client.post(f"/api/v1/evaluation/jobs/{job_id}/cancel", headers=headers)
    assert cancelled.json()["status"] == "cancelled"


def test_worker_reuses_saved_attempts_without_provider_calls(migrated_db):
    from contextlib import contextmanager

    from sqlalchemy.orm import sessionmaker

    from app.agents.configuration import AgentConfiguration
    from app.core.config import Settings
    from app.evaluation import runtime_snapshot, selected_attempts
    from app.seed.demo_data import demo_id, seed_demo
    from evals.run_worker import run_job

    connection, _ = migrated_db
    factory = sessionmaker(connection, expire_on_commit=False)
    _, checksum = selected_attempts("pilot", ["loan-emi-fixed"], ["2"], 2, 9)
    settings = Settings(_env_file=None, app_env="test")
    with factory() as db, db.begin():
        seed_demo(db)
        job = EvaluationJob(owner_id=demo_id("customer-1"), status="running", manifest={
            "dataset": "pilot", "case_ids": ["loan-emi-fixed"], "cells": ["2"],
            "repeats": 2, "seed": 9, "max_attempts": 2,
            "attempt_count": 2, "dataset_sha256": checksum,
            "runtime": runtime_snapshot(settings),
        })
        db.add(job)
        db.flush()
        job_id = job.id
    connection.commit()
    calls = []

    @contextmanager
    def fake_runtime(settings):
        yield settings, factory

    def fake_execute(_settings, _factory, case, configuration: AgentConfiguration, repeat):
        calls.append((case.id, configuration.agent_count, repeat))
        return {"case_id": case.id, "repeat": repeat, "status": "completed",
                "configuration": configuration.model_dump(), "score": {"passed": True}, "duration_ms": 1}

    run_job(settings, factory, job_id, execute=fake_execute, runtime=fake_runtime)
    run_job(settings, factory, job_id, execute=fake_execute, runtime=fake_runtime)
    with factory() as db:
        assert db.get(EvaluationJob, job_id).status == "completed"
        assert len(db.query(EvaluationAttempt).filter_by(job_id=job_id).all()) == 2
    assert len(calls) == 2
    with pytest.raises(ValueError, match="model or agent code"):
        run_job(settings.model_copy(update={"llm_model": "changed"}), factory, job_id,
                execute=fake_execute, runtime=fake_runtime)


def test_text_comparison_requires_owned_chat_and_cost_acknowledgment(api):
    client, _ = api
    email = f"text-evaluation-{uuid4().hex}@example.org"
    registered = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Text-evaluation-test-password-123", "full_name": "Text Evaluator",
    }).json()
    token = client.post("/api/v1/auth/login", json={
        "email": email, "password": "Text-evaluation-test-password-123",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    settings = client.app.state.settings
    settings.evaluation_owner_customer_id = registered["id"]
    settings.evaluation_live_enabled = True
    settings.llm_provider = "gemini"
    settings.llm_api_key = SecretStr("test-only-fake-key")
    settings.llm_model = "test-model"
    settings.chat_mode = "agents"
    conversation_id = client.post("/api/v1/chat/conversations", headers=headers).json()["id"]
    payload = {"conversation_id": conversation_id, "question": "What is my demo balance?",
               "acknowledge_provider_cost": True}
    without_price = client.post("/api/v1/evaluation/text-comparisons", headers=headers, json=payload)
    assert without_price.status_code == 201
    assert without_price.json()["manifest"]["input_usd_per_million"] is None
    client.post(f"/api/v1/evaluation/jobs/{without_price.json()['id']}/cancel", headers=headers)
    saved = client.post("/api/v1/evaluation/jobs", headers=headers, json={
        "dataset": "pilot", "case_ids": ["loan-emi-fixed"], "cells": ["2"],
        "input_usd_per_million": "1", "output_usd_per_million": "2",
        "price_source": "test price", "price_date": "2026-11-22",
    })
    assert saved.status_code == 201
    assert client.post("/api/v1/evaluation/text-comparisons", headers=headers,
                       json={**payload, "acknowledge_provider_cost": False}).status_code == 422
    assert client.post("/api/v1/evaluation/text-comparisons", headers=headers,
                       json={**payload, "question": "   "}).status_code == 422
    assert client.post("/api/v1/evaluation/text-comparisons", headers=headers,
                       json={**payload, "conversation_id": str(uuid4())}).status_code == 404
    queued = client.post("/api/v1/evaluation/text-comparisons", headers=headers, json=payload)
    assert queued.status_code == 201
    assert queued.json()["status"] == "queued"
    assert queued.json()["manifest"]["cells"] == ["2", "3", "5"]
    assert queued.json()["manifest"]["customer_id"] == registered["id"]
    assert client.post("/api/v1/evaluation/text-comparisons", headers=headers, json=payload).status_code == 409


def test_text_comparison_worker_uses_same_owner_and_question_without_provider(migrated_db, monkeypatch):
    import hashlib
    from contextlib import contextmanager

    from sqlalchemy.orm import sessionmaker

    from app.core.config import Settings
    from app.evaluation import runtime_snapshot
    from app.seed.demo_data import demo_id, seed_demo
    from evals.run_worker import run_job

    connection, _ = migrated_db
    factory = sessionmaker(connection, expire_on_commit=False)
    settings = Settings(_env_file=None, app_env="test", evaluation_cell_cooldown_seconds=2)
    question = "What is my fictional savings balance?"
    owner_id = demo_id("customer-1")
    with factory() as db, db.begin():
        seed_demo(db)
        job = EvaluationJob(owner_id=owner_id, status="running", manifest={
            "dataset": "text", "question": question, "customer_id": str(owner_id),
            "cells": ["2", "3", "5"], "attempt_count": 3,
            "dataset_sha256": hashlib.sha256(question.encode()).hexdigest(),
            "runtime": runtime_snapshot(settings),
        })
        db.add(job)
        db.flush()
        job_id = job.id
    connection.commit()
    calls = []
    pauses = []
    monkeypatch.setattr("evals.run_worker.sleep", pauses.append)

    @contextmanager
    def fake_runtime(_settings, customer_id):
        assert customer_id == owner_id
        yield settings, factory

    def fake_execute(_settings, _factory, case, configuration, repeat, *, customer_id):
        calls.append((case.question, configuration.agent_count, customer_id))
        return {"case_id": case.id, "repeat": repeat, "status": "completed",
                "configuration": configuration.model_dump(), "score": {"passed": True},
                "answer": {"status": "answered", "answer": "Fictional balance"},
                "duration_ms": 1, "usage": {"input_tokens": 10, "output_tokens": 5}}

    run_job(settings, factory, job_id, execute=fake_execute, runtime=fake_runtime)
    with factory() as db:
        attempts = db.query(EvaluationAttempt).filter_by(job_id=job_id).order_by(EvaluationAttempt.position).all()
        assert db.get(EvaluationJob, job_id).status == "completed"
        assert len(attempts) == 3
        assert all(item.result["score"]["passed"] is None for item in attempts)
    assert calls == [(question, count, owner_id) for count in (2, 3, 5)]
    assert pauses == [2, 2]

    with factory() as db, db.begin():
        limited = EvaluationJob(owner_id=owner_id, status="running", manifest=job.manifest)
        db.add(limited)
        db.flush()
        limited_id = limited.id
    connection.commit()

    def quota_execute(_settings, _factory, case, configuration, repeat, *, customer_id):
        return {"case_id": case.id, "repeat": repeat, "status": "failed",
                "configuration": configuration.model_dump(), "error_type": "PROVIDER_QUOTA_EXCEEDED",
                "duration_ms": 1}

    run_job(settings, factory, limited_id, execute=quota_execute, runtime=fake_runtime)
    with factory() as db:
        assert db.get(EvaluationJob, limited_id).status == "failed"
        assert len(db.query(EvaluationAttempt).filter_by(job_id=limited_id).all()) == 1


def test_provider_quota_error_is_classified_without_exposing_provider_text():
    from app.core.errors import APIError
    from evals.run_comparison import safe_error_type

    class QuotaError(Exception):
        code = 429

    try:
        raise APIError(503, "AGENT_UNAVAILABLE", "Safe message") from QuotaError("private provider details")
    except APIError as error:
        assert safe_error_type(error) == "PROVIDER_QUOTA_EXCEEDED"
    assert safe_error_type(ValueError("Different failure")) == "ValueError"
