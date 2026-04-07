"""Models for test configuration: suites, sweep configs, and individual test cases."""

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


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

    # Relationships
    sweep_configs: Mapped[list["SweepConfig"]] = relationship(back_populates="test_suite", lazy="selectin")
    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="test_suite", lazy="selectin")
    test_runs: Mapped[list["TestRun"]] = relationship(back_populates="test_suite", lazy="selectin")


class SweepConfig(Base):
    __tablename__ = "sweep_configs"

    test_suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_suites.id"), nullable=False
    )
    snr_db_values: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    speech_level_db_values: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: [0.0],
        comment="Speech gain levels in dB. 0=original, negative=quieter/whisper, positive=louder/shout.",
    )
    delay_ms_values: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    gain_db_values: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    noise_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pipelines: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    llm_backends: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    eq_configs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="Array of EQ filter chain configs")

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
    snr_db: Mapped[float | None] = mapped_column(Float, nullable=True)
    speech_level_db: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=0.0,
        comment="Digital gain applied to speech before mixing (dB). 0=original level.",
    )
    delay_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    gain_db: Mapped[float | None] = mapped_column(Float, nullable=True)
    noise_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    eq_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    speech_sample: Mapped["SpeechSample"] = relationship(lazy="selectin")
    results: Mapped[list["TestResult"]] = relationship(back_populates="test_case", lazy="selectin")
