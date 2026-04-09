"""Models for test configuration: suites, sweep configs, and individual test cases."""

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base
from backend.app.models.prompt import Prompt  # noqa: F401 — ensure Prompt is registered


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestSuiteStatusEnum(str, enum.Enum):
    draft = "draft"
    ready = "ready"
    running = "running"
    completed = "completed"
    archived = "archived"


class TestCaseStatusEnum(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class PipelineEnum(str, enum.Enum):
    direct_audio = "direct_audio"
    asr_text = "asr_text"
    telephony = "telephony"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestSuite(Base):
    __tablename__ = "test_suites"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(TestSuiteStatusEnum, name="test_suite_status_enum", native_enum=False),
        nullable=False,
        default=TestSuiteStatusEnum.draft,
    )

    # Prompt association
    prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    sweep_configs: Mapped[list["SweepConfig"]] = relationship(back_populates="test_suite", lazy="selectin")
    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="test_suite", lazy="selectin")
    test_runs: Mapped[list["TestRun"]] = relationship(back_populates="test_suite", lazy="selectin")


class SweepConfig(Base):
    __tablename__ = "sweep_configs"

    test_suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_suites.id"), nullable=False
    )
    noise_level_db_values: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    speech_level_db_values: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: [0.0],
        comment="Speech gain levels in dB. 0=original, negative=quieter/whisper, positive=louder/shout.",
    )
    delay_ms_values: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    gain_db_values: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    noise_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    interferer_level_db_values: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: [0.0],
        comment="Relative levels for speech interferer in dB. 0=same as speech. Only used with secondary_voice/babble.",
    )
    pipelines: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    llm_backends: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    eq_configs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="Array of EQ filter chain configs")

    # Telephony sweep dimensions (added in migration 006)
    bt_codec_types: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment='BT HFP codec types to sweep, e.g. ["cvsd", "msbc", "none"]',
    )
    agc_configs: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment='AGC preset names to sweep, e.g. ["off", "mild", "aggressive"]',
    )
    aec_residual_configs: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="List of AEC residual config dicts to sweep",
    )
    network_configs: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="List of network degradation config dicts to sweep",
    )
    telephony_enabled: Mapped[bool] = mapped_column(
        nullable=False, default=False,
        comment="Whether this sweep uses the telephony pipeline",
    )

    # Far-end / 2-way conversation sweep dimensions (added in migration 008)
    far_end_enabled: Mapped[bool] = mapped_column(
        nullable=False, default=False,
        comment="Enable 2-way conversation with uncorrelated far-end speech",
    )
    far_end_speech_level_db_values: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="Far-end speech gain levels to sweep (dB)",
    )
    far_end_offset_ms_values: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="Far-end timing offsets to sweep (ms). Negative = far-end first (barge-in).",
    )

    # Relationships
    test_suite: Mapped["TestSuite"] = relationship(back_populates="sweep_configs", lazy="selectin")


class TestCase(Base):
    __tablename__ = "test_cases"

    test_suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_suites.id"), nullable=False
    )
    speech_sample_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("speech_samples.id"), nullable=False
    )
    noise_level_db: Mapped[float | None] = mapped_column(Float, nullable=True)
    speech_level_db: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=0.0,
        comment="Digital gain applied to speech before mixing (dB). 0=original level.",
    )
    delay_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    gain_db: Mapped[float | None] = mapped_column(Float, nullable=True)
    noise_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    interferer_level_db: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None,
        comment="Relative level for speech interferer (secondary_voice/babble). 0=same as speech RMS. None=muted.",
    )
    eq_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Telephony-specific per-case parameters (added in migration 006)
    bt_codec: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="BT HFP codec for this test case: cvsd, msbc, or none",
    )
    agc_config_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="AGC configuration (serialized AGCConfig or preset name)",
    )
    aec_residual_config_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="AEC residual configuration for this test case",
    )
    network_config_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Network degradation configuration for this test case",
    )

    # Far-end / 2-way conversation per-case parameters (added in migration 008)
    far_end_enabled: Mapped[bool] = mapped_column(
        nullable=False, default=False,
        comment="Whether this case has far-end (2-way) speech",
    )
    far_end_speech_sample_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("speech_samples.id"), nullable=True,
        comment="Far-end caller speech sample (uncorrelated from near-end)",
    )
    far_end_speech_level_db: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=0.0,
        comment="Far-end speech gain (dB)",
    )
    far_end_offset_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=0.0,
        comment="Far-end timing offset (ms). Negative = far-end starts first.",
    )

    system_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Resolved system prompt text for this test case",
    )

    pipeline: Mapped[str] = mapped_column(
        Enum(PipelineEnum, name="pipeline_enum", native_enum=False),
        nullable=False,
    )
    llm_backend: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(TestCaseStatusEnum, name="test_case_status_enum", native_enum=False),
        nullable=False,
        default=TestCaseStatusEnum.pending,
    )
    deterministic_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="SHA-256 hash for checkpointing"
    )

    # Relationships
    test_suite: Mapped["TestSuite"] = relationship(back_populates="test_cases", lazy="selectin")
    speech_sample: Mapped["SpeechSample"] = relationship(foreign_keys=[speech_sample_id], lazy="selectin")
    results: Mapped[list["TestResult"]] = relationship(back_populates="test_case", lazy="selectin")
