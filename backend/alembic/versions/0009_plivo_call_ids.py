"""Allow Plivo's 36-character call UUIDs.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("phone_calls", "provider_sid", type_=sa.String(36), existing_type=sa.String(34))


def downgrade():
    op.alter_column("phone_calls", "provider_sid", type_=sa.String(34), existing_type=sa.String(36))
