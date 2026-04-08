"""Add degraded_audio_path to test_results for storing dirty WAVs on failure.

Revision ID: 003_add_degraded_audio_path
Revises: 002_add_metrics_columns
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa

revision = "003_add_degraded_audio_path"
down_revision = "002_add_metrics_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_results",
        sa.Column(
            "degraded_audio_path",
            sa.String(500),
            nullable=True,
            comment="Path to degraded (dirty) WAV for failed/interesting cases",
        ),
    )


def downgrade() -> None:
    op.drop_column("test_results", "degraded_audio_path")
