from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue

from app.schemas import Input

Role = Literal["account", "card", "loan", "support"]
ROLES = ("account", "card", "loan", "support")


class ToolFact(Input):
    call_id: UUID
    tool: str = Field(max_length=40)
    data: dict[str, JsonValue]


class SpecialistSummary(Input):
    status: Literal["answered", "clarification", "needs_tools", "refused"]
    answer: str = Field(min_length=1, max_length=4000)


class Artifact(Input):
    id: UUID
    run_id: UUID
    role: Role
    framework: Literal["CrewAI"] = "CrewAI"
    revision: int = Field(ge=1)
    consumed: list[UUID] = Field(default_factory=list, max_length=4)
    summary: SpecialistSummary
    facts: list[ToolFact] = Field(default_factory=list, max_length=16)


class Delegation(Input):
    run_id: UUID
    role: Role
    task: str = Field(min_length=1, max_length=4000)
    consume: list[UUID] = Field(default_factory=list, max_length=4)


class SupervisorAnswer(Input):
    status: Literal["answered", "clarification", "needs_tools", "refused"]
    answer: str = Field(min_length=1, max_length=4000)


class ProtocolGrant(Input):
    sub: UUID
    run_id: UUID
    role: Role
    exp: int
