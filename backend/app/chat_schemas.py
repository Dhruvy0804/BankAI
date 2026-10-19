from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas import Input, Output


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
    status: Literal["guidance", "needs_tools", "refused"]
    answer: str = Field(min_length=1, max_length=4000)


class ChatReply(Guidance):
    conversation_id: UUID
    message_id: UUID
    request_id: str
    run_id: UUID
    provider: Literal["gemini"]
    model: str
    prompt_version: Literal["phase5-guidance-v1"] = "phase5-guidance-v1"
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    duration_ms: int = Field(ge=0)
    banking_actions_enabled: Literal[False] = False
    sources: list[str] = Field(default_factory=list, max_length=0)
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
    banking_actions_enabled: Literal[False] = False
