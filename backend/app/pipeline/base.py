"""Abstract pipeline interface and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..audio.types import AudioBuffer
from ..llm.base import LLMResponse, Transcription


@dataclass
class PipelineInput:
    """Input to a test pipeline."""

    clean_speech: AudioBuffer
    original_text: str  # The text that was synthesized into speech
    expected_intent: str  # What the speech is asking for
    expected_action: str | None = None  # Expected structured action (for command matching)
    system_prompt: str = "You are a helpful in-car voice assistant."


@dataclass
class PipelineResult:
    """Output from a test pipeline, including all intermediate artifacts."""

    # Audio artifacts
    degraded_audio: AudioBuffer | None = None  # Speech + noise + echo
    echo_audio: AudioBuffer | None = None  # Just the echo component

    # ASR (Pipeline B only)
    transcription: Transcription | None = None

    # LLM response
    llm_response: LLMResponse | None = None

    # Metadata
    pipeline_type: str = ""
    total_latency_ms: float = 0.0
    error: str | None = None
    telephony_metadata: dict | None = None  # Populated by TelephonyPipeline


@runtime_checkable
class Pipeline(Protocol):
    """Interface for test execution pipelines."""

    @property
    def pipeline_type(self) -> str: ...

    async def execute(self, input: PipelineInput) -> PipelineResult: ...
