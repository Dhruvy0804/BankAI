from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from app.agents.contracts import Artifact, SpecialistSummary, ToolFact
from app.core.errors import APIError
from app.models import AgentArtifact, AgentEvent, AgentRun


class Blackboard:
    def __init__(self, factory, run_id: UUID, customer_id: UUID):
        self.factory, self.run_id, self.customer_id = factory, run_id, customer_id

    def owned(self, db, *, active=False, lock=False):
        query = select(AgentRun).where(
            AgentRun.id == self.run_id, AgentRun.customer_id == self.customer_id
        )
        run = db.scalar(query.with_for_update() if lock else query)
        if run is None:
            raise APIError(404, "NOT_FOUND", "Agent run not found.")
        if active and (run.status != "running" or run.expires_at <= datetime.now(UTC)):
            raise APIError(409, "RUN_INACTIVE", "This agent run has ended or expired.")
        return run

    def event(self, role, kind, **payload):
        # Callers pass metadata, never provider prompts, raw steps, or credentials.
        with self.factory() as db, db.begin():
            self.owned(db)
            db.add(AgentEvent(run_id=self.run_id, role=role, kind=kind, payload=payload))

    def reserve(self, role, kind):
        with self.factory() as db, db.begin():
            run = self.owned(db, active=True, lock=True)
            name, limit = ("model_calls", 20) if kind == "model" else ("tool_calls", 16)
            count = getattr(run, name)
            if count >= limit:
                raise APIError(429, "AGENT_BUDGET", "The agent execution budget was reached.")
            setattr(run, name, count + 1)
            db.add(AgentEvent(run_id=self.run_id, role=role, kind=f"{kind}_start", payload={}))

    def usage(self, role, usage):
        with self.factory() as db, db.begin():
            run = self.owned(db, lock=True)
            complete = usage is not None and all(
                getattr(usage, name, None) is not None
                for name in ("prompt_token_count", "candidates_token_count", "total_token_count")
            )
            run.usage_complete = run.usage_complete and complete
            if usage:
                run.input_tokens += usage.prompt_token_count or 0
                run.output_tokens += usage.candidates_token_count or 0
                run.total_tokens += usage.total_token_count or 0
            db.add(
                AgentEvent(
                    run_id=self.run_id,
                    role=role,
                    kind="model_end",
                    payload={
                        "total_tokens": usage.total_token_count if usage else None,
                    },
                )
            )

    def model_failed(self, role):
        with self.factory() as db, db.begin():
            run = self.owned(db, lock=True)
            run.usage_complete = False
            db.add(
                AgentEvent(
                    run_id=run.id,
                    role=role,
                    kind="model_error",
                    payload={"code": "PROVIDER_FAILURE"},
                )
            )

    def read(self, identifiers=None):
        with self.factory() as db:
            self.owned(db, active=True)
            rows = list(
                db.scalars(
                    select(AgentArtifact)
                    .where(AgentArtifact.run_id == self.run_id)
                    .order_by(AgentArtifact.revision)
                )
            )
            artifacts = [Artifact.model_validate(row.payload) for row in rows]
            if identifiers is not None:
                found = {a.id: a for a in artifacts}
                if len(set(identifiers)) != len(identifiers) or any(
                    i not in found for i in identifiers
                ):
                    raise APIError(404, "NOT_FOUND", "Blackboard artifact not found in this run.")
                return [found[i] for i in identifiers]
            return artifacts

    def publish(
        self, role, summary: SpecialistSummary, facts: list[ToolFact], consumed, expected_revision
    ):
        with self.factory() as db, db.begin():
            run = self.owned(db, active=True, lock=True)
            if run.revision != expected_revision:
                raise APIError(
                    409, "STATE_CONFLICT", "Blackboard revision changed; reload context."
                )
            rows = list(db.scalars(select(AgentArtifact).where(AgentArtifact.run_id == run.id)))
            known = {row.id for row in rows}
            if any(identifier not in known for identifier in consumed):
                raise APIError(404, "NOT_FOUND", "Consumed artifact does not belong to this run.")
            if any(row.role == role for row in rows):
                raise APIError(409, "ROLE_COMPLETED", "This specialist already produced a result.")
            run.revision += 1
            artifact = Artifact(
                id=uuid4(),
                run_id=run.id,
                role=role,
                revision=run.revision,
                summary=summary,
                facts=facts,
                consumed=consumed,
            )
            db.add(
                AgentArtifact(
                    id=artifact.id,
                    run_id=run.id,
                    role=role,
                    revision=run.revision,
                    payload=artifact.model_dump(mode="json"),
                )
            )
            db.add(
                AgentEvent(
                    run_id=run.id,
                    role=role,
                    kind="state_publish",
                    payload={
                        "artifact_id": str(artifact.id),
                        "revision": run.revision,
                        "consumed": [str(value) for value in consumed],
                    },
                )
            )
            return artifact
