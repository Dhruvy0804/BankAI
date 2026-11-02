import asyncio
from uuid import uuid4

import pytest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from sqlalchemy import select

from app.agents.configuration import AgentConfiguration
from app.agents.security import issue_grant
from app.agents.supervisor import run_supervisor
from app.models import AgentEvent, AgentRun
from app.seed.demo_data import demo_id

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.integration.test_agents",)


@pytest.mark.parametrize(
    ("configuration", "roles"),
    [
        (AgentConfiguration(agent_count=2, architecture="direct", prompt_strategy="few_shot"), ("generalist",)),
        (AgentConfiguration(agent_count=3, architecture="direct"), ("account_card", "loan_support")),
        (AgentConfiguration(agent_count=5, architecture="direct"), ("account", "card", "loan", "support")),
        (AgentConfiguration(agent_count=5, architecture="blackboard", prompt_strategy="few_shot"), ("account", "card", "loan", "support")),
    ],
)
def test_real_frameworks_use_configured_roles_and_message_context(
    runtime, monkeypatch, configuration, roles
):
    settings, factory, client, conversation_id, fixture_run_id = runtime
    with factory() as db, db.begin():
        db.get(AgentRun, fixture_run_id).configuration = configuration.model_dump()
    calls = {}

    def fake_crew(self, messages, **kwargs):
        role = self._role
        index = calls.get(role, 0)
        calls[role] = index + 1
        self._board.reserve(role, "model")
        self._board.usage(role, types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=10, total_token_count=20
        ))
        if role in ("generalist", "account_card", "account") and index == 0:
            return "Action: account_snapshot\nAction Input: {}"
        if role == "card" and index == 0:
            return "Action: card_snapshot\nAction Input: {}"
        if role in ("loan_support", "loan") and index == 0:
            assert "kyc" in str(messages), "Prior Account artifact must arrive in the A2A message"
            return 'Action: calculate_emi\nAction Input: {"principal":"12000","annual_interest_rate":"12","tenure_months":12}'
        return 'Final Answer: {"status":"answered","answer":"Verified demo tool facts are ready.","source_ids":[]}'

    async def fake_adk(self, llm_request, stream=False):
        index = self.__dict__.get("_test_call_count", 0)
        self.__dict__["_test_call_count"] = index + 1
        prior = []
        for item in llm_request.contents:
            for part in item.parts or []:
                response = part.function_response.response if part.function_response else None
                if isinstance(response, dict) and "id" in response:
                    prior.append(response["id"])
        if index < len(roles):
            part = types.Part(function_call=types.FunctionCall(
                name="delegate",
                args={"role": roles[index], "task": "Read account facts and calculate EMI when relevant.", "consume": prior},
            ))
        else:
            part = types.Part(function_call=types.FunctionCall(
                name="finish", args={"status": "answered", "answer": "Verified demo results are ready."}
            ))
        yield LlmResponse(
            content=types.Content(role="model", parts=[part]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=10, total_token_count=20
            ),
        )

    monkeypatch.setattr("app.agents.specialists.MonitoredGemini.call", fake_crew)
    monkeypatch.setattr("google.adk.models.google_llm.Gemini.generate_content_async", fake_adk)
    answer, artifacts, run_id, usage, _ = asyncio.run(run_supervisor(
        settings, factory, demo_id("customer-1"), conversation_id, str(uuid4()),
        [("user", "Read my account balance and calculate INR 12000 EMI at 12% for 12 months")],
        configuration,
    ))
    assert answer.status == "answered"
    assert tuple(a.role for a in artifacts) == roles
    assert usage["total_tokens"] is not None
    with factory() as db:
        run = db.get(AgentRun, run_id)
        assert AgentConfiguration.model_validate(run.configuration) == configuration
        events = list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id)))
    assert next(e for e in events if e.kind == "run_start").payload["configured_roles"] == configuration.agent_count
    trace = client.get(f"/api/v1/chat/runs/{run_id}").json()
    assert list(trace["configured_roles"]) == ["supervisor", *roles]
    assert trace["configuration"] == configuration.model_dump()
    if len(roles) > 1:
        assert artifacts[0].id in artifacts[-1].consumed
        event_kind = "message_consume" if configuration.architecture == "direct" else "state_consume"
        assert any(e.kind == event_kind for e in events)
    denied_role = "account" if configuration.agent_count == 2 else "generalist"
    denied = client.get(
        f"/internal/a2a/{denied_role}/.well-known/agent-card.json",
        headers={"Authorization": "Bearer " + issue_grant(settings, demo_id("customer-1"), fixture_run_id, denied_role)},
    )
    assert denied.status_code == 403


def test_configuration_rejects_unplanned_counts_and_modes():
    with pytest.raises(ValueError):
        AgentConfiguration(agent_count=4)
    with pytest.raises(ValueError):
        AgentConfiguration(architecture="shared_memory")
