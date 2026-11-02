"""Persist voice session ownership and correlated speech events.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("conversation_id", sa.UUID(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_voice_sessions_customer_id", "voice_sessions", ["customer_id"])
    op.create_index("ix_voice_sessions_conversation_id", "voice_sessions", ["conversation_id"])
    op.create_table(
        "voice_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("session_id", sa.UUID(), sa.ForeignKey("voice_sessions.id"), nullable=False),
        sa.Column("run_id", sa.UUID(), sa.ForeignKey("agent_runs.id")),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_voice_events_session_id", "voice_events", ["session_id"])


def downgrade():
    op.drop_table("voice_events")
    op.drop_table("voice_sessions")
