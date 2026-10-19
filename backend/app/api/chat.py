from time import monotonic
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

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
from app.models import AuditLog, ChatTurn, Conversation

router = APIRouter(prefix="/api/v1", tags=["Text chat"])


def owned_conversation(db, customer, conversation_id, *, lock=False):
    query = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.customer_id == customer.id
    )
    try:
        obj = db.scalar(query.with_for_update(nowait=True) if lock else query)
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
        configured=settings.llm_configured, provider=settings.llm_provider, model=settings.llm_model
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
        result = request.app.state.llm_provider.generate(history)
    except APIError as error:
        error.actor = customer.id
        error.action = "chat_failed"
        error.resource_type = "conversations"
        error.resource_id = obj.id
        raise
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
