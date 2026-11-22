"""Process explicitly queued evaluation jobs; never run without the live gate."""

import hashlib
from time import sleep
from uuid import UUID

from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import sessionmaker

from app.agents.configuration import AgentConfiguration
from app.core.config import Settings
from app.evaluation import Scenario, runtime_snapshot, selected_attempts
from app.models import EvaluationAttempt, EvaluationJob
from evals.run_comparison import execute_case, isolated_runtime

WORKER_LOCK = 2026112009


def run_job(settings, factory, job_id: UUID, execute=execute_case, runtime=isolated_runtime):
    with factory() as db:
        job = db.get(EvaluationJob, job_id)
        manifest = job.manifest
        customer_id = job.owner_id
    if manifest["dataset"] == "text":
        if manifest.get("customer_id") != str(customer_id) or manifest.get("cells") != ["2", "3", "5"]:
            raise ValueError("Invalid text comparison owner or agent configuration")
        case = Scenario(id="custom-text", category="multi_turn_cross_domain", customer=1,
                        question=manifest["question"], expected_statuses=[
                            "answered", "clarification", "needs_tools", "refused"],
                        expected_tools=[], expected_facts=[])
        attempts = [(case, AgentConfiguration(agent_count=count), 1) for count in (2, 3, 5)]
        checksum = hashlib.sha256(case.question.encode()).hexdigest()
    else:
        attempts, checksum = selected_attempts(manifest["dataset"], manifest["case_ids"],
            manifest["cells"], manifest["repeats"], manifest["seed"])
    if checksum != manifest["dataset_sha256"] or len(attempts) != manifest["attempt_count"]:
        raise ValueError("Saved evaluation manifest no longer matches its dataset")
    if manifest.get("runtime") != runtime_snapshot(settings):
        raise ValueError("Saved evaluation manifest no longer matches the model or agent code")
    for position, (case, configuration, repeat) in enumerate(attempts, 1):
        if manifest["dataset"] == "text" and position > 1:
            remaining = settings.evaluation_cell_cooldown_seconds
            while remaining > 0:
                interval = min(5, remaining)
                sleep(interval)
                remaining -= interval
                with factory() as db:
                    status = db.get(EvaluationJob, job_id).status
                    if status == "cancel_requested":
                        db.execute(update(EvaluationJob).where(EvaluationJob.id == job_id)
                                   .values(status="cancelled"))
                        db.commit()
                        return
                    if status != "running":
                        return
        with factory() as db:
            job = db.get(EvaluationJob, job_id)
            if job.status == "cancel_requested":
                job.status = "cancelled"
                db.commit()
                return
            if job.status != "running":
                return
            if db.scalar(select(EvaluationAttempt.id).where(
                EvaluationAttempt.job_id == job_id, EvaluationAttempt.position == position)):
                continue
        runtime_context = runtime(settings, customer_id) if manifest["dataset"] == "text" else runtime(settings)
        with runtime_context as (isolated_settings, isolated_factory):
            if manifest["dataset"] == "text":
                result = execute(isolated_settings, isolated_factory, case, configuration, repeat,
                                 customer_id=customer_id)
            else:
                result = execute(isolated_settings, isolated_factory, case, configuration, repeat)
        if manifest["dataset"] == "text":
            result["score"] = {"passed": None, "checks": {}, "human_review_required": True}
        with factory() as db:
            db.add(EvaluationAttempt(job_id=job_id, position=position, result=result))
            if result.get("error_type") == "PROVIDER_QUOTA_EXCEEDED":
                job = db.get(EvaluationJob, job_id)
                job.status = "failed"
                job.error = "PROVIDER_QUOTA_EXCEEDED"
            db.commit()
        if result.get("error_type") == "PROVIDER_QUOTA_EXCEEDED":
            return
    with factory() as db:
        job = db.get(EvaluationJob, job_id)
        job.status = "cancelled" if job.status == "cancel_requested" else "completed"
        db.commit()


def work_forever(settings: Settings, interval: float = 2):
    if not settings.evaluation_live_enabled or not settings.llm_configured or settings.chat_mode != "agents":
        raise RuntimeError("Live evaluation is disabled or its provider is unavailable")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        with engine.connect() as guard:
            if not guard.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK}):
                raise RuntimeError("Another evaluation worker is already running")
            guard.commit()
            with factory() as db:
                db.execute(update(EvaluationJob).where(EvaluationJob.status == "running")
                           .values(status="interrupted", error="worker_restarted_review_before_resume"))
                db.execute(update(EvaluationJob).where(EvaluationJob.status == "cancel_requested")
                           .values(status="cancelled"))
                db.commit()
            while True:
                with factory() as db:
                    job = db.scalar(select(EvaluationJob).where(EvaluationJob.status == "queued")
                        .order_by(EvaluationJob.created_at).limit(1))
                    if job:
                        job.status = "running"
                        job.error = None
                        job_id = job.id
                        db.commit()
                    else:
                        job_id = None
                if job_id is None:
                    sleep(interval)
                    continue
                try:
                    run_job(settings, factory, job_id)
                except Exception as exc:  # noqa: BLE001 -- persist safe failure type, not provider text.
                    with factory() as db:
                        job = db.get(EvaluationJob, job_id)
                        if job and job.status == "running":
                            job.status = "failed"
                            job.error = type(exc).__name__
                            db.commit()
    finally:
        engine.dispose()


if __name__ == "__main__":
    work_forever(Settings())
