"""Voice catalog service that aggregates and queries voices across TTS providers."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from .tts_base import TTSProvider, VoiceInfo


class VoiceCatalog:
    """Aggregates voices from multiple TTS providers and supports filtered queries."""

    def __init__(self, providers: Sequence[TTSProvider] | None = None) -> None:
        self._providers: list[TTSProvider] = list(providers) if providers else []
        self._voices: list[VoiceInfo] = []
        self._loaded = False

    def add_provider(self, provider: TTSProvider) -> None:
        """Register an additional TTS provider."""
        self._providers.append(provider)
        self._loaded = False  # invalidate cache

    async def load(self) -> None:
        """Fetch voice listings from every registered provider."""
        self._voices = []
        for provider in self._providers:
            voices = await provider.list_voices()
            self._voices.extend(voices)
        self._loaded = True

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            await self.load()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def query_voices(
        self,
        *,
        gender: str | None = None,
        age_group: str | None = None,
        accent: str | None = None,
        language: str | None = None,
    ) -> list[VoiceInfo]:
        """Return voices matching **all** supplied filters.

        Omitted filters are not applied (i.e. ``None`` means "any").
        """
        await self._ensure_loaded()

        results: list[VoiceInfo] = []
        for v in self._voices:
            if gender is not None and v.gender != gender:
                continue
            if age_group is not None and v.age_group != age_group:
                continue
            if accent is not None and v.accent != accent:
                continue
            if language is not None and not v.language.startswith(language):
                continue
            results.append(v)
        return results

    async def get_diverse_voice_set(
        self,
        count: int,
        language: str = "en",
    ) -> list[VoiceInfo]:
        """Select up to *count* voices that maximise diversity.

        Diversity is measured across gender, age group, accent, and provider.
        The algorithm uses round-robin bucket sampling so that underrepresented
        attributes are surfaced first.
        """
        candidates = await self.query_voices(language=language)
        if not candidates:
            return []
        if len(candidates) <= count:
            return list(candidates)

        # Build buckets for each diversity axis.
        buckets: dict[str, dict[str, list[VoiceInfo]]] = {
            "gender": defaultdict(list),
            "age_group": defaultdict(list),
            "accent": defaultdict(list),
            "provider": defaultdict(list),
        }
        for v in candidates:
            buckets["gender"][v.gender].append(v)
            buckets["age_group"][v.age_group].append(v)
            buckets["accent"][v.accent].append(v)
            buckets["provider"][v.provider].append(v)

        selected: list[VoiceInfo] = []
        selected_ids: set[tuple[str, str]] = set()  # (provider, voice_id)

        def _add(voice: VoiceInfo) -> bool:
            key = (voice.provider, voice.voice_id)
            if key in selected_ids:
                return False
            selected.append(voice)
            selected_ids.add(key)
            return True

        # Round-robin across axes, picking from the smallest bucket first
        # to maximise coverage of rare attributes.
        axes = list(buckets.keys())
        axis_idx = 0
        bucket_cursors: dict[str, dict[str, int]] = {
            axis: defaultdict(int) for axis in axes
        }

        while len(selected) < count:
            made_progress = False
            for axis in axes:
                if len(selected) >= count:
                    break
                # Sort bucket keys by bucket size (smallest first) for diversity
                sorted_keys = sorted(
                    buckets[axis].keys(),
                    key=lambda k, a=axis: len(buckets[a][k]),
                )
                for key in sorted_keys:
                    if len(selected) >= count:
                        break
                    bucket = buckets[axis][key]
                    cursor = bucket_cursors[axis][key]
                    if cursor < len(bucket):
                        if _add(bucket[cursor]):
                            made_progress = True
                        bucket_cursors[axis][key] = cursor + 1

            if not made_progress:
                # All cursors exhausted; fill remainder from any remaining candidates.
                for v in candidates:
                    if len(selected) >= count:
                        break
                    _add(v)
                break

        return selected
