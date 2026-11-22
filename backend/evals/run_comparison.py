"""Isolated, explicitly opt-in provider pilot. Default invocation only prints the manifest."""

import argparse
import asyncio
import json
import socket
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from time import monotonic, sleep
from uuid import uuid4

import uvicorn
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.agents.supervisor import run_supervisor
from app.core.config import ROOT, Settings
from app.evaluation import load_benchmark, load_pilot, pilot_cells, schedule, score
from app.main import create_app
from app.models import (
    Account,
    AgentEvent,
    AgentRun,
    Card,
    Conversation,
    Customer,
    KYCRecord,
    Loan,
    PolicyChunk,
    PolicyDocument,
    SupportTicket,
    Transaction,
)
from app.seed.demo_data import demo_id, seed_demo
from app.services.policies import DIMENSIONS, corpus


def copy_customer_records(source, target, customer_id):
    customer = source.get(Customer, customer_id)
    if customer is None or not customer.is_active:
        raise ValueError("Comparison customer is unavailable")
    target.add(Customer(id=customer_id, full_name="Evaluation customer",
                        email=f"evaluation-{customer_id.hex}@bankai.example",
                        password_hash="disabled", is_active=True))
    target.flush()

    def copy(model, rows):
        columns = [column.key for column in model.__table__.columns]
        target.add_all(model(**{name: getattr(row, name) for name in columns}) for row in rows)
        target.flush()

    accounts = source.scalars(select(Account).where(Account.customer_id == customer_id)).all()
    copy(Account, accounts)
    if accounts:
        copy(Transaction, source.scalars(select(Transaction).where(
            Transaction.account_id.in_([account.id for account in accounts]))).all())
    for model in (Card, KYCRecord, Loan, SupportTicket):
        copy(model, source.scalars(select(model).where(model.customer_id == customer_id)).all())


def safe_error_type(error):
    current = error
    while current is not None:
        if (getattr(current, "code", None) in (429, "RESOURCE_EXHAUSTED")
                or "ResourceExhausted" in type(current).__name__):
            return "PROVIDER_QUOTA_EXCEEDED"
        current = current.__cause__
    return type(error).__name__


@contextmanager
def isolated_runtime(settings, customer_id=None):
    # Generated hex is the only interpolated SQL identifier; every attempt gets a fresh schema.
    schema = "bankai_eval_" + uuid4().hex
    admin = create_engine(settings.database_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    schema_engine = None
    server = None
    thread = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'SET search_path TO "{schema}", public'))
            connection.commit()
            admin.dialect.default_schema_name = schema
            migration = Config(str(ROOT / "backend/alembic.ini"))
            migration.attributes.update(connection=connection, schema=schema)
            command.upgrade(migration, "head")
            connection.commit()
        schema_engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args={"options": f"-c search_path={schema},public -c statement_timeout=3000"},
        )
        factory = sessionmaker(schema_engine, expire_on_commit=False)
        with factory() as db, db.begin():
            seed_demo(db)
            approved = {(name, checksum) for name, checksum, _, _ in corpus()}
            with sessionmaker(admin, expire_on_commit=False)() as source:
                source.execute(text("SET LOCAL search_path TO public"))
                if customer_id is not None:
                    copy_customer_records(source, db, customer_id)
                documents = source.scalars(select(PolicyDocument)).all()
                for document in documents:
                    if (document.source, document.checksum) not in approved:
                        continue
                    chunks = source.scalars(select(PolicyChunk).where(PolicyChunk.document_id == document.id)).all()
                    if not chunks or any(chunk.embedding is None or len(chunk.embedding) != DIMENSIONS for chunk in chunks):
                        continue
                    db.merge(PolicyDocument(id=document.id, title=document.title, source=document.source,
                        checksum=document.checksum, ingested_at=document.ingested_at))
                    db.flush()
                    for chunk in chunks:
                        db.merge(PolicyChunk(id=chunk.id, document_id=document.id, chunk_index=chunk.chunk_index,
                            text=chunk.text, section=chunk.section, embedding=chunk.embedding,
                            embedding_model=chunk.embedding_model, ingested_at=chunk.ingested_at))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        isolated_settings = settings.model_copy(update={
            "app_env": "test", "chat_mode": "agents", "voice_enabled": False,
            "phone_enabled": False, "evaluation_live_enabled": False,
            "agent_base_url": f"http://127.0.0.1:{port}",
        })
        app = create_app(isolated_settings, session_factory=factory)
        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error", access_log=False,
        ))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = monotonic() + 15
        while not server.started and thread.is_alive() and monotonic() < deadline:
            sleep(0.05)
        if not server.started:
            raise RuntimeError("Isolated protocol server could not start")
        yield isolated_settings, factory
    finally:
        if server:
            server.should_exit = True
        if thread:
            thread.join(timeout=10)
        if schema_engine:
            schema_engine.dispose()
        if thread and thread.is_alive():
            raise RuntimeError("Isolated protocol server did not stop; schema retained")
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def execute_case(settings, factory, case, configuration, repeat, customer_id=None):
    customer_id = customer_id or demo_id(f"customer-{case.customer}")
    request_id = str(uuid4())
    with factory() as db, db.begin():
        conversation = Conversation(customer_id=customer_id, title="Isolated evaluation")
        db.add(conversation)
        db.flush()
        conversation_id = conversation.id
    started = monotonic()
    history = []
    all_artifacts = []
    turns = []
    try:
        for question in [*case.prior_questions, case.question]:
            history.append(("user", question))
            answer, artifacts, run_id, usage, duration = asyncio.run(run_supervisor(
                settings, factory, customer_id, conversation_id, str(uuid4()),
                history, configuration,
            ))
            history.append(("assistant", answer.answer))
            all_artifacts.extend(artifacts)
            turns.append({"question": question, "answer": answer.model_dump(mode="json"),
                "run_id": str(run_id), "usage": usage, "duration_ms": duration})
        result = {
            "status": "completed",
            "run_id": str(run_id),
            "answer": answer.model_dump(mode="json"),
            "usage": {key: sum(turn["usage"].get(key) or 0 for turn in turns)
                      if all(turn["usage"].get(key) is not None for turn in turns) else None
                      for key in ("input_tokens", "output_tokens", "total_tokens")},
            "duration_ms": int((monotonic() - started) * 1000),
            "turns": turns,
            "artifacts": [artifact.model_dump(mode="json") for artifact in all_artifacts],
        }
    except Exception as exc:  # noqa: BLE001 -- preserve failed attempts without leaking provider text.
        result = {
            "status": "failed", "error_type": safe_error_type(exc),
            "duration_ms": int((monotonic() - started) * 1000),
            "score": {"passed": False, "checks": {}, "human_review_required": True},
        }
    with factory() as db:
        runs = list(db.scalars(select(AgentRun).where(AgentRun.conversation_id == conversation_id).order_by(AgentRun.created_at)))
        if runs:
            events = list(db.scalars(select(AgentEvent).where(
                AgentEvent.run_id.in_([run.id for run in runs]),
            ).order_by(AgentEvent.sequence)))
            result["run_id"] = str(runs[-1].id)
            result["model_calls"] = sum(run.model_calls for run in runs)
            result["tool_calls"] = sum(run.tool_calls for run in runs)
            result["roles_used"] = sorted({event.role for event in events if event.kind == "agent_start"})
            result["events"] = [
                {"run_id": str(event.run_id), "role": event.role, "kind": event.kind, "payload": event.payload}
                for event in events
            ]
    if result["status"] == "completed":
        result["score"] = score(case, answer, all_artifacts, configuration,
                                tool_calls=result.get("tool_calls", 0))
    return {
        "case_id": case.id, "category": case.category, "repeat": repeat,
        "configuration": configuration.model_dump(), "request_id": request_id,
        **result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly allow Gemini calls")
    parser.add_argument("--dataset", choices=("pilot", "benchmark"), default="pilot")
    parser.add_argument("--case", help="Pilot case ID; required for --live")
    parser.add_argument("--cell", choices=("2", "3", "5", "direct", "few_shot"),
                        help="Run only this comparison cell")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--seed", type=int, default=9)
    args = parser.parse_args()
    cases, checksum = load_benchmark() if args.dataset == "benchmark" else load_pilot()
    chosen = [case for case in cases if case.id == args.case] if args.case else cases
    if not chosen:
        parser.error("Unknown pilot case ID")
    attempts = schedule(chosen, repeats=args.repeats, seed=args.seed)
    cell_names = {
        "2": pilot_cells()[0], "3": pilot_cells()[1], "5": pilot_cells()[2],
        "direct": pilot_cells()[3], "few_shot": pilot_cells()[4],
    }
    if args.cell:
        attempts = [attempt for attempt in attempts if attempt[1] == cell_names[args.cell]]
    manifest = {
        "dataset": f"{args.dataset}_cases_v1", "dataset_sha256": checksum,
        "scenario_count": len(chosen),
        "cells": [cell.model_dump() for cell in (pilot_cells() if not args.cell else [cell_names[args.cell]])],
        "attempt_count": len(attempts), "seed": args.seed,
    }
    if not args.live:
        print(json.dumps({**manifest, "status": "dry_run_no_provider_calls"}, indent=2))
        return
    if not 1 <= args.max_attempts <= 900 or len(attempts) > args.max_attempts:
        parser.error("Live run requires an explicit attempt cap covering all selected cells")
    settings = Settings()
    if not settings.llm_configured:
        parser.error("Gemini provider is not configured in the ignored .env")
    results = []
    for case, configuration, repeat in attempts:
        with isolated_runtime(settings) as (isolated_settings, factory):
            results.append(execute_case(isolated_settings, factory, case, configuration, repeat))
    output = ROOT / f".artifacts/phase9-pilot-{uuid4().hex}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        **manifest, "status": "exploratory_live_pilot",
        "generated_at": datetime.now(UTC).isoformat(), "results": results,
    }, indent=2), encoding="utf-8")
    print(json.dumps({"attempts": len(results), "passed": sum(r["score"]["passed"] for r in results), "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
