import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    DataPart,
    Message,
    MessageSendParams,
    Part,
    SendMessageRequest,
    TaskState,
    TextPart,
)
from a2a.utils import new_agent_text_message, new_task

from app.agents.configuration import AgentConfiguration
from app.agents.contracts import ROLES, Artifact, Delegation
from app.agents.security import ProtocolAuth, current_grant, issue_grant
from app.agents.specialists import run_specialist
from app.agents.state import Blackboard
from app.agents.tools import create_mcp
from app.core.errors import APIError


class ScopedTaskStore(InMemoryTaskStore):
    """Protocol tasks are isolated by grant; PostgreSQL retains the durable evidence."""

    def __init__(self):
        super().__init__()
        self.scopes = {}

    def prune(self):
        now = datetime.now(UTC).timestamp()
        for identifier, (_, expiry) in list(self.scopes.items()):
            if expiry <= now:
                self.scopes.pop(identifier, None)
                self.tasks.pop(identifier, None)

    @staticmethod
    def identity():
        grant = current_grant.get()
        return (grant.sub, grant.run_id, grant.role), grant.exp

    async def save(self, task, context=None):
        owner, expiry = self.identity()
        async with self.lock:
            self.prune()
            if task.id in self.scopes and self.scopes[task.id][0] != owner:
                raise APIError(403, "TASK_DENIED", "Task does not belong to this service grant.")
            if task.id not in self.tasks and len(self.tasks) >= 1000:
                raise APIError(429, "TASK_LIMIT", "Protocol task capacity reached.")
            self.scopes[task.id] = (owner, expiry)
            self.tasks[task.id] = task

    async def get(self, task_id, context=None):
        owner, _ = self.identity()
        async with self.lock:
            self.prune()
            if self.scopes.get(task_id, (None,))[0] != owner:
                return None
            return self.tasks.get(task_id)

    async def delete(self, task_id, context=None):
        owner, _ = self.identity()
        async with self.lock:
            if self.scopes.get(task_id, (None,))[0] == owner:
                self.scopes.pop(task_id, None)
                self.tasks.pop(task_id, None)


class CrewExecutor(AgentExecutor):
    def __init__(self, settings, factory):
        self.settings, self.factory = settings, factory

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        grant = current_grant.get()
        board = Blackboard(self.factory, grant.run_id, grant.sub)
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.update_status(TaskState.working)
        try:
            delegation = Delegation.model_validate_json(context.get_user_input())
            if delegation.run_id != grant.run_id or delegation.role != grant.role:
                raise APIError(403, "DELEGATION_DENIED", "Task does not match the service grant.")
            board.event(grant.role, "a2a_received", task_id=task.id)
            token = issue_grant(self.settings, grant.sub, grant.run_id, grant.role)
            result = await asyncio.to_thread(
                run_specialist, self.settings, self.factory, grant, delegation, token
            )
            await updater.add_artifact(
                [Part(root=DataPart(data=result.model_dump(mode="json")))],
                name="Blackboard artifact",
            )
            await updater.complete()
            board.event(grant.role, "a2a_completed", task_id=task.id, artifact_id=str(result.id))
        except Exception as exc:  # noqa: BLE001 -- sanitize arbitrary framework failures at the protocol boundary.
            board.event(
                grant.role,
                "agent_error",
                code="SPECIALIST_FAILED",
                task_id=task.id,
                error_type=type(exc).__name__,
            )
            await updater.update_status(
                TaskState.failed,
                message=new_agent_text_message("The specialist could not complete this task."),
                final=True,
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        grant = current_grant.get()
        board = Blackboard(self.factory, grant.run_id, grant.sub)
        with self.factory() as db, db.begin():
            run = board.owned(db, active=True, lock=True)
            run.status = "cancelled"
        board.event(grant.role, "cancel_requested")
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.update_status(TaskState.canceled, final=True)


def mount_protocols(app, settings, factory):
    server = create_mcp(factory, settings)
    mcp_app = server.streamable_http_app()
    app.mount("/internal/mcp", ProtocolAuth(mcp_app, settings, factory))
    for role in ROLES:
        card = AgentCard(
            name=f"BankAI {role}",
            description=f"CrewAI {role} specialist for fictional banking",
            url=f"{settings.agent_base_url}/internal/a2a/{role}/",
            version="1.0.0",
            default_input_modes=["text/plain"],
            default_output_modes=["application/json"],
            capabilities=AgentCapabilities(streaming=False),
            skills=[
                AgentSkill(
                    id=role, name=role, description=f"Authenticated {role} tasks", tags=["bankai"]
                )
            ],
            security_schemes={
                "service_grant": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            },
            security=[{"service_grant": []}],
        )
        handler = DefaultRequestHandler(
            agent_executor=CrewExecutor(settings, factory), task_store=ScopedTaskStore()
        )
        a2a = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
        app.mount(f"/internal/a2a/{role}", ProtocolAuth(a2a, settings, factory, role=role))
    return server


async def delegate_a2a(settings, factory, customer_id, run_id, role, task, consume):
    board = Blackboard(factory, run_id, customer_id)
    with factory() as db:
        config = AgentConfiguration.model_validate(board.owned(db, active=True).configuration)
    if role not in config.roles:
        raise APIError(403, "ROLE_DENIED", "Role is not in this run configuration.")
    context = board.read(consume)
    request = Delegation(
        run_id=run_id,
        role=role,
        task=task,
        consume=consume,
        context=context if config.architecture == "direct" else [],
    )
    token = issue_grant(settings, customer_id, run_id, role)
    base = f"{settings.agent_base_url}/internal/a2a/{role}/"
    board.event("supervisor", "a2a_send", target=role)
    async with httpx.AsyncClient(
        timeout=settings.agent_timeout_seconds,
        headers={"Authorization": "Bearer " + token},
        follow_redirects=False,
    ) as client:
        card = await A2ACardResolver(client, base).get_agent_card()
        if card.url.rstrip("/") != base.rstrip("/"):
            raise APIError(
                502, "A2A_CARD_INVALID", "Agent Card endpoint did not match the allowed service."
            )
        response = await A2AClient(client, agent_card=card).send_message(
            SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(
                    message=Message(
                        role="user",
                        message_id=str(uuid4()),
                        parts=[Part(root=TextPart(text=request.model_dump_json()))],
                    )
                ),
            )
        )
    root = response.root
    result = getattr(root, "result", None)
    if (
        result is None
        or getattr(result, "status", None) is None
        or result.status.state != TaskState.completed
    ):
        raise APIError(502, "A2A_FAILED", "The specialist did not complete its task.")
    for artifact in result.artifacts or []:
        for part in artifact.parts:
            if isinstance(part.root, DataPart):
                validated = Artifact.model_validate(part.root.data)
                if validated.run_id != run_id or validated.role != role:
                    raise APIError(
                        502, "A2A_INVALID_OUTPUT", "Invalid specialist artifact ownership."
                    )
                persisted = board.read([validated.id])[0]
                if validated != persisted:
                    raise APIError(
                        502, "A2A_INVALID_OUTPUT", "Specialist artifact differs from shared state."
                    )
                board.event("supervisor", "a2a_result", target=role, artifact_id=str(validated.id))
                return validated
    raise APIError(502, "A2A_INVALID_OUTPUT", "The specialist returned no typed artifact.")
