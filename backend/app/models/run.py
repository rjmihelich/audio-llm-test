"""Models for test execution: runs and individual results."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestRunStatusEnum(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestRun(Base):
    __tablename__ = "test_runs"

    test_suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_suites.id"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(TestRunStatusEnum, name="test_run_status_enum", native_enum=False),
        nullable=False,
        default=TestRunStatusEnum.pending,
    )
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    test_suite: Mapped["TestSuite"] = relationship(back_populates="test_runs", lazy="selectin")
    results: Mapped[list["TestResult"]] = relationship(back_populates="test_run", lazy="selectin")


class TestResult(Base):
    __tablename__ = "test_results"

    test_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_runs.id"), nullable=False
    )
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_cases.id"), nullable=False
    )
    llm_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_response_audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    llm_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    asr_transcript: Mapped[str | None] = mapped_column(Text, nullable=True, comment="ASR transcript for pipeline B")
    wer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Word Error Rate")
    total_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Wall-clock pipeline latency (ASR + LLM + noise gen)")
    asr_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True, comment="ASR-only latency in ms (Pipeline B)")
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="LLM prompt token count")
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="LLM completion token count")
    evaluation_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="0.0 to 1.0")
    evaluation_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evaluation_details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluator_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Pipeline or evaluation error message")
    error_stage: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Stage where error occurred: audio_load, pipeline, evaluation, timeout")

    # Relationships
    test_run: Mapped["TestRun"] = relationship(back_populates="results", lazy="selectin")
    test_case: Mapped["TestCase"] = relationship(back_populates="results", lazy="selectin")
