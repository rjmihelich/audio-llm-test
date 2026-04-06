"""Models for speech corpus: voices, corpus entries, and generated samples."""

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProviderEnum(str, enum.Enum):
    openai = "openai"
    google = "google"
    elevenlabs = "elevenlabs"


class GenderEnum(str, enum.Enum):
    male = "male"
    female = "female"
    neutral = "neutral"


class AgeGroupEnum(str, enum.Enum):
    child = "child"
    young_adult = "young_adult"
    adult = "adult"
    senior = "senior"


class CorpusCategoryEnum(str, enum.Enum):
    harvard_sentence = "harvard_sentence"
    navigation = "navigation"
    media = "media"
    climate = "climate"
    phone = "phone"
    general = "general"


class SampleStatusEnum(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    ready = "ready"
    failed = "failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Voice(Base):
    __tablename__ = "voices"

    provider: Mapped[str] = mapped_column(
        Enum(ProviderEnum, name="provider_enum", native_enum=False),
        nullable=False,
    )
    voice_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="Provider-specific voice identifier")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[str] = mapped_column(
        Enum(GenderEnum, name="gender_enum", native_enum=False),
        nullable=False,
    )
    age_group: Mapped[str] = mapped_column(
        Enum(AgeGroupEnum, name="age_group_enum", native_enum=False),
        nullable=False,
    )
    accent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    samples: Mapped[list["SpeechSample"]] = relationship(back_populates="voice", lazy="selectin")


class CorpusEntry(Base):
    __tablename__ = "corpus_entries"

    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        Enum(CorpusCategoryEnum, name="corpus_category_enum", native_enum=False),
        nullable=False,
    )
    expected_intent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    # Relationships
    samples: Mapped[list["SpeechSample"]] = relationship(back_populates="corpus_entry", lazy="selectin")


class SpeechSample(Base):
    __tablename__ = "speech_samples"

    corpus_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus_entries.id"), nullable=False
    )
    voice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voices.id"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=16000)
    status: Mapped[str] = mapped_column(
        Enum(SampleStatusEnum, name="sample_status_enum", native_enum=False),
        nullable=False,
        default=SampleStatusEnum.pending,
    )

    # Relationships
    corpus_entry: Mapped["CorpusEntry"] = relationship(back_populates="samples", lazy="selectin")
    voice: Mapped["Voice"] = relationship(back_populates="samples", lazy="selectin")
