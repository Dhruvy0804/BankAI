from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.chat_schemas import Guidance
from app.core.config import Settings
from app.core.errors import APIError
from app.models import AuditLog, ChatTurn, Conversation, PendingAction
from app.services.llm import ModelResult
from tests.integration.test_banking_api import login

pytestmark = pytest.mark.integration


class FakeProvider:
    """Explicit test double, never selected by application configuration."""

    def __init__(self):
        self.histories = []
        self.failure = None

    def generate(self, history):
        self.histories.append(history)
        if self.failure:
            raise self.failure
        return ModelResult(
            Guidance(status="needs_tools", answer="Use the Accounts page for your balance."),
            input_tokens=10,
            output_tokens=8,
            total_tokens=18,
        )


def conversation(client, auth):
    response = client.post("/api/v1/chat/conversations", json={}, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(client, auth, cid, message="What is my balance?", message_id=None):
    return client.post(
        "/api/v1/chat",
        headers=auth,
        json={
            "conversation_id": cid,
            "message_id": str(message_id or uuid4()),
            "message": message,
        },
    )


def test_persistent_context_retry_and_customer_isolation(api):
    client, connection = api
    fake = FakeProvider()
    client.app.state.llm_provider = fake
    auth = login(client)
    other = login(client, "ravi")
    cid = conversation(client, auth)
    mid = str(uuid4())
    first = send(client, auth, cid, message_id=mid)
    assert first.status_code == 200, first.text
    assert first.json()["banking_actions_enabled"] is False
    assert first.json()["sources"] == []
    assert first.json()["total_tokens"] == 18
    retry = send(client, auth, cid, message_id=mid)
    assert retry.json() == first.json()
    assert len(fake.histories) == 1
    assert send(client, auth, cid, message="different", message_id=mid).status_code == 409
    assert send(client, auth, cid, message="What about cards?").status_code == 200
    assert [role for role, text in fake.histories[-1]] == ["user", "model", "user"]
    history = client.get(f"/api/v1/chat/conversations/{cid}", headers=auth)
    assert len(history.json()["turns"]) == 2
    assert history.json()["title"] == "What is my balance?"
    assert len(client.get("/api/v1/chat/conversations", headers=auth).json()) == 1
    assert client.get("/api/v1/chat/conversations", headers=other).json() == []
    assert client.get(f"/api/v1/chat/conversations/{cid}", headers=other).status_code == 404
    assert send(client, other, cid).status_code == 404
    assert len(fake.histories) == 2
    with Session(connection) as db:
        assert db.scalar(select(func.count()).select_from(ChatTurn)) == 2
        assert db.scalar(select(func.count()).select_from(PendingAction)) == 0


def test_provider_failure_rolls_back_and_logs_safe_error(api):
    client, connection = api
    auth = login(client)
    cid = conversation(client, auth)
    fake = FakeProvider()
    fake.failure = APIError(504, "LLM_TIMEOUT", "The assistant timed out.")
    client.app.state.llm_provider = fake
    result = send(client, auth, cid)
    assert result.status_code == 504
    assert result.json()["error"]["request_id"] == result.headers["X-Request-ID"]
    with Session(connection) as db:
        assert db.scalar(select(func.count()).select_from(ChatTurn)) == 0
        assert (
            db.scalar(select(AuditLog.outcome).where(AuditLog.action == "chat_failed"))
            == "LLM_TIMEOUT"
        )
        assert db.get(Conversation, cid).title == "New conversation"


def test_missing_provider_authentication_and_input_validation(api):
    client, _ = api
    assert client.get("/api/v1/chat/status").status_code == 401
    assert client.post("/api/v1/chat/conversations", json={}).status_code == 401
    auth = login(client)
    assert client.get("/api/v1/chat/status", headers=auth).json()["configured"] is False
    cid = conversation(client, auth)
    response = send(client, auth, cid)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
    for text in [" ", "x" * 2001]:
        assert send(client, auth, cid, message=text).status_code == 422
    invalid = client.post(
        "/api/v1/chat",
        headers=auth,
        json={
            "conversation_id": cid,
            "message_id": str(uuid4()),
            "message": "Hello",
            "customer_id": str(uuid4()),
        },
    )
    assert invalid.status_code == 422


def test_context_window_and_conversation_limit(api):
    client, connection = api
    auth = login(client)
    cid = conversation(client, auth)
    fake = FakeProvider()
    client.app.state.llm_provider = fake
    first = send(client, auth, cid).json()
    with Session(connection) as db, db.begin():
        for position in range(2, 100):
            db.add(
                ChatTurn(
                    conversation_id=cid,
                    message_id=uuid4(),
                    position=position,
                    user_text=f"Message {position}",
                    response=first,
                )
            )
    connection.commit()
    assert send(client, auth, cid).status_code == 200
    assert len(fake.histories[-1]) == 21
    assert fake.histories[-1][0][1] == "Message 90"
    assert send(client, auth, cid).json()["error"]["code"] == "CONVERSATION_FULL"


def test_concurrent_conversation_is_rejected_before_provider_call(api):
    client, connection = api
    auth = login(client)
    cid = conversation(client, auth)
    fake = FakeProvider()
    client.app.state.llm_provider = fake
    schema = connection.dialect.default_schema_name
    engine = create_engine(
        Settings(_env_file=None).database_url,
        connect_args={
            "options": f"-c search_path={schema},public -c statement_timeout=3000",
        },
    )
    original_factory = client.app.state.session_factory
    try:
        client.app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
        with Session(engine) as lock_session, lock_session.begin():
            lock_session.scalar(
                select(Conversation).where(Conversation.id == cid).with_for_update()
            )
            response = send(client, auth, cid)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "CHAT_BUSY"
            assert fake.histories == []
        assert send(client, auth, cid).status_code == 200
    finally:
        client.app.state.session_factory = original_factory
        engine.dispose()


def test_chat_throttle_limits_provider_calls(api):
    client, _ = api
    auth = login(client)
    cid = conversation(client, auth)
    fake = FakeProvider()
    client.app.state.llm_provider = fake
    for _ in range(10):
        assert send(client, auth, cid).status_code == 200
    response = send(client, auth, cid)
    assert response.status_code == 429
    assert "chat requests" in response.json()["error"]["message"]
    assert len(fake.histories) == 10
