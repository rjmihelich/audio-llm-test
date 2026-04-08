"""Rename snr_db to noise_level_db.

Revision ID: 007
Revises: 006
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sweep_configs", "snr_db_values", new_column_name="noise_level_db_values")
    op.alter_column("test_cases", "snr_db", new_column_name="noise_level_db")


def downgrade() -> None:
    op.alter_column("sweep_configs", "noise_level_db_values", new_column_name="snr_db_values")
    op.alter_column("test_cases", "noise_level_db", new_column_name="snr_db")
