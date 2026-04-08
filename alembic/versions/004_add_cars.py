"""Add cars and car_noise_files tables for vehicle noise libraries.

Revision ID: 004_add_cars
Revises: 003_add_degraded_audio_path
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "004_add_cars"
down_revision = "003_add_degraded_audio_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cars",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata_json", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "car_noise_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("car_id", UUID(as_uuid=True), sa.ForeignKey("cars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("noise_category", sa.String(20), nullable=False),
        sa.Column("speed", sa.Float, nullable=False),
        sa.Column("condition", sa.String(100), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("duration_s", sa.Float, nullable=True),
        sa.Column("sample_rate", sa.Integer, nullable=True),
        sa.Column("metadata_json", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_car_noise_files_car_id", "car_noise_files", ["car_id"])
    op.create_index("ix_car_noise_files_category_speed", "car_noise_files", ["noise_category", "speed"])


def downgrade() -> None:
    op.drop_table("car_noise_files")
    op.drop_table("cars")
