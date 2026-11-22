"""Persist owner evaluation jobs and per-attempt evidence.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evaluation_jobs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("owner_id", UUID(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("error", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evaluation_jobs_owner_id", "evaluation_jobs", ["owner_id"])
    op.execute("CREATE UNIQUE INDEX uq_evaluation_one_active ON evaluation_jobs ((true)) "
        "WHERE status IN ('queued', 'running', 'cancel_requested')")
    op.create_table(
        "evaluation_attempts",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("job_id", UUID(), sa.ForeignKey("evaluation_jobs.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("review", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "position", name="uq_evaluation_attempt_position"),
    )
    op.create_index("ix_evaluation_attempts_job_id", "evaluation_attempts", ["job_id"])


def downgrade():
    op.drop_table("evaluation_attempts")
    op.drop_table("evaluation_jobs")
