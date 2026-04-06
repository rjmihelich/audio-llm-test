"""Initial migration – create all tables.

Revision ID: 001_initial
Revises: -
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- voices ---
    op.create_table(
        "voices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("voice_id", sa.String(length=255), nullable=False, comment="Provider-specific voice identifier"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("gender", sa.String(length=255), nullable=False),
        sa.Column("age_group", sa.String(length=255), nullable=False),
        sa.Column("accent", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("metadata_json", JSON, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_voices"),
    )

    # --- corpus_entries ---
    op.create_table(
        "corpus_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=255), nullable=False),
        sa.Column("expected_intent", sa.String(length=255), nullable=True),
        sa.Column("expected_action", sa.String(length=255), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_corpus_entries"),
    )

    # --- speech_samples ---
    op.create_table(
        "speech_samples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("corpus_entry_id", UUID(as_uuid=True), nullable=False),
        sa.Column("voice_id", UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_speech_samples"),
        sa.ForeignKeyConstraint(["corpus_entry_id"], ["corpus_entries.id"], name="fk_speech_samples_corpus_entry_id_corpus_entries"),
        sa.ForeignKeyConstraint(["voice_id"], ["voices.id"], name="fk_speech_samples_voice_id_voices"),
    )

    # --- test_suites ---
    op.create_table(
        "test_suites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_test_suites"),
    )

    # --- sweep_configs ---
    op.create_table(
        "sweep_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("test_suite_id", UUID(as_uuid=True), nullable=False),
        sa.Column("snr_db_values", JSON, nullable=False),
        sa.Column("delay_ms_values", JSON, nullable=False),
        sa.Column("gain_db_values", JSON, nullable=False),
        sa.Column("noise_types", JSON, nullable=False),
        sa.Column("pipelines", JSON, nullable=False),
        sa.Column("llm_backends", JSON, nullable=False),
        sa.Column("eq_configs", JSON, nullable=False, comment="Array of EQ filter chain configs"),
        sa.PrimaryKeyConstraint("id", name="pk_sweep_configs"),
        sa.ForeignKeyConstraint(["test_suite_id"], ["test_suites.id"], name="fk_sweep_configs_test_suite_id_test_suites"),
    )

    # --- test_cases ---
    op.create_table(
        "test_cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("test_suite_id", UUID(as_uuid=True), nullable=False),
        sa.Column("speech_sample_id", UUID(as_uuid=True), nullable=False),
        sa.Column("snr_db", sa.Float(), nullable=True),
        sa.Column("delay_ms", sa.Float(), nullable=True),
        sa.Column("gain_db", sa.Float(), nullable=True),
        sa.Column("noise_type", sa.String(length=100), nullable=True),
        sa.Column("eq_config_json", JSON, nullable=True),
        sa.Column("pipeline", sa.String(length=255), nullable=False),
        sa.Column("llm_backend", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=255), nullable=False),
        sa.Column("deterministic_hash", sa.String(length=64), nullable=False, comment="SHA-256 hash for checkpointing"),
        sa.PrimaryKeyConstraint("id", name="pk_test_cases"),
        sa.ForeignKeyConstraint(["test_suite_id"], ["test_suites.id"], name="fk_test_cases_test_suite_id_test_suites"),
        sa.ForeignKeyConstraint(["speech_sample_id"], ["speech_samples.id"], name="fk_test_cases_speech_sample_id_speech_samples"),
        sa.UniqueConstraint("deterministic_hash", name="uq_test_cases_deterministic_hash"),
    )
    op.create_index("ix_deterministic_hash", "test_cases", ["deterministic_hash"])

    # --- test_runs ---
    op.create_table(
        "test_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("test_suite_id", UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=255), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("completed_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("progress_pct", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_test_runs"),
        sa.ForeignKeyConstraint(["test_suite_id"], ["test_suites.id"], name="fk_test_runs_test_suite_id_test_suites"),
    )

    # --- test_results ---
    op.create_table(
        "test_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("test_run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("test_case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("llm_response_text", sa.Text(), nullable=True),
        sa.Column("llm_response_audio_path", sa.String(length=500), nullable=True),
        sa.Column("llm_latency_ms", sa.Float(), nullable=True),
        sa.Column("asr_transcript", sa.Text(), nullable=True, comment="ASR transcript for pipeline B"),
        sa.Column("wer", sa.Float(), nullable=True, comment="Word Error Rate"),
        sa.Column("evaluation_score", sa.Float(), nullable=True, comment="0.0 to 1.0"),
        sa.Column("evaluation_passed", sa.Boolean(), nullable=True),
        sa.Column("evaluation_details_json", JSON, nullable=True),
        sa.Column("evaluator_type", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_test_results"),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], name="fk_test_results_test_run_id_test_runs"),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], name="fk_test_results_test_case_id_test_cases"),
    )


def downgrade() -> None:
    op.drop_table("test_results")
    op.drop_table("test_runs")
    op.drop_index("ix_deterministic_hash", table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_table("sweep_configs")
    op.drop_table("test_suites")
    op.drop_table("speech_samples")
    op.drop_table("corpus_entries")
    op.drop_table("voices")
