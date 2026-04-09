"""Add prompts table and system_prompt columns.

Revision ID: 009
Revises: 008
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- prompts: library of reusable system prompts ---
    op.create_table(
        "prompts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # --- test_suites: track which prompt was used and the resolved text ---
    op.add_column("test_suites", sa.Column(
        "prompt_id",
        sa.UUID(as_uuid=True),
        sa.ForeignKey("prompts.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.add_column("test_suites", sa.Column("system_prompt", sa.Text(), nullable=True))

    # --- test_cases: store resolved system_prompt text per case ---
    op.add_column("test_cases", sa.Column("system_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("test_cases", "system_prompt")
    op.drop_column("test_suites", "system_prompt")
    op.drop_column("test_suites", "prompt_id")
    op.drop_table("prompts")
