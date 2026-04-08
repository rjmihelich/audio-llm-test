"""Add interferer_level_db to test_cases and sweep_configs.

Revision ID: 005
Revises: 004
"""

revision = "005"
down_revision = "004"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


def upgrade():
    op.add_column(
        "test_cases",
        sa.Column(
            "interferer_level_db",
            sa.Float(),
            nullable=True,
            comment="Relative level for speech interferer (secondary_voice/babble). 0=same as speech RMS. None=muted.",
        ),
    )
    op.add_column(
        "sweep_configs",
        sa.Column(
            "interferer_level_db_values",
            JSON(),
            nullable=False,
            server_default="[0.0]",
            comment="Relative levels for speech interferer in dB.",
        ),
    )


def downgrade():
    op.drop_column("sweep_configs", "interferer_level_db_values")
    op.drop_column("test_cases", "interferer_level_db")
