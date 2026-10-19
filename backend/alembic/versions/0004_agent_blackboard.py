"""Persistent agent runs, Blackboard artifacts, and callback events.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def identity():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "agent_runs",
        *identity(),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in (
                "revision",
                "model_calls",
                "tool_calls",
                "input_tokens",
                "output_tokens",
                "total_tokens",
            )
        ],
        sa.Column("usage_complete", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'cancelled')", name="status"
        ),
        sa.CheckConstraint(
            "revision >= 0 AND model_calls >= 0 AND tool_calls >= 0", name="counters"
        ),
    )
    for name in ("customer_id", "conversation_id"):
        op.create_index(f"ix_agent_runs_{name}", "agent_runs", [name])
    op.create_table(
        "agent_artifacts",
        *identity(),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.UniqueConstraint("run_id", "revision", name="uq_agent_artifact_revision"),
        sa.UniqueConstraint("run_id", "role", name="uq_agent_artifact_role"),
    )
    op.create_index("ix_agent_artifacts_run_id", "agent_artifacts", ["run_id"])
    op.create_table(
        "agent_events",
        *identity(),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
    )
    op.create_index("ix_agent_events_run_id", "agent_events", ["run_id"])


def downgrade():
    op.drop_table("agent_events")
    op.drop_table("agent_artifacts")
    op.drop_table("agent_runs")
