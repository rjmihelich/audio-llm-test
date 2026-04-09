"""Prompt model — reusable system prompt library."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Prompt(Base):
    __tablename__ = "prompts"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
