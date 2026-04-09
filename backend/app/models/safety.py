"""Models for voice safety testing: runs, cases, and agent verdicts."""

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

class SafetyRunStatusEnum(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class SafetyVerdictEnum(str, enum.Enum):
    passed = "passed"
    warning = "warning"
    failed = "failed"


class SafetySeverityEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SafetyTestRun(Base):
    """A batch safety test run against a specific LLM backend."""

    __tablename__ = "safety_test_runs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(SafetyRunStatusEnum, name="safety_run_status_enum", native_enum=False),
        nullable=False,
        default=SafetyRunStatusEnum.pending,
    )
    llm_backend: Mapped[str] = mapped_column(String(100), nullable=False)
    system_prompt: Mapped[str] = mapped_column(
        Text, nullable=False, default="You are a helpful in-car voice assistant."
    )

    # Filters used for this run
    categories_filter: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="Adversarial categories included (null = all)"
    )
    min_severity_filter: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="Minimum severity level included"
    )
    agents_filter: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="Agent names used (null = all)"
    )

    # Execution config
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=6)

    # Progress
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    results: Mapped[list["SafetyTestCaseResult"]] = relationship(
        back_populates="safety_run", lazy="selectin", cascade="all, delete-orphan"
    )


class SafetyTestCaseResult(Base):
    """Result for a single adversarial utterance within a safety test run."""

    __tablename__ = "safety_test_case_results"

    safety_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("safety_test_runs.id", ondelete="CASCADE"), nullable=False
    )

    # Utterance metadata
    utterance_id: Mapped[str] = mapped_column(String(50), nullable=False)
    utterance_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subcategory: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_behavior: Mapped[str] = mapped_column(String(50), nullable=False)

    # Model response
    model_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_backend: Mapped[str] = mapped_column(String(100), nullable=False)

    # Composite verdict
    composite_verdict: Mapped[str] = mapped_column(
        Enum(SafetyVerdictEnum, name="safety_verdict_enum", native_enum=False),
        nullable=False,
    )
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    safety_run: Mapped["SafetyTestRun"] = relationship(back_populates="results")
    agent_verdicts: Mapped[list["SafetyAgentVerdict"]] = relationship(
        back_populates="case_result", lazy="selectin", cascade="all, delete-orphan"
    )


class SafetyAgentVerdict(Base):
    """Individual agent verdict for a single test case."""

    __tablename__ = "safety_agent_verdicts"

    case_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety_test_case_results.id", ondelete="CASCADE"),
        nullable=False,
    )

    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    verdict: Mapped[str] = mapped_column(
        Enum(SafetyVerdictEnum, name="safety_verdict_enum", native_enum=False, create_constraint=False),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        Enum(SafetySeverityEnum, name="safety_severity_enum", native_enum=False),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Relationships
    case_result: Mapped["SafetyTestCaseResult"] = relationship(back_populates="agent_verdicts")
