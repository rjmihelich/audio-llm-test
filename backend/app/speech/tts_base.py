"""Abstract TTS provider protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..audio.types import AudioBuffer


@dataclass
class VoiceInfo:
    """Metadata about a single TTS voice."""

    provider: str
    voice_id: str
    name: str
    gender: str  # male/female/neutral
    age_group: str  # child/young_adult/adult/senior
    accent: str
    language: str


@runtime_checkable
class TTSProvider(Protocol):
    """Interface that every TTS backend must satisfy."""

    provider_name: str

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer: ...

    async def list_voices(self) -> list[VoiceInfo]: ...
