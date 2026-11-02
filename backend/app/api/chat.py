from time import monotonic
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.agents.configuration import AgentConfiguration
from app.api.deps import DB, Actor
from app.chat_schemas import (
    ChatInput,
    ChatReply,
    ChatStatus,
    ConversationDetail,
    ConversationOut,
    Guidance,
    TurnOut,
)
from app.core.errors import APIError
from app.models import AgentArtifact, AgentEvent, AgentRun, AuditLog, ChatTurn, Conversation
from app.schemas import PendingOut
from app.services.policies import policy_sources

router = APIRouter(prefix="/api/v1", tags=["Text chat"])


def owned_conversation(db, customer, conversation_id, *, lock=False):
    query = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.customer_id == customer.id
    )
    try:
        obj = db.scalar(query.with_for_update(nowait=True, key_share=True) if lock else query)
    except OperationalError as exc:
        if getattr(exc.orig, "sqlstate", None) != "55P03":
            raise
        raise APIError(
            409, "CHAT_BUSY", "A response is already being generated. Refresh shortly."
        ) from exc
    if obj is None:
        raise APIError(404, "NOT_FOUND", "Conversation not found.")
    return obj


@router.get("/chat/status", response_model=ChatStatus)
def status(request: Request, customer: Actor):
    settings = request.app.state.settings
    return ChatStatus(
        configured=settings.llm_configured,
        provider=settings.llm_provider,
        model=settings.llm_model,
        mode=settings.chat_mode,
        configured_agent_count=5 if settings.chat_mode == "agents" else 0,
        banking_actions_enabled=settings.chat_mode == "agents",
        voice_configured=settings.voice_configured,
        phone_configured=settings.phone_configured and str(customer.id) == settings.phone_owner_customer_id,
    )


@router.get("/chat/conversations", response_model=list[ConversationOut])
def conversations(db: DB, customer: Actor, offset: int = Query(default=0, ge=0, le=100000)):
    return db.scalars(
        select(Conversation)
        .where(Conversation.customer_id == customer.id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .offset(offset)
        .limit(50)
    ).all()


@router.post("/chat/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(db: DB, customer: Actor):
    conversation = Conversation(customer_id=customer.id, title="New conversation")
    db.add(conversation)
    db.flush()
    return conversation


@router.get("/chat/conversations/{conversation_id}", response_model=ConversationDetail)
def conversation_detail(conversation_id: UUID, db: DB, customer: Actor):
    obj = owned_conversation(db, customer, conversation_id)
    turns = db.scalars(
        select(ChatTurn).where(ChatTurn.conversation_id == obj.id).order_by(ChatTurn.position)
    ).all()
    return ConversationDetail(
        **ConversationOut.model_validate(obj).model_dump(),
        turns=[TurnOut.model_validate(turn) for turn in turns],
    )


@router.post("/chat", response_model=ChatReply)
def chat(data: ChatInput, request: Request, db: DB, customer: Actor):
    obj = owned_conversation(db, customer, data.conversation_id, lock=True)
    previous = db.scalar(
        select(ChatTurn).where(
            ChatTurn.conversation_id == obj.id, ChatTurn.message_id == data.message_id
        )
    )
    if previous:
        if previous.user_text != data.message:
            raise APIError(409, "MESSAGE_CONFLICT", "Use a new message ID for a different message.")
        return ChatReply.model_validate(previous.response)
    recent = list(
        reversed(
            db.scalars(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == obj.id)
                .order_by(ChatTurn.position.desc())
                .limit(10)
            ).all()
        )
    )
    position = recent[-1].position + 1 if recent else 1
    if position > 100:
        raise APIError(409, "CONVERSATION_FULL", "Start a new conversation to continue.")
    request.app.state.chat_limiter.check(str(customer.id))
    history = []
    for turn in recent:
        history.extend(
            [
                ("user", turn.user_text),
                (
                    "model",
                    Guidance.model_validate(
                        {"status": turn.response["status"], "answer": turn.response["answer"]}
                    ).model_dump_json(),
                ),
            ]
        )
    history.append(("user", data.message))
    started = monotonic()
    try:
        if request.app.state.settings.chat_mode == "agents":
            import asyncio

            from app.agents.supervisor import run_supervisor

            if not request.app.state.agent_slots.acquire(blocking=False):
                raise APIError(429, "AGENT_BUSY", "The agent service is busy. Try again shortly.")
            try:
                answer, artifacts, run_id, usage, duration = asyncio.run(
                    run_supervisor(
                        request.app.state.settings,
                        request.app.state.session_factory,
                        customer.id,
                        obj.id,
                        request.state.request_id,
                        history,
                    )
                )
            finally:
                request.app.state.agent_slots.release()
            facts = [fact for artifact in artifacts for fact in artifact.facts]
            pending = [
                PendingOut.model_validate(fact.data)
                for fact in facts
                if fact.tool in ("prepare_card_block", "prepare_loan_application")
            ]
            reply = ChatReply(
                status="confirmation_required" if pending else answer.status,
                answer=answer.answer,
                conversation_id=obj.id,
                message_id=data.message_id,
                request_id=request.state.request_id,
                run_id=run_id,
                provider="gemini",
                model=request.app.state.settings.llm_model,
                prompt_version="phase7-rag-v1",
                duration_ms=duration,
                banking_actions_enabled=True,
                data=facts,
                artifact_ids=[artifact.id for artifact in artifacts],
                pending_actions=pending,
                sources=[
                    source
                    for key, source in policy_sources(facts).items()
                    if key in answer.source_ids
                ],
                **usage,
            )
        else:
            result = request.app.state.llm_provider.generate(history)
            reply = ChatReply(
                **result.guidance.model_dump(),
                conversation_id=obj.id,
                message_id=data.message_id,
                request_id=request.state.request_id,
                run_id=uuid4(),
                provider="gemini",
                model=request.app.state.settings.llm_model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                duration_ms=int((monotonic() - started) * 1000),
            )
    except APIError as error:
        error.actor = customer.id
        error.action = "chat_failed"
        error.resource_type = "conversations"
        error.resource_id = obj.id
        raise
    db.add(
        ChatTurn(
            conversation_id=obj.id,
            message_id=data.message_id,
            position=position,
            user_text=data.message,
            response=reply.model_dump(mode="json"),
        )
    )
    if position == 1:
        obj.title = data.message[:80]
    db.add(
        AuditLog(
            customer_id=customer.id,
            action="chat_completed",
            resource_type="conversations",
            resource_id=obj.id,
            outcome="success",
            request_id=request.state.request_id,
        )
    )
    db.flush()
    return reply


@router.get("/chat/runs/{run_id}")
def run_trace(run_id: UUID, db: DB, customer: Actor):
    run = db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.customer_id == customer.id)
    )
    if run is None:
        raise APIError(404, "NOT_FOUND", "Agent run not found.")
    configuration = AgentConfiguration.model_validate(run.configuration)
    return {
        "run_id": run.id,
        "request_id": run.request_id,
        "status": run.status,
        "configuration": configuration.model_dump(),
        "configured_roles": {"supervisor": "Google ADK"} | {
            role: "CrewAI" for role in configuration.roles
        },
        "model": run.model,
        "revision": run.revision,
        "model_calls": run.model_calls,
        "tool_calls": run.tool_calls,
        "total_tokens": run.total_tokens if run.usage_complete else None,
        "artifacts": [
            row.payload
            for row in db.scalars(
                select(AgentArtifact)
                .where(AgentArtifact.run_id == run.id)
                .order_by(AgentArtifact.revision)
            )
        ],
        "events": [
            {
                "id": row.id,
                "sequence": row.sequence,
                "at": row.created_at,
                "role": row.role,
                "kind": row.kind,
                "metadata": row.payload,
            }
            for row in db.scalars(
                select(AgentEvent)
                .where(AgentEvent.run_id == run.id)
                .order_by(AgentEvent.sequence)
                .limit(500)
            )
        ],
    }


@router.post("/chat/runs/{run_id}/cancel")
def cancel_run(run_id: UUID, db: DB, customer: Actor):
    run = db.scalar(
        select(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.customer_id == customer.id,
        )
        .with_for_update()
    )
    if run is None:
        raise APIError(404, "NOT_FOUND", "Agent run not found.")
    if run.status == "running":
        run.status = "cancelled"
        db.add(AgentEvent(run_id=run.id, role="supervisor", kind="cancel_requested", payload={}))
    return {"run_id": run.id, "status": run.status}
