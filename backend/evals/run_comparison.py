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
from app.evaluation import load_pilot, pilot_cells, schedule, score
from app.main import create_app
from app.models import AgentEvent, AgentRun, Conversation
from app.seed.demo_data import demo_id, seed_demo


@contextmanager
def isolated_runtime(settings):
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
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        isolated_settings = settings.model_copy(update={
            "app_env": "test", "chat_mode": "agents", "voice_enabled": False,
            "phone_enabled": False, "agent_base_url": f"http://127.0.0.1:{port}",
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


def execute_case(settings, factory, case, configuration, repeat):
    customer_id = demo_id(f"customer-{case.customer}")
    request_id = str(uuid4())
    with factory() as db, db.begin():
        conversation = Conversation(customer_id=customer_id, title="Isolated evaluation")
        db.add(conversation)
        db.flush()
        conversation_id = conversation.id
    started = monotonic()
    try:
        answer, artifacts, run_id, usage, duration = asyncio.run(run_supervisor(
            settings, factory, customer_id, conversation_id, request_id,
            [("user", case.question)], configuration,
        ))
        result = {
            "status": "completed",
            "run_id": str(run_id),
            "answer": answer.model_dump(mode="json"),
            "score": score(case, answer, artifacts, configuration),
            "usage": usage,
            "duration_ms": duration,
            "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
        }
    except Exception as exc:  # noqa: BLE001 -- preserve failed attempts without leaking provider text.
        result = {
            "status": "failed", "error_type": type(exc).__name__,
            "duration_ms": int((monotonic() - started) * 1000),
            "score": {"passed": False, "checks": {}, "human_review_required": True},
        }
    with factory() as db:
        run = db.scalar(select(AgentRun).where(
            AgentRun.conversation_id == conversation_id,
        ).order_by(AgentRun.created_at.desc()).limit(1))
        if run:
            events = list(db.scalars(select(AgentEvent).where(
                AgentEvent.run_id == run.id,
            ).order_by(AgentEvent.sequence)))
            result["run_id"] = str(run.id)
            result["model_calls"] = run.model_calls
            result["tool_calls"] = run.tool_calls
            result["roles_used"] = sorted({event.role for event in events if event.kind == "agent_start"})
            result["events"] = [
                {"role": event.role, "kind": event.kind, "payload": event.payload}
                for event in events
            ]
    return {
        "case_id": case.id, "category": case.category, "repeat": repeat,
        "configuration": configuration.model_dump(), "request_id": request_id,
        **result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly allow Gemini calls")
    parser.add_argument("--case", help="Pilot case ID; required for --live")
    parser.add_argument("--cell", choices=("2", "3", "5", "direct", "few_shot"),
                        help="Run only this comparison cell")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--seed", type=int, default=9)
    args = parser.parse_args()
    cases, checksum = load_pilot()
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
        "dataset": "pilot_cases_v1", "dataset_sha256": checksum,
        "scenario_count": len(chosen),
        "cells": [cell.model_dump() for cell in (pilot_cells() if not args.cell else [cell_names[args.cell]])],
        "attempt_count": len(attempts), "seed": args.seed,
    }
    if not args.live:
        print(json.dumps({**manifest, "status": "dry_run_no_provider_calls"}, indent=2))
        return
    if args.case is None or not 1 <= args.max_attempts <= 5 or len(attempts) > args.max_attempts:
        parser.error("Live pilot requires one --case and a 1–5 attempt cap covering the selected cells")
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
