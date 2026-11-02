"""Store the authorized agent configuration on each run.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_runs",
        sa.Column(
            "configuration",
            JSONB(),
            nullable=False,
            server_default=sa.text(
                "jsonb_build_object('agent_count', 5, 'architecture', 'blackboard', 'prompt_strategy', 'react')"
            ),
        ),
    )


def downgrade():
    op.drop_column("agent_runs", "configuration")
