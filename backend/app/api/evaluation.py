"""Owner-only saved evaluation plans, run evidence, review, and exports."""

import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, select

from app.api.chat import owned_conversation
from app.api.deps import DB, Actor
from app.core.errors import APIError
from app.evaluation import (
    CELL_NAMES,
    load_benchmark,
    load_pilot,
    runtime_snapshot,
    selected_attempts,
)
from app.models import EvaluationAttempt, EvaluationJob
from app.schemas import Input

router = APIRouter(prefix="/api/v1/evaluation", tags=["Private evaluation"])


class PlanInput(Input):
    dataset: Literal["pilot", "benchmark"] = "pilot"
    case_ids: list[str] = Field(default_factory=list, max_length=60)
    cells: list[Literal["2", "3", "5", "direct", "few_shot"]] = Field(default_factory=lambda: list(CELL_NAMES), min_length=1, max_length=5)
    repeats: int = Field(default=1, ge=1, le=3)
    seed: int = Field(default=9, ge=0, le=1_000_000)
    max_attempts: int = Field(default=35, ge=1, le=900)
    input_usd_per_million: Decimal | None = Field(default=None, ge=0, le=1000)
    output_usd_per_million: Decimal | None = Field(default=None, ge=0, le=1000)
    price_source: str = Field(default="", max_length=160)
    price_date: date | None = None

    @model_validator(mode="after")
    def complete_price_snapshot(self):
        supplied = (self.input_usd_per_million is not None, self.output_usd_per_million is not None,
                    bool(self.price_source.strip()), self.price_date is not None)
        if any(supplied) and not all(supplied):
            raise ValueError("Provide both token prices, their source, and date together")
        return self


class StartInput(Input):
    acknowledge_provider_cost: Literal[True]


class ReviewInput(Input):
    quality: int = Field(ge=1, le=5)
    notes: str = Field(default="", max_length=500)


class TextComparisonInput(Input):
    conversation_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    acknowledge_provider_cost: Literal[True]

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank")
        return value.strip()


def owner(request: Request, customer: Actor):
    settings = request.app.state.settings
    configured = settings.evaluation_owner_customer_id or settings.phone_owner_customer_id
    if str(customer.id) != configured or customer.email.endswith("@bankai.example"):
        raise APIError(403, "EVALUATION_OWNER_ONLY", "Only the configured project owner can inspect evaluations.")


def owned_job(db: DB, customer: Actor, job_id: UUID) -> EvaluationJob:
    row = db.scalar(select(EvaluationJob).where(EvaluationJob.id == job_id, EvaluationJob.owner_id == customer.id))
    if row is None:
        raise APIError(404, "EVALUATION_NOT_FOUND", "Evaluation plan not found.")
    return row


def plan(data: PlanInput, settings) -> dict:
    try:
        attempts, checksum = selected_attempts(data.dataset, data.case_ids, data.cells, data.repeats, data.seed)
    except ValueError as exc:
        raise APIError(422, "EVALUATION_SELECTION", str(exc)) from exc
    if len(attempts) > data.max_attempts:
        raise APIError(422, "EVALUATION_BUDGET", "Attempt count exceeds the selected hard cap.")
    return {
        **data.model_dump(mode="json"), "dataset_sha256": checksum, "attempt_count": len(attempts),
        "scenario_count": len({case.id for case, _, _ in attempts}),
        "runtime": runtime_snapshot(settings),
        "status": "plan_only_no_provider_calls",
    }


@router.get("/config")
def config(request: Request, customer: Actor):
    owner(request, customer)
    return {
        "live_enabled": request.app.state.settings.evaluation_live_enabled,
        "cells": list(CELL_NAMES),
        "datasets": {
            name: [{"id": case.id, "category": case.category, "question": case.question,
                    "expected_statuses": case.expected_statuses, "expected_tools": case.expected_tools}
                   for case in loader()[0]]
            for name, loader in (("pilot", load_pilot), ("benchmark", load_benchmark))
        },
    }


@router.post("/preview")
def preview(data: PlanInput, request: Request, customer: Actor):
    owner(request, customer)
    return plan(data, request.app.state.settings)


@router.post("/jobs", status_code=201)
def save_plan(data: PlanInput, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    manifest = plan(data, request.app.state.settings)
    row = EvaluationJob(owner_id=customer.id, status="planned", manifest=manifest)
    db.add(row)
    db.flush()
    return {"id": row.id, "status": row.status, "manifest": row.manifest}


@router.post("/text-comparisons", status_code=201)
def compare_text(data: TextComparisonInput, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    settings = request.app.state.settings
    if not settings.evaluation_live_enabled or not settings.llm_configured or settings.chat_mode != "agents":
        raise APIError(503, "EVALUATION_LIVE_DISABLED", "Live text comparison is unavailable.")
    owned_conversation(db, customer, data.conversation_id)
    active = db.scalar(select(func.count()).select_from(EvaluationJob).where(
        EvaluationJob.status.in_(("queued", "running", "cancel_requested"))))
    if active:
        raise APIError(409, "EVALUATION_BUSY", "Another evaluation is still active.")
    runtime = runtime_snapshot(settings)
    priced = next((row.manifest for row in db.scalars(select(EvaluationJob).where(
        EvaluationJob.owner_id == customer.id).order_by(EvaluationJob.created_at.desc()).limit(30))
        if row.manifest.get("runtime") == runtime and row.manifest.get("input_usd_per_million") is not None
        and row.manifest.get("output_usd_per_million") is not None and row.manifest.get("price_date")), None)
    manifest = {
        "dataset": "text", "question": data.question, "conversation_id": str(data.conversation_id),
        "customer_id": str(customer.id), "cells": ["2", "3", "5"], "repeats": 1, "seed": 9,
        "max_attempts": 3, "attempt_count": 3, "scenario_count": 1,
        "dataset_sha256": hashlib.sha256(data.question.encode()).hexdigest(),
        "runtime": runtime, "status": "live_text_comparison",
        **{key: priced.get(key) if priced else None for key in (
            "input_usd_per_million", "output_usd_per_million", "price_source", "price_date")},
    }
    row = EvaluationJob(owner_id=customer.id, status="queued", manifest=manifest)
    db.add(row)
    db.flush()
    return {"id": row.id, "status": row.status, "manifest": row.manifest}


@router.get("/jobs")
def jobs(request: Request, db: DB, customer: Actor):
    owner(request, customer)
    rows = db.scalars(select(EvaluationJob).where(EvaluationJob.owner_id == customer.id)
        .order_by(EvaluationJob.created_at.desc()).limit(30)).all()
    return [{"id": row.id, "status": row.status, "manifest": row.manifest,
             "created_at": row.created_at, "error": row.error} for row in rows]


@router.get("/jobs/{job_id}")
def job(job_id: UUID, request: Request, db: DB, customer: Actor,
        offset: int = Query(default=0, ge=0, le=900), limit: int = Query(default=20, ge=1, le=100)):
    owner(request, customer)
    row = owned_job(db, customer, job_id)
    attempts = db.scalars(select(EvaluationAttempt).where(EvaluationAttempt.job_id == row.id)
        .order_by(EvaluationAttempt.position).offset(offset).limit(limit)).all()
    summaries = db.scalars(select(EvaluationAttempt.result).where(EvaluationAttempt.job_id == row.id)).all()
    cells = {}
    rates = (row.manifest.get("input_usd_per_million"), row.manifest.get("output_usd_per_million"))
    priced = all(rate is not None for rate in rates)
    for item in summaries:
        cfg = item.get("configuration", {})
        key = f"{cfg.get('agent_count', '?')} / {cfg.get('architecture', '?')} / {cfg.get('prompt_strategy', '?')}"
        metric = cells.setdefault(key, {"attempts": 0, "passed": 0, "failed": 0, "duration_ms": 0,
                                        "input_tokens": 0, "output_tokens": 0, "usage_complete": True,
                                        "model_calls": 0, "tool_calls": 0, "calls_complete": True})
        metric["attempts"] += 1
        metric["passed"] += int(bool(item.get("score", {}).get("passed")))
        metric["failed"] += int(item.get("status") != "completed")
        metric["duration_ms"] += item.get("duration_ms", 0)
        usage = item.get("usage", {})
        for token in ("input_tokens", "output_tokens"):
            if usage.get(token) is None:
                metric["usage_complete"] = False
            else:
                metric[token] += usage[token]
        for count in ("model_calls", "tool_calls"):
            if item.get(count) is None:
                metric["calls_complete"] = False
            else:
                metric[count] += item[count]
    for metric in cells.values():
        metric["estimated_cost_usd"] = (str((
            Decimal(metric["input_tokens"]) * Decimal(str(rates[0]))
            + Decimal(metric["output_tokens"]) * Decimal(str(rates[1]))) / Decimal(1_000_000))
            if priced and metric["usage_complete"] else None)
    known_costs = [Decimal(metric["estimated_cost_usd"]) for metric in cells.values()
                   if metric["estimated_cost_usd"] is not None]
    return {
        "id": row.id, "status": row.status, "manifest": row.manifest, "error": row.error,
        "created_at": row.created_at, "completed_count": len(summaries),
        "passed_count": sum(bool(item.get("score", {}).get("passed")) for item in summaries),
        "duration_ms": sum(item.get("duration_ms", 0) for item in summaries),
        "cell_metrics": cells,
        "projected_cost_usd": str(sum(known_costs) * Decimal(row.manifest["attempt_count"])
                                  / Decimal(len(summaries))) if priced and len(known_costs) == len(cells)
                                  and summaries else None,
        "attempts": [{"id": item.id, "position": item.position, "result": item.result,
                      "review": item.review} for item in attempts],
    }


@router.get("/jobs/{job_id}/compare")
def compare(job_id: UUID, case_id: str, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    row = owned_job(db, customer, job_id)
    scenarios = load_benchmark()[0] if row.manifest["dataset"] == "benchmark" else load_pilot()[0]
    scenario = next((item for item in scenarios if item.id == case_id), None)
    if scenario is None or (row.manifest["case_ids"] and case_id not in row.manifest["case_ids"]):
        raise APIError(404, "EVALUATION_CASE_NOT_FOUND", "Scenario not in this evaluation.")
    attempts = db.scalars(select(EvaluationAttempt).where(
        EvaluationAttempt.job_id == row.id,
        EvaluationAttempt.result["case_id"].astext == case_id,
    ).order_by(EvaluationAttempt.position).limit(15)).all()
    return {"scenario": scenario.model_dump(mode="json"),
            "attempts": [{"id": item.id, "position": item.position, "result": item.result,
                          "review": item.review} for item in attempts]}


@router.post("/jobs/{job_id}/start")
def start(job_id: UUID, data: StartInput, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    settings = request.app.state.settings
    if not settings.evaluation_live_enabled or not settings.llm_configured or settings.chat_mode != "agents":
        raise APIError(503, "EVALUATION_LIVE_DISABLED", "Live evaluation is disabled or its provider is unavailable.")
    row = owned_job(db, customer, job_id)
    if row.status not in ("planned", "interrupted"):
        raise APIError(409, "EVALUATION_STATE", "Only a planned or interrupted evaluation can be started.")
    manifest = row.manifest
    if manifest.get("runtime") != runtime_snapshot(settings):
        raise APIError(409, "EVALUATION_RUNTIME_CHANGED", "The model or agent code changed. Save a new plan.")
    if manifest.get("input_usd_per_million") is None:
        raise APIError(422, "EVALUATION_PRICE_MISSING", "Save a plan with a dated token-price snapshot before a live run.")
    if selected_attempts(manifest["dataset"], manifest["case_ids"], manifest["cells"],
                         manifest["repeats"], manifest["seed"])[1] != manifest["dataset_sha256"]:
        raise APIError(409, "EVALUATION_DATA_CHANGED", "The scenario dataset changed. Save a new plan.")
    active = db.scalar(select(func.count()).select_from(EvaluationJob).where(
        EvaluationJob.status.in_(("queued", "running", "cancel_requested"))))
    if active:
        raise APIError(409, "EVALUATION_BUSY", "Another evaluation is still active.")
    row.status = "queued"
    return {"id": row.id, "status": row.status}


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: UUID, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    row = owned_job(db, customer, job_id)
    if row.status in ("planned", "queued", "interrupted"):
        row.status = "cancelled"
    elif row.status == "running":
        row.status = "cancel_requested"
    return {"id": row.id, "status": row.status}


@router.post("/jobs/{job_id}/attempts/{attempt_id}/review")
def review(job_id: UUID, attempt_id: UUID, data: ReviewInput, request: Request, db: DB, customer: Actor):
    owner(request, customer)
    row = owned_job(db, customer, job_id)
    attempt = db.scalar(select(EvaluationAttempt).where(
        EvaluationAttempt.id == attempt_id, EvaluationAttempt.job_id == row.id))
    if attempt is None:
        raise APIError(404, "EVALUATION_ATTEMPT_NOT_FOUND", "Evaluation attempt not found.")
    attempt.review = data.model_dump()
    return {"id": attempt.id, "review": attempt.review}


@router.get("/jobs/{job_id}/export")
def export(job_id: UUID, request: Request, db: DB, customer: Actor,
           format: Literal["json", "csv", "md"] = "json"):
    owner(request, customer)
    row = owned_job(db, customer, job_id)
    attempts = db.scalars(select(EvaluationAttempt).where(EvaluationAttempt.job_id == row.id)
        .order_by(EvaluationAttempt.position)).all()
    items = [{"position": item.position, "result": item.result, "review": item.review} for item in attempts]
    rates = (row.manifest.get("input_usd_per_million"), row.manifest.get("output_usd_per_million"))

    def cost(result):
        usage = result.get("usage", {})
        if any(value is None for value in (*rates, usage.get("input_tokens"), usage.get("output_tokens"))):
            return None
        return str((Decimal(usage["input_tokens"]) * Decimal(str(rates[0]))
                    + Decimal(usage["output_tokens"]) * Decimal(str(rates[1]))) / Decimal(1_000_000))

    if format == "json":
        content = json.dumps({"manifest": row.manifest, "status": row.status,
                              "attempts": items}, indent=2, default=str)
    elif format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(("position", "case_id", "repeat", "agent_count", "architecture",
                         "prompt", "status", "passed", "duration_ms", "input_tokens",
                         "output_tokens", "model_calls", "tool_calls", "estimated_cost_usd", "quality"))
        for item in items:
            result = item["result"]
            configuration = result.get("configuration", {})
            usage = result.get("usage", {})
            writer.writerow((item["position"], result.get("case_id"), result.get("repeat"),
                configuration.get("agent_count"), configuration.get("architecture"),
                configuration.get("prompt_strategy"), result.get("status"),
                result.get("score", {}).get("passed"), result.get("duration_ms"),
                usage.get("input_tokens"), usage.get("output_tokens"),
                result.get("model_calls"), result.get("tool_calls"), cost(result),
                (item["review"] or {}).get("quality")))
        content = out.getvalue()
    else:
        lines = ["# BankAI evaluation", "", f"Status: {row.status}",
                 f"Dataset: {row.manifest['dataset']} ({row.manifest['dataset_sha256']})",
                 f"Attempts: {len(items)}/{row.manifest['attempt_count']}",
                 f"Deterministic passes: {sum(bool(item['result'].get('score', {}).get('passed')) for item in items)}",
                 f"Token price snapshot: {row.manifest.get('price_source') or 'unavailable'} ({row.manifest.get('price_date') or 'undated'})",
                 f"Estimated token cost USD: {sum((Decimal(cost(item['result'])) for item in items), Decimal(0)) if items and all(cost(item['result']) is not None for item in items) else 'unavailable'}",
                 "", "| Case | Agents | Architecture | Prompt | Result | Pass | Time (ms) | Input tokens | Output tokens | Model calls | Tool calls | Est. USD | Quality |",
                 "|---|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
        for item in items:
            result = item["result"]
            cfg = result.get("configuration", {})
            usage = result.get("usage", {})
            lines.append("| " + " | ".join(str(value) for value in (
                result.get("case_id", ""), cfg.get("agent_count", ""), cfg.get("architecture", ""),
                cfg.get("prompt_strategy", ""), result.get("status", ""),
                result.get("score", {}).get("passed", ""), result.get("duration_ms", ""),
                usage.get("input_tokens", ""), usage.get("output_tokens", ""),
                result.get("model_calls", ""), result.get("tool_calls", ""),
                cost(result) or "", (item["review"] or {}).get("quality", ""))) + " |")
        lines.extend(("", "Scores check receipts and fixtures; answer quality requires human review.", ""))
        content = "\n".join(lines)
    return {"format": format, "content": content, "filename": f"bankai-evaluation-{job_id}.{format}"}
