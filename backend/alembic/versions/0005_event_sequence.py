"""Order callback events even when transaction timestamps are identical.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_events", sa.Column("sequence", sa.BigInteger(), sa.Identity(), nullable=False)
    )
    op.create_unique_constraint("uq_agent_events_sequence", "agent_events", ["sequence"])


def downgrade():
    op.drop_constraint("uq_agent_events_sequence", "agent_events", type_="unique")
    op.drop_column("agent_events", "sequence")
