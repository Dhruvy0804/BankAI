"""Owner-initiated demo phone calls and sanitized events.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_calls",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("conversation_id", sa.UUID(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("demo_customer", sa.String(12), nullable=False),
        sa.Column("destination_hint", sa.String(8), nullable=False),
        sa.Column("provider_sid", sa.String(34), unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_phone_calls_customer_id", "phone_calls", ["customer_id"])
    op.create_table(
        "phone_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("call_id", sa.UUID(), sa.ForeignKey("phone_calls.id"), nullable=False),
        sa.Column("run_id", sa.UUID(), sa.ForeignKey("agent_runs.id")),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_phone_events_call_id", "phone_events", ["call_id"])


def downgrade():
    op.drop_table("phone_events")
    op.drop_table("phone_calls")
