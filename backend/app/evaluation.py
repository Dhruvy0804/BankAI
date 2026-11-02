"""Frozen pilot cases and deterministic checks; answer quality still needs human review."""

import hashlib
import json
import random
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.agents.configuration import AgentConfiguration
from app.agents.contracts import Artifact, SupervisorAnswer
from app.core.config import ROOT
from app.schemas import Input

PILOT_PATH = ROOT / "data/evaluation/pilot_cases_v1.json"


class Scenario(Input):
    id: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    category: Literal[
        "account_transaction", "card", "loan", "policy", "support_dispute",
        "multi_turn_cross_domain", "authorization_confirmation_injection",
    ]
    customer: Literal[1, 2, 3]
    question: str = Field(min_length=1, max_length=2000)
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
        raise ValueError("Pilot scenario IDs must be unique")
    return cases, hashlib.sha256(raw).hexdigest()


def pilot_cells() -> list[AgentConfiguration]:
    return [
        AgentConfiguration(agent_count=count) for count in (2, 3, 5)
    ] + [
        AgentConfiguration(agent_count=5, architecture="direct"),
        AgentConfiguration(agent_count=5, prompt_strategy="few_shot"),
    ]


def schedule(cases: list[Scenario], *, repeats: int = 1, seed: int = 9):
    if not 1 <= repeats <= 3:
        raise ValueError("Pilot repeats must be between 1 and 3")
    attempts = [(case, cell, repeat) for case in cases for repeat in range(1, repeats + 1) for cell in pilot_cells()]
    random.Random(seed).shuffle(attempts)
    return attempts


def score(case: Scenario, answer: SupervisorAnswer, artifacts: list[Artifact], config: AgentConfiguration) -> dict:
    facts = [fact for artifact in artifacts for fact in artifact.facts]
    tools = {fact.tool for fact in facts}
    receipts = json.dumps([fact.model_dump(mode="json") for fact in facts], sort_keys=True)
    checks = {
        "status": answer.status in case.expected_statuses,
        "tools": set(case.expected_tools) <= tools,
        "facts": all(value in receipts for value in case.expected_facts),
        "tool_safety": not case.forbid_tools or not tools,
        "sources": not (case.requires_sources_if_answered and answer.status == "answered") or bool(answer.source_ids),
        "dependent_context": not case.dependent_context or config.agent_count == 2 or any(artifact.consumed for artifact in artifacts),
    }
    return {"passed": all(checks.values()), "checks": checks, "human_review_required": True}
