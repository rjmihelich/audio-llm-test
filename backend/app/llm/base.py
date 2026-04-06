"""Abstract LLM backend protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..audio.types import AudioBuffer


@dataclass
class LLMResponse:
    """Response from an LLM backend."""

    text: str
    audio: AudioBuffer | None = None  # If the LLM returns audio (e.g., GPT-4o)
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    raw_response: dict = field(default_factory=dict)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an LLM backend."""

    requests_per_minute: int = 60
    tokens_per_minute: int = 100_000
    max_concurrent: int = 10


@runtime_checkable
class LLMBackend(Protocol):
    """Common interface for all LLM backends."""

    @property
    def name(self) -> str: ...

    @property
    def supports_audio_input(self) -> bool: ...

    @property
    def rate_limit(self) -> RateLimitConfig: ...

    async def query_with_audio(
        self,
        audio: AudioBuffer,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse: ...

    async def query_with_text(
        self,
        text: str,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse: ...


@runtime_checkable
class ASRBackend(Protocol):
    """Interface for speech-to-text backends."""

    @property
    def name(self) -> str: ...

    async def transcribe(self, audio: AudioBuffer) -> Transcription: ...


@dataclass
class Transcription:
    """Result of speech-to-text transcription."""

    text: str
    language: str = ""
    confidence: float = 0.0
    word_timestamps: list[dict] | None = None
    latency_ms: float = 0.0
