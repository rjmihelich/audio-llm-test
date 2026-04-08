"""Add far-end speech (2-way conversation) and doubletalk metrics.

Revision ID: 008
Revises: 007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- sweep_configs: far-end sweep dimensions ---
    op.add_column("sweep_configs", sa.Column("far_end_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("sweep_configs", sa.Column("far_end_speech_level_db_values", JSON, nullable=True))
    op.add_column("sweep_configs", sa.Column("far_end_offset_ms_values", JSON, nullable=True))

    # --- test_cases: far-end per-case parameters ---
    op.add_column("test_cases", sa.Column("far_end_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("test_cases", sa.Column(
        "far_end_speech_sample_id",
        sa.UUID(as_uuid=True),
        sa.ForeignKey("speech_samples.id"),
        nullable=True,
    ))
    op.add_column("test_cases", sa.Column("far_end_speech_level_db", sa.Float(), nullable=True))
    op.add_column("test_cases", sa.Column("far_end_offset_ms", sa.Float(), nullable=True))

    # --- test_results: telephony evaluation and doubletalk metrics ---
    op.add_column("test_results", sa.Column("downlink_audio_path", sa.String(500), nullable=True))
    op.add_column("test_results", sa.Column("telephony_eval_json", JSON, nullable=True))
    op.add_column("test_results", sa.Column("doubletalk_metrics_json", JSON, nullable=True))


def downgrade() -> None:
    # test_results
    op.drop_column("test_results", "doubletalk_metrics_json")
    op.drop_column("test_results", "telephony_eval_json")
    op.drop_column("test_results", "downlink_audio_path")

    # test_cases
    op.drop_column("test_cases", "far_end_offset_ms")
    op.drop_column("test_cases", "far_end_speech_level_db")
    op.drop_column("test_cases", "far_end_speech_sample_id")
    op.drop_column("test_cases", "far_end_enabled")

    # sweep_configs
    op.drop_column("sweep_configs", "far_end_offset_ms_values")
    op.drop_column("sweep_configs", "far_end_speech_level_db_values")
    op.drop_column("sweep_configs", "far_end_enabled")
