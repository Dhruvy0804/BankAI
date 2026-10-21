from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.agents.contracts import ToolFact
from app.schemas import Input, Output, PendingOut
from app.services.policies import PolicySource


class ChatInput(Input):
    conversation_id: UUID
    message_id: UUID
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value.strip()


class Guidance(Input):
    status: Literal[
        "guidance", "needs_tools", "refused", "answered", "clarification", "confirmation_required"
    ]
    answer: str = Field(min_length=1, max_length=4000)


class ChatReply(Guidance):
    conversation_id: UUID
    message_id: UUID
    request_id: str
    run_id: UUID
    provider: Literal["gemini"]
    model: str
    prompt_version: Literal["phase5-guidance-v1", "phase6-blackboard-v1", "phase7-rag-v1"] = (
        "phase5-guidance-v1"
    )
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    duration_ms: int = Field(ge=0)
    banking_actions_enabled: bool = False
    data: list[ToolFact] = Field(default_factory=list, max_length=16)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=4)
    pending_actions: list[PendingOut] = Field(default_factory=list, max_length=16)
    sources: list[PolicySource] = Field(default_factory=list, max_length=8)
    simulated: Literal[True] = True


class ConversationOut(Output):
    id: UUID
    title: str
    created_at: datetime


class TurnOut(Output):
    message_id: UUID
    user_text: str
    response: ChatReply
    created_at: datetime


class ConversationDetail(ConversationOut):
    turns: list[TurnOut]


class ChatStatus(Output):
    configured: bool
    provider: str
    model: str
    banking_actions_enabled: bool = False
    mode: Literal["guidance", "agents"] = "guidance"
    configured_agent_count: Literal[0, 5] = 0
