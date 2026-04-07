"""Add metrics columns to test_results.

Revision ID: 002_add_metrics
Revises: 001_initial
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa

revision = "002_add_metrics"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use IF NOT EXISTS to be safe on already-migrated DBs
    op.execute("ALTER TABLE test_results ADD COLUMN IF NOT EXISTS total_latency_ms FLOAT")
    op.execute("ALTER TABLE test_results ADD COLUMN IF NOT EXISTS asr_latency_ms FLOAT")
    op.execute("ALTER TABLE test_results ADD COLUMN IF NOT EXISTS input_tokens INTEGER")
    op.execute("ALTER TABLE test_results ADD COLUMN IF NOT EXISTS output_tokens INTEGER")
    # Also add error/error_stage if missing (they're in the model but not initial migration)
    op.execute("ALTER TABLE test_results ADD COLUMN IF NOT EXISTS error TEXT")
    op.execute("ALTER TABLE test_results ADD COLUMN IF NOT EXISTS error_stage VARCHAR(50)")
    # And test_runs extras
    op.execute("ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS skipped_cases INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS error_message TEXT")
    op.execute("ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS error_details JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE test_results DROP COLUMN IF EXISTS total_latency_ms")
    op.execute("ALTER TABLE test_results DROP COLUMN IF EXISTS asr_latency_ms")
    op.execute("ALTER TABLE test_results DROP COLUMN IF EXISTS input_tokens")
    op.execute("ALTER TABLE test_results DROP COLUMN IF EXISTS output_tokens")
