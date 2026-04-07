"""Add metrics columns to test_results.

Revision ID: 002_add_metrics_columns
Revises: 001_initial
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa

revision = "002_add_metrics_columns"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_results",
        sa.Column("total_latency_ms", sa.Float(), nullable=True,
                  comment="Wall-clock pipeline latency (ASR + LLM + noise gen)"),
    )
    op.add_column(
        "test_results",
        sa.Column("asr_latency_ms", sa.Float(), nullable=True,
                  comment="ASR-only latency in ms (Pipeline B)"),
    )
    op.add_column(
        "test_results",
        sa.Column("input_tokens", sa.Integer(), nullable=True,
                  comment="LLM prompt token count"),
    )
    op.add_column(
        "test_results",
        sa.Column("output_tokens", sa.Integer(), nullable=True,
                  comment="LLM completion token count"),
    )


def downgrade() -> None:
    op.drop_column("test_results", "output_tokens")
    op.drop_column("test_results", "input_tokens")
    op.drop_column("test_results", "asr_latency_ms")
    op.drop_column("test_results", "total_latency_ms")
