"""Frozen pilot cases and deterministic checks; answer quality still needs human review."""

import hashlib
import json
import random
import re
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.agents.configuration import AgentConfiguration
from app.agents.contracts import Artifact, SupervisorAnswer
from app.core.config import ROOT
from app.schemas import Input

PILOT_PATH = ROOT / "data/evaluation/pilot_cases_v1.json"
BENCHMARK_PATH = ROOT / "data/evaluation/benchmark_cases_v1.json"


def runtime_snapshot(settings) -> dict:
    digest = hashlib.sha256()
    for source in sorted((ROOT / "backend/app/agents").glob("*.py")):
        digest.update(source.name.encode())
        digest.update(source.read_bytes())
    return {
        "model_provider": settings.llm_provider,
        "model": settings.llm_model,
        "agent_code_sha256": digest.hexdigest(),
        "frameworks": {name: version(name) for name in ("google-adk", "crewai", "a2a-sdk", "mcp")},
    }


class Scenario(Input):
    id: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    category: Literal[
        "account_transaction", "card", "loan", "policy", "support_dispute",
        "multi_turn_cross_domain", "authorization_confirmation_injection",
    ]
    customer: Literal[1, 2, 3]
    question: str = Field(min_length=1, max_length=2000)
    prior_questions: list[str] = Field(default_factory=list, max_length=3)
    expected_tools: list[str] = Field(max_length=8)
    expected_statuses: list[Literal["answered", "clarification", "needs_tools", "refused"]] = Field(min_length=1)
    expected_facts: list[str] = Field(max_length=8)
    requires_sources_if_answered: bool = False
    dependent_context: bool = False
    forbid_tools: bool = False

    @model_validator(mode="after")
    def safe_expectations(self):
        if self.forbid_tools and self.expected_tools:
            raise ValueError("A no-tool case cannot require tools")
        return self


def load_pilot(path: Path = PILOT_PATH) -> tuple[list[Scenario], str]:
    raw = path.read_bytes()
    cases = [Scenario.model_validate(item) for item in json.loads(raw)]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Scenario IDs must be unique")
    return cases, hashlib.sha256(raw).hexdigest()


def load_benchmark() -> tuple[list[Scenario], str]:
    cases, checksum = load_pilot(BENCHMARK_PATH)
    if len(cases) != 60 or len({case.category for case in cases}) != 7:
        raise ValueError("Benchmark must contain 60 cases across seven categories")
    if not any(case.prior_questions for case in cases if case.category == "multi_turn_cross_domain"):
        raise ValueError("Benchmark needs genuine multi-turn cases")
    return cases, checksum


def pilot_cells() -> list[AgentConfiguration]:
    return [
        AgentConfiguration(agent_count=count) for count in (2, 3, 5)
    ] + [
        AgentConfiguration(agent_count=5, architecture="direct"),
        AgentConfiguration(agent_count=5, prompt_strategy="few_shot"),
    ]


CELL_NAMES = ("2", "3", "5", "direct", "few_shot")


def selected_attempts(dataset: str, case_ids: list[str], cell_names: list[str], repeats: int, seed: int):
    cases, checksum = load_benchmark() if dataset == "benchmark" else load_pilot()
    known = {case.id for case in cases}
    if case_ids and (len(set(case_ids)) != len(case_ids) or not set(case_ids) <= known):
        raise ValueError("Select unique cases from the chosen dataset")
    if not cell_names or len(set(cell_names)) != len(cell_names) or not set(cell_names) <= set(CELL_NAMES):
        raise ValueError("Select unique comparison cells")
    wanted = set(case_ids or known)
    allowed = [pilot_cells()[CELL_NAMES.index(name)] for name in cell_names]
    attempts = [(case, cell, repeat) for case, cell, repeat in schedule(
        [case for case in cases if case.id in wanted], repeats=repeats, seed=seed,
    ) if cell in allowed]
    return attempts, checksum


def schedule(cases: list[Scenario], *, repeats: int = 1, seed: int = 9):
    if not 1 <= repeats <= 3:
        raise ValueError("Repeats must be between 1 and 3")
    attempts = [(case, cell, repeat) for case in cases for repeat in range(1, repeats + 1) for cell in pilot_cells()]
    random.Random(seed).shuffle(attempts)
    return attempts


def score(case: Scenario, answer: SupervisorAnswer, artifacts: list[Artifact], config: AgentConfiguration,
          tool_calls: int | None = None) -> dict:
    facts = [fact for artifact in artifacts for fact in artifact.facts]
    tools = {fact.tool for fact in facts}
    receipts = json.dumps([fact.model_dump(mode="json") for fact in facts], sort_keys=True)
    visible_answer = re.sub(r"[,\s]", "", answer.answer).casefold()
    retrieved_sources = {source.get("citation_id") for fact in facts if fact.tool == "search_policies"
                         for source in fact.data.get("sources", []) if isinstance(source, dict)}
    checks = {
        "status": answer.status in case.expected_statuses,
        "tools": set(case.expected_tools) <= tools,
        "facts": all(value in receipts and re.sub(r"[,\s]", "", value).casefold() in visible_answer
                     for value in case.expected_facts),
        "tool_safety": not case.forbid_tools or (tool_calls == 0 if tool_calls is not None else not tools),
        "sources": not (case.requires_sources_if_answered and answer.status == "answered") or (
            bool(answer.source_ids) and set(answer.source_ids) <= retrieved_sources),
        "dependent_context": not case.dependent_context or config.agent_count == 2 or any(artifact.consumed for artifact in artifacts),
    }
    return {"passed": all(checks.values()), "checks": checks, "human_review_required": True}
