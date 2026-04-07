"""Speech corpus and TTS API endpoints."""

from __future__ import annotations

import logging
import traceback
import uuid

import asyncio
import json as json_mod

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import asc, desc, distinct, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import get_session
from backend.app.models.speech import CorpusEntry, SpeechSample, Voice
from backend.app.speech.corpus import (
    COMMAND_TEMPLATES,
    HARVARD_SENTENCES,
    MULTILINGUAL_TEMPLATES,
    expand_templates,
    expand_templates_multilingual,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class VoiceResponse(BaseModel):
    provider: str
    voice_id: str
    name: str
    gender: str
    age_group: str
    accent: str
    language: str


class CorpusEntryResponse(BaseModel):
    id: str
    text: str
    category: str
    expected_intent: str
    expected_action: str | None = None
    language: str = "en"


class SynthesizeRequest(BaseModel):
    corpus_entry_ids: list[str] | None = None
    voice_ids: list[str] | None = None
    categories: list[str] | None = None
    languages: list[str] | None = None
    # Voice filters
    providers: list[str] | None = None
    genders: list[str] | None = None
    voice_languages: list[str] | None = None
    # Limits
    max_corpus: int | None = None
    max_voices: int | None = None


class SynthesizeResponse(BaseModel):
    task_id: str
    total_combinations: int
    status: str = "queued"


class SyncVoicesResponse(BaseModel):
    synced: int
    providers: list[str]
    errors: list[str]


@router.get("/stats")
async def speech_stats(
    session: AsyncSession = Depends(get_session),
):
    """Return speech sample counts grouped by provider and status."""
    stmt = (
        select(
            Voice.provider,
            SpeechSample.status,
            func.count().label("cnt"),
        )
        .join(Voice, SpeechSample.voice_id == Voice.id)
        .group_by(Voice.provider, SpeechSample.status)
    )
    rows = (await session.execute(stmt)).all()

    by_provider: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for provider, status, cnt in rows:
        prov = provider.value if hasattr(provider, "value") else provider
        stat = status.value if hasattr(status, "value") else status
        by_provider.setdefault(prov, {})[stat] = cnt
        totals[stat] = totals.get(stat, 0) + cnt

    return {"by_provider": by_provider, "totals": totals}


@router.post("/voices/sync", response_model=SyncVoicesResponse)
async def sync_voices(
    session: AsyncSession = Depends(get_session),
):
    """Sync voices from all configured TTS providers into the database.

    Fetches available voices from each provider whose API key is configured,
    inserts new ones, and skips duplicates (matched by provider + voice_id).
    """
    from backend.app.speech.tts_openai import OpenAITTSProvider
    from backend.app.speech.tts_base import VoiceInfo

    synced = 0
    providers_synced: list[str] = []
    errors: list[str] = []

    # Load existing voices to skip duplicates
    existing_result = await session.execute(select(Voice))
    existing = {(v.provider, v.voice_id) for v in existing_result.scalars().all()}

    async def _insert_voices(voice_infos: list[VoiceInfo], provider_name: str):
        nonlocal synced
        count = 0
        for vi in voice_infos:
            if (vi.provider, vi.voice_id) in existing:
                continue
            voice = Voice(
                provider=vi.provider,
                voice_id=vi.voice_id,
                name=vi.name,
                gender=vi.gender,
                age_group=vi.age_group,
                accent=vi.accent,
                language=vi.language,
            )
            session.add(voice)
            existing.add((vi.provider, vi.voice_id))
            count += 1
        synced += count
        if count > 0:
            providers_synced.append(f"{provider_name} ({count} voices)")

    # OpenAI — always available (hardcoded voice list, no API call needed)
    try:
        openai_provider = OpenAITTSProvider(api_key=settings.openai_api_key or "dummy")
        openai_voices = await openai_provider.list_voices()
        await _insert_voices(openai_voices, "openai")
    except Exception as e:
        errors.append(f"openai: {e}")

    # ElevenLabs — needs API key
    if settings.elevenlabs_api_key:
        try:
            from backend.app.speech.tts_elevenlabs import ElevenLabsTTSProvider
            el_provider = ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key)
            el_voices = await el_provider.list_voices()
            await _insert_voices(el_voices, "elevenlabs")
            await el_provider.close()
        except Exception as e:
            errors.append(f"elevenlabs: {e}")

    # Google — needs credentials (GOOGLE_APPLICATION_CREDENTIALS env var)
    if settings.google_api_key:
        try:
            from backend.app.speech.tts_google import GoogleTTSProvider
            google_provider = GoogleTTSProvider()
            google_voices = await google_provider.list_voices()
            await _insert_voices(google_voices, "google")
        except Exception as e:
            errors.append(f"google: {e}")

    # --- Free / open-source providers (no API key needed) ---

    # Edge TTS — Microsoft's free neural TTS
    try:
        from backend.app.speech.tts_edge import EdgeTTSProvider
        edge_provider = EdgeTTSProvider()
        edge_voices = await edge_provider.list_voices()
        await _insert_voices(edge_voices, "edge")
    except ImportError:
        errors.append("edge: edge-tts package not installed (pip install edge-tts)")
    except Exception as e:
        errors.append(f"edge: {e}")

    # gTTS — Google Translate free TTS
    try:
        from backend.app.speech.tts_gtts import GTTSProvider
        gtts_provider = GTTSProvider()
        gtts_voices = await gtts_provider.list_voices()
        await _insert_voices(gtts_voices, "gtts")
    except ImportError:
        errors.append("gtts: gTTS package not installed (pip install gTTS)")
    except Exception as e:
        errors.append(f"gtts: {e}")

    # Piper — fast local neural TTS
    try:
        from backend.app.speech.tts_piper import PiperTTSProvider
        piper_provider = PiperTTSProvider()
        piper_voices = await piper_provider.list_voices()
        await _insert_voices(piper_voices, "piper")
    except ImportError:
        errors.append("piper: piper-tts package not installed (pip install piper-tts)")
    except Exception as e:
        errors.append(f"piper: {e}")

    # Coqui TTS — open-source multi-model
    try:
        from backend.app.speech.tts_coqui import CoquiTTSProvider
        coqui_provider = CoquiTTSProvider()
        coqui_voices = await coqui_provider.list_voices()
        await _insert_voices(coqui_voices, "coqui")
    except ImportError:
        errors.append("coqui: TTS package not installed (pip install TTS)")
    except Exception as e:
        errors.append(f"coqui: {e}")

    # Bark — Suno's text-to-audio
    try:
        from backend.app.speech.tts_bark import BarkTTSProvider
        bark_provider = BarkTTSProvider()
        bark_voices = await bark_provider.list_voices()
        await _insert_voices(bark_voices, "bark")
    except ImportError:
        errors.append("bark: suno-bark package not installed (pip install suno-bark)")
    except Exception as e:
        errors.append(f"bark: {e}")

    # Azure Cognitive Services Speech — paid, supports expressive styles
    if settings.azure_speech_key:
        try:
            from backend.app.speech.tts_azure import AzureTTSProvider
            azure_provider = AzureTTSProvider(
                speech_key=settings.azure_speech_key,
                speech_region=settings.azure_speech_region,
            )
            azure_voices = await azure_provider.list_voices()
            await _insert_voices(azure_voices, "azure")
        except ImportError:
            errors.append("azure: azure-cognitiveservices-speech not installed (pip install azure-cognitiveservices-speech)")
        except Exception as e:
            errors.append(f"azure: {e}")

    # eSpeak / pyttsx3 — system TTS
    try:
        from backend.app.speech.tts_espeak import ESpeakTTSProvider
        espeak_provider = ESpeakTTSProvider()
        espeak_voices = await espeak_provider.list_voices()
        await _insert_voices(espeak_voices, "espeak")
    except ImportError:
        errors.append("espeak: pyttsx3 package not installed (pip install pyttsx3)")
    except Exception as e:
        errors.append(f"espeak: {e}")

    try:
        await session.commit()
    except Exception as e:
        logger.error(f"Failed to commit synced voices: {e}\n{traceback.format_exc()}")
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save synced voices to database ({type(e).__name__}): {e}",
        )

    return SyncVoicesResponse(
        synced=synced,
        providers=providers_synced,
        errors=errors,
    )


@router.get("/voices", response_model=list[VoiceResponse])
async def list_voices(
    provider: str | None = None,
    gender: str | None = None,
    language: str | None = None,
    accent: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """List available TTS voices with optional filtering."""
    stmt = select(Voice)
    if provider is not None:
        stmt = stmt.where(Voice.provider == provider)
    if gender is not None:
        stmt = stmt.where(Voice.gender == gender)
    if language is not None:
        stmt = stmt.where(Voice.language == language)
    if accent is not None:
        stmt = stmt.where(Voice.accent == accent)

    result = await session.execute(stmt)
    voices = result.scalars().all()
    return [
        VoiceResponse(
            provider=v.provider,
            voice_id=v.voice_id,
            name=v.name,
            gender=v.gender,
            age_group=v.age_group,
            accent=v.accent or "",
            language=v.language,
        )
        for v in voices
    ]


@router.get("/corpus", response_model=list[CorpusEntryResponse])
async def list_corpus(
    category: str | None = None,
    language: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """List corpus entries with optional filtering."""
    stmt = select(CorpusEntry)
    if category is not None:
        stmt = stmt.where(CorpusEntry.category == category)
    if language is not None:
        stmt = stmt.where(CorpusEntry.language == language)
    stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    entries = result.scalars().all()
    return [
        CorpusEntryResponse(
            id=str(e.id),
            text=e.text,
            category=e.category,
            expected_intent=e.expected_intent or "",
            expected_action=e.expected_action,
            language=e.language,
        )
        for e in entries
    ]


@router.get("/corpus/stats")
async def corpus_stats(session: AsyncSession = Depends(get_session)):
    # Query corpus_entries grouped by category
    cat_stmt = select(CorpusEntry.category, func.count()).group_by(CorpusEntry.category)
    cat_result = await session.execute(cat_stmt)
    by_category = {row[0]: row[1] for row in cat_result.all()}

    # Query by language
    lang_stmt = select(CorpusEntry.language, func.count()).group_by(CorpusEntry.language)
    lang_result = await session.execute(lang_stmt)
    by_language = {row[0]: row[1] for row in lang_result.all()}

    total_stmt = select(func.count()).select_from(CorpusEntry)
    total = (await session.execute(total_stmt)).scalar() or 0

    return {"by_category": by_category, "by_language": by_language, "total": total}


class SeedCorpusRequest(BaseModel):
    languages: list[str] | None = None  # e.g. ["en", "es", "fr"]; None = English only
    per_category: int = 50  # how many expanded entries per category


class GeneratePreview(BaseModel):
    corpus_entries: int
    voices: int
    total_combinations: int
    estimated_size_mb: float
    avg_duration_s: float


# Default estimate: 22050 Hz, 16-bit mono ≈ 44.1 KB/s, avg utterance ~3s ≈ 132 KB
_DEFAULT_AVG_BYTES = 132_000

@router.post("/synthesize/preview", response_model=GeneratePreview)
async def synthesize_preview(
    request: SynthesizeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Preview how many WAV files a synthesis run would create."""
    corpus_stmt = select(func.count()).select_from(CorpusEntry)
    if request.categories:
        corpus_stmt = corpus_stmt.where(CorpusEntry.category.in_(request.categories))
    if request.languages:
        corpus_stmt = corpus_stmt.where(CorpusEntry.language.in_(request.languages))
    corpus_count = (await session.execute(corpus_stmt)).scalar() or 0
    if request.max_corpus and corpus_count > request.max_corpus:
        corpus_count = request.max_corpus

    voice_stmt = select(func.count()).select_from(Voice)
    if request.voice_ids:
        try:
            ids = [uuid.UUID(vid) for vid in request.voice_ids]
        except ValueError:
            ids = []
        voice_stmt = voice_stmt.where(Voice.id.in_(ids))
    if request.providers:
        voice_stmt = voice_stmt.where(Voice.provider.in_(request.providers))
    if request.genders:
        voice_stmt = voice_stmt.where(Voice.gender.in_(request.genders))
    if request.voice_languages:
        voice_stmt = voice_stmt.where(Voice.language.in_(request.voice_languages))
    voice_count = (await session.execute(voice_stmt)).scalar() or 0
    if request.max_voices and voice_count > request.max_voices:
        voice_count = request.max_voices

    total = corpus_count * voice_count

    # Try to compute actual average from existing ready samples
    avg_stmt = select(
        func.avg(SpeechSample.duration_s),
        func.avg(SpeechSample.sample_rate),
    ).where(SpeechSample.status == "ready")
    avg_result = await session.execute(avg_stmt)
    row = avg_result.one_or_none()
    avg_dur = float(row[0]) if row and row[0] else 3.0
    avg_rate = float(row[1]) if row and row[1] else 22050.0

    # WAV size: sample_rate × 2 bytes (16-bit) × 1 channel × duration + 44 byte header
    avg_bytes = avg_rate * 2 * avg_dur + 44
    estimated_mb = (total * avg_bytes) / (1024 * 1024)

    return GeneratePreview(
        corpus_entries=corpus_count,
        voices=voice_count,
        total_combinations=total,
        estimated_size_mb=round(estimated_mb, 1),
        avg_duration_s=round(avg_dur, 1),
    )


@router.post("/corpus/seed")
async def seed_corpus(
    request: SeedCorpusRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Seed the corpus with Harvard sentences and command templates.

    Pass ``{"languages": ["en", "es", "fr", ...]}`` to also generate
    multilingual corpus entries. If omitted, only English is generated.
    """
    languages = (request.languages if request else None) or ["en"]
    per_category = request.per_category if request else 50
    count = 0

    try:
        # ---- English content ----
        if "en" in languages:
            # Insert Harvard sentences
            for text in HARVARD_SENTENCES:
                entry = CorpusEntry(
                    text=text,
                    category="harvard_sentence",
                    expected_intent="speech_recognition",
                    expected_action=None,
                    language="en",
                )
                session.add(entry)
                count += 1

            # Expand English command templates
            for category in COMMAND_TEMPLATES:
                try:
                    expanded = expand_templates(category, per_category)
                except Exception as e:
                    logger.error(f"Failed to expand templates for category '{category}': {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Template expansion failed for category '{category}': {e}",
                    )
                for text, expected_intent, expected_action in expanded:
                    entry = CorpusEntry(
                        text=text,
                        category=category,
                        expected_intent=expected_intent,
                        expected_action=expected_action,
                        language="en",
                    )
                    session.add(entry)
                    count += 1

        # ---- Multilingual content ----
        for lang in languages:
            if lang == "en":
                continue  # already handled above
            if lang not in MULTILINGUAL_TEMPLATES:
                logger.warning(f"No multilingual templates for language '{lang}', skipping")
                continue
            for category in MULTILINGUAL_TEMPLATES[lang]:
                try:
                    expanded = expand_templates_multilingual(category, lang, per_category)
                except Exception as e:
                    logger.error(f"Failed to expand {lang}/{category}: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Template expansion failed for {lang}/{category}: {e}",
                    )
                for text, expected_intent, expected_action in expanded:
                    entry = CorpusEntry(
                        text=text,
                        category=category,
                        expected_intent=expected_intent,
                        expected_action=expected_action,
                        language=lang,
                    )
                    session.add(entry)
                    count += 1

        await session.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to seed corpus: {e}\n{traceback.format_exc()}")
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to seed corpus ({type(e).__name__}): {e}",
        )

    return {"status": "seeded", "entries_created": count, "languages": languages}


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_speech(
    request: SynthesizeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Trigger batch TTS generation for corpus entries x voices.

    This creates SpeechSample records with status=pending for all
    specified combinations. The actual TTS generation is the worker's job.
    """
    try:
        # Build corpus entry query
        corpus_stmt = select(CorpusEntry)
        if request.corpus_entry_ids:
            try:
                ids = [uuid.UUID(cid) for cid in request.corpus_entry_ids]
            except ValueError as e:
                raise HTTPException(400, f"Invalid corpus_entry_id: {e}")
            corpus_stmt = corpus_stmt.where(CorpusEntry.id.in_(ids))
        if request.categories:
            corpus_stmt = corpus_stmt.where(CorpusEntry.category.in_(request.categories))
        if request.languages:
            corpus_stmt = corpus_stmt.where(CorpusEntry.language.in_(request.languages))

        if request.max_corpus:
            corpus_stmt = corpus_stmt.limit(request.max_corpus)

        corpus_result = await session.execute(corpus_stmt)
        corpus_entries = corpus_result.scalars().all()

        # Build voice query
        voice_stmt = select(Voice)
        if request.voice_ids:
            try:
                ids = [uuid.UUID(vid) for vid in request.voice_ids]
            except ValueError as e:
                raise HTTPException(400, f"Invalid voice_id: {e}")
            voice_stmt = voice_stmt.where(Voice.id.in_(ids))
        if request.providers:
            voice_stmt = voice_stmt.where(Voice.provider.in_(request.providers))
        if request.genders:
            voice_stmt = voice_stmt.where(Voice.gender.in_(request.genders))
        if request.voice_languages:
            voice_stmt = voice_stmt.where(Voice.language.in_(request.voice_languages))
        if request.max_voices:
            voice_stmt = voice_stmt.limit(request.max_voices)

        voice_result = await session.execute(voice_stmt)
        voices = voice_result.scalars().all()

        if not corpus_entries and not voices:
            raise HTTPException(
                400,
                "No corpus entries or voices found. Seed the corpus first "
                "(POST /api/speech/corpus/seed) and sync voices "
                "(POST /api/speech/voices/sync).",
            )
        if not corpus_entries:
            raise HTTPException(
                400,
                f"No corpus entries matched the filters "
                f"(categories={request.categories}, languages={request.languages}). "
                f"Seed the corpus first (POST /api/speech/corpus/seed).",
            )
        if not voices:
            raise HTTPException(
                400,
                f"No voices matched the filters (voice_ids={request.voice_ids}). "
                f"Sync voices first (POST /api/speech/voices/sync).",
            )

        task_id = str(uuid.uuid4())
        total = 0

        for entry in corpus_entries:
            for voice in voices:
                provider_str = voice.provider.value if hasattr(voice.provider, 'value') else voice.provider
                file_path = str(
                    settings.audio_storage_path
                    / f"{provider_str}_{voice.voice_id}"
                    / f"{entry.id}.wav"
                )
                sample = SpeechSample(
                    corpus_entry_id=entry.id,
                    voice_id=voice.id,
                    file_path=file_path,
                    duration_s=0.0,
                    sample_rate=settings.default_sample_rate,
                    status="pending",
                )
                session.add(sample)
                total += 1

        await session.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create synthesis task: {e}\n{traceback.format_exc()}")
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create synthesis task ({type(e).__name__}): {e}",
        )

    return SynthesizeResponse(
        task_id=task_id,
        total_combinations=total,
        status="queued",
    )


class GenerateDirectRequest(BaseModel):
    provider: str = "edge"
    voice_id: str | None = None
    categories: list[str] | None = None
    limit: int = 10


class GenerateDirectResponse(BaseModel):
    generated: int
    failed: int
    errors: list[str]


@router.post("/generate-direct", response_model=GenerateDirectResponse)
async def generate_direct(
    request: GenerateDirectRequest,
    session: AsyncSession = Depends(get_session),
):
    """Generate WAV files synchronously without Redis/worker.

    Processes pending speech samples directly using the specified TTS provider.
    Use ``limit`` to control batch size (default 10).
    """
    from pathlib import Path

    # Load a TTS provider
    provider_name = request.provider
    try:
        if provider_name == "edge":
            from backend.app.speech.tts_edge import EdgeTTSProvider
            tts = EdgeTTSProvider()
        elif provider_name == "gtts":
            from backend.app.speech.tts_gtts import GTTSProvider
            tts = GTTSProvider()
        elif provider_name == "espeak":
            from backend.app.speech.tts_espeak import ESpeakTTSProvider
            tts = ESpeakTTSProvider()
        elif provider_name == "openai":
            from backend.app.speech.tts_openai import OpenAITTSProvider
            tts = OpenAITTSProvider(api_key=settings.openai_api_key or "")
        else:
            raise HTTPException(400, f"Unsupported provider for direct generation: {provider_name}")
    except ImportError as e:
        raise HTTPException(400, f"Provider '{provider_name}' not installed: {e}")

    # Find pending samples for this provider
    stmt = (
        select(SpeechSample)
        .join(Voice, SpeechSample.voice_id == Voice.id)
        .join(CorpusEntry, SpeechSample.corpus_entry_id == CorpusEntry.id)
        .where(SpeechSample.status == "pending")
        .where(Voice.provider == provider_name)
    )
    if request.voice_id:
        stmt = stmt.where(Voice.voice_id == request.voice_id)
    if request.categories:
        stmt = stmt.where(CorpusEntry.category.in_(request.categories))
    stmt = stmt.limit(request.limit)

    result = await session.execute(stmt)
    samples = result.scalars().all()

    if not samples:
        raise HTTPException(404, "No pending samples found for this provider/filter")

    generated = 0
    failed = 0
    errors: list[str] = []

    for sample in samples:
        try:
            # Get the voice_id and corpus text
            voice = sample.voice
            corpus_entry = sample.corpus_entry

            # Generate audio
            sample.status = "generating"
            await session.commit()

            audio_buf = await tts.synthesize(corpus_entry.text, voice.voice_id)

            # Save WAV file
            file_path = Path(sample.file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            import soundfile as sf
            sf.write(str(file_path), audio_buf.samples, audio_buf.sample_rate)

            # Update record
            sample.status = "ready"
            sample.duration_s = audio_buf.duration_s
            sample.sample_rate = audio_buf.sample_rate
            generated += 1

        except Exception as e:
            sample.status = "failed"
            failed += 1
            errors.append(f"{voice.voice_id}/{corpus_entry.id}: {e}")
            logger.error(f"TTS generation failed: {e}")

    await session.commit()

    return GenerateDirectResponse(
        generated=generated,
        failed=failed,
        errors=errors,
    )


class GenerateWavsRequest(BaseModel):
    """Combined request: create sample records + generate WAV files in one step."""
    categories: list[str] | None = None
    languages: list[str] | None = None
    providers: list[str] | None = None
    genders: list[str] | None = None
    voice_languages: list[str] | None = None
    max_corpus: int | None = None
    max_voices: int | None = None
    max_total: int = 500  # hard cap per request to avoid timeouts


class GenerateWavsResponse(BaseModel):
    total_queued: int
    generated: int
    failed: int
    errors: list[str]


_tts_provider_cache: dict[str, object] = {}


def _load_tts_provider(provider_name: str):
    """Instantiate a TTS provider by name.  Cached so models stay loaded."""
    if provider_name in _tts_provider_cache:
        return _tts_provider_cache[provider_name]

    provider = None
    if provider_name == "edge":
        from backend.app.speech.tts_edge import EdgeTTSProvider
        provider = EdgeTTSProvider()
    elif provider_name == "gtts":
        from backend.app.speech.tts_gtts import GTTSProvider
        provider = GTTSProvider()
    elif provider_name == "espeak":
        from backend.app.speech.tts_espeak import ESpeakTTSProvider
        provider = ESpeakTTSProvider()
    elif provider_name == "openai":
        from backend.app.speech.tts_openai import OpenAITTSProvider
        provider = OpenAITTSProvider(api_key=settings.openai_api_key or "")
    elif provider_name == "piper":
        from backend.app.speech.tts_piper import PiperTTSProvider
        provider = PiperTTSProvider()
    elif provider_name == "coqui":
        from backend.app.speech.tts_coqui import CoquiTTSProvider
        provider = CoquiTTSProvider()
    elif provider_name == "bark":
        from backend.app.speech.tts_bark import BarkTTSProvider
        provider = BarkTTSProvider()
    elif provider_name == "azure":
        from backend.app.speech.tts_azure import AzureTTSProvider
        provider = AzureTTSProvider(
            speech_key=getattr(settings, "azure_speech_key", "") or "",
            speech_region=getattr(settings, "azure_speech_region", "") or "eastus",
        )

    if provider is not None:
        _tts_provider_cache[provider_name] = provider
    return provider


async def _build_generation_plan(
    request: GenerateWavsRequest,
    session: AsyncSession,
) -> tuple[list, list, dict[str, list]]:
    """Build corpus × voice matrix and create pending SpeechSample records.

    Returns (corpus_entries, voices, samples_by_provider).
    """
    from pathlib import Path

    # --- Build corpus entries query ---
    corpus_stmt = select(CorpusEntry)
    if request.categories:
        corpus_stmt = corpus_stmt.where(CorpusEntry.category.in_(request.categories))
    if request.languages:
        corpus_stmt = corpus_stmt.where(CorpusEntry.language.in_(request.languages))
    if request.max_corpus:
        corpus_stmt = corpus_stmt.limit(request.max_corpus)
    corpus_entries = list((await session.execute(corpus_stmt)).scalars().all())

    # --- Build voices query ---
    voice_stmt = select(Voice)
    if request.providers:
        voice_stmt = voice_stmt.where(Voice.provider.in_(request.providers))
    if request.genders:
        voice_stmt = voice_stmt.where(Voice.gender.in_(request.genders))
    if request.voice_languages:
        voice_stmt = voice_stmt.where(Voice.language.in_(request.voice_languages))
    if request.max_voices:
        voice_stmt = voice_stmt.limit(request.max_voices)
    voices = list((await session.execute(voice_stmt)).scalars().all())

    if not corpus_entries:
        raise HTTPException(400, "No corpus entries matched your filters. Seed the corpus first.")
    if not voices:
        raise HTTPException(400, "No voices matched your filters. Sync voices first.")

    # --- Filter to only providers we can actually generate with ---
    supported_providers = {"edge", "gtts", "espeak", "openai", "piper", "coqui", "bark", "azure", "slurp"}
    voices = [
        v for v in voices
        if (v.provider.value if hasattr(v.provider, 'value') else v.provider) in supported_providers
    ]
    if not voices:
        raise HTTPException(400, "No voices from supported TTS providers matched your filters.")

    # --- Cap total combinations ---
    max_total = request.max_total
    total_possible = len(corpus_entries) * len(voices)
    if total_possible > max_total:
        max_corpus_for_cap = max(1, max_total // len(voices))
        corpus_entries = corpus_entries[:max_corpus_for_cap]
        logger.info(f"Capped corpus to {max_corpus_for_cap} entries (total would be {total_possible}, cap={max_total})")

    # --- Check existing samples: skip ready, reuse failed/pending ---
    existing_stmt = select(SpeechSample).where(
        SpeechSample.corpus_entry_id.in_([e.id for e in corpus_entries]),
        SpeechSample.voice_id.in_([v.id for v in voices]),
    )
    existing_result = await session.execute(existing_stmt)
    existing_map: dict[tuple, SpeechSample] = {}
    for s in existing_result.scalars().all():
        existing_map[(s.corpus_entry_id, s.voice_id)] = s

    # --- Build samples list: skip ready, retry failed, create new ---
    samples_by_provider: dict[str, list[SpeechSample]] = {}
    skipped = 0
    for entry in corpus_entries:
        for voice in voices:
            provider_str = voice.provider.value if hasattr(voice.provider, 'value') else voice.provider
            key = (entry.id, voice.id)
            existing = existing_map.get(key)

            if existing and existing.status == "ready":
                skipped += 1
                continue

            if existing and existing.status in ("failed", "pending", "generating"):
                # Reuse existing record — reset to pending for retry
                existing.status = "pending"
                samples_by_provider.setdefault(provider_str, []).append(existing)
                continue

            # Create new sample record
            file_path = str(
                settings.audio_storage_path
                / f"{provider_str}_{voice.voice_id}"
                / f"{entry.id}.wav"
            )
            sample = SpeechSample(
                corpus_entry_id=entry.id,
                voice_id=voice.id,
                file_path=file_path,
                duration_s=0.0,
                sample_rate=settings.default_sample_rate,
                status="pending",
            )
            session.add(sample)
            samples_by_provider.setdefault(provider_str, []).append(sample)
    await session.commit()

    return corpus_entries, voices, samples_by_provider


@router.post("/generate-wavs", response_model=GenerateWavsResponse)
async def generate_wavs(
    request: GenerateWavsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create sample records AND generate WAV files in one step.

    Returns final summary. For real-time progress, use POST /generate-wavs/stream.
    """
    import soundfile as sf
    from pathlib import Path

    _, _, samples_by_provider = await _build_generation_plan(request, session)

    total = sum(len(s) for s in samples_by_provider.values())
    generated = 0
    failed = 0
    errors: list[str] = []

    for provider_name, provider_samples in samples_by_provider.items():
        try:
            tts = _load_tts_provider(provider_name)
        except Exception as e:
            for s in provider_samples:
                s.status = "failed"
                failed += 1
            errors.append(f"{provider_name}: could not load provider – {e}")
            continue

        if tts is None:
            for s in provider_samples:
                s.status = "failed"
                failed += 1
            errors.append(f"{provider_name}: unsupported provider for direct generation")
            continue

        for sample in provider_samples:
            try:
                voice = sample.voice
                corpus_entry = sample.corpus_entry
                sample.status = "generating"
                await session.commit()

                audio_buf = await tts.synthesize(corpus_entry.text, voice.voice_id)

                fp = Path(sample.file_path)
                fp.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(fp), audio_buf.samples, audio_buf.sample_rate)

                sample.status = "ready"
                sample.duration_s = audio_buf.duration_s
                sample.sample_rate = audio_buf.sample_rate
                generated += 1
            except Exception as e:
                sample.status = "failed"
                failed += 1
                err_msg = f"{voice.voice_id}/{corpus_entry.id}: {e}"
                errors.append(err_msg)
                logger.error(f"TTS generation failed: {err_msg}")

    await session.commit()

    return GenerateWavsResponse(
        total_queued=total,
        generated=generated,
        failed=failed,
        errors=errors[:50],
    )


@router.post("/generate-wavs/stream")
async def generate_wavs_stream(
    request: GenerateWavsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Generate WAV files with real-time Server-Sent Events progress.

    Streams JSON events:
      {"type":"planning", "message": "..."}
      {"type":"start",    "total": N, "skipped": N}
      {"type":"loading",  "provider": "piper", "message": "Loading model..."}
      {"type":"progress", "generated": N, "failed": N, "total": N, "current": "voice/text...", "pct": 50.0}
      {"type":"error",    "message": "...", "generated": N, "failed": N, "total": N}
      {"type":"complete", "generated": N, "failed": N, "total": N, "errors": [...]}
    """
    import soundfile as sf
    from pathlib import Path

    # We move ALL work inside the generator so the SSE stream opens immediately
    # and the client gets feedback before the planning/model-loading phases.

    async def event_stream():
        generated = 0
        failed = 0
        errors: list[str] = []

        # --- Phase 1: planning (DB queries, dedup) ---
        yield f"data: {json_mod.dumps({'type': 'planning', 'message': 'Building generation plan...'})}\n\n"

        try:
            _, _, samples_by_provider = await _build_generation_plan(request, session)
        except HTTPException as e:
            yield f"data: {json_mod.dumps({'type': 'error', 'message': e.detail, 'generated': 0, 'failed': 0, 'total': 0})}\n\n"
            yield f"data: {json_mod.dumps({'type': 'complete', 'generated': 0, 'failed': 0, 'total': 0, 'errors': [e.detail]})}\n\n"
            return
        except Exception as e:
            msg = f"Planning failed: {type(e).__name__}: {e}"
            yield f"data: {json_mod.dumps({'type': 'error', 'message': msg, 'generated': 0, 'failed': 0, 'total': 0})}\n\n"
            yield f"data: {json_mod.dumps({'type': 'complete', 'generated': 0, 'failed': 0, 'total': 0, 'errors': [msg]})}\n\n"
            return

        total = sum(len(s) for s in samples_by_provider.values())

        # Send start event
        yield f"data: {json_mod.dumps({'type': 'start', 'total': total})}\n\n"

        if total == 0:
            yield f"data: {json_mod.dumps({'type': 'complete', 'generated': 0, 'failed': 0, 'total': 0, 'errors': []})}\n\n"
            return

        # --- Phase 2: generate per provider ---
        for provider_name, provider_samples in samples_by_provider.items():
            # Notify client we're loading the provider/model
            yield f"data: {json_mod.dumps({'type': 'loading', 'provider': provider_name, 'message': f'Loading {provider_name} model...'})}\n\n"

            try:
                tts = _load_tts_provider(provider_name)
            except Exception as e:
                for s in provider_samples:
                    s.status = "failed"
                    failed += 1
                err = f"{provider_name}: could not load provider – {e}"
                errors.append(err)
                yield f"data: {json_mod.dumps({'type': 'error', 'message': err, 'generated': generated, 'failed': failed, 'total': total})}\n\n"
                continue

            if tts is None:
                for s in provider_samples:
                    s.status = "failed"
                    failed += 1
                err = f"{provider_name}: unsupported provider"
                errors.append(err)
                yield f"data: {json_mod.dumps({'type': 'error', 'message': err, 'generated': generated, 'failed': failed, 'total': total})}\n\n"
                continue

            for sample in provider_samples:
                try:
                    voice = sample.voice
                    corpus_entry = sample.corpus_entry
                    sample.status = "generating"
                    await session.commit()

                    audio_buf = await tts.synthesize(corpus_entry.text, voice.voice_id)

                    fp = Path(sample.file_path)
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    sf.write(str(fp), audio_buf.samples, audio_buf.sample_rate)

                    sample.status = "ready"
                    sample.duration_s = audio_buf.duration_s
                    sample.sample_rate = audio_buf.sample_rate
                    generated += 1
                except Exception as e:
                    sample.status = "failed"
                    failed += 1
                    err_msg = f"{voice.voice_id}/{corpus_entry.text[:30]}: {type(e).__name__}: {e}"
                    errors.append(err_msg)
                    logger.error(f"TTS generation failed: {err_msg}")
                    yield f"data: {json_mod.dumps({'type': 'error', 'message': err_msg, 'generated': generated, 'failed': failed, 'total': total})}\n\n"

                done = generated + failed
                pct = (done / total * 100) if total > 0 else 0
                current_label = f"{voice.name}: {corpus_entry.text[:40]}"
                yield f"data: {json_mod.dumps({'type': 'progress', 'generated': generated, 'failed': failed, 'total': total, 'current': current_label, 'pct': round(pct, 1)})}\n\n"

        await session.commit()

        yield f"data: {json_mod.dumps({'type': 'complete', 'generated': generated, 'failed': failed, 'total': total, 'errors': errors[:50]})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-wavs/retry")
async def retry_failed_samples(
    request: dict = Body(default={}),
    session: AsyncSession = Depends(get_session),
):
    """Reset all failed SpeechSample records to pending.

    Optionally filter by provider(s) via ``{"providers": ["edge", "gtts"]}``.
    After resetting, hit the generate endpoint to process them.
    """
    stmt = select(SpeechSample).where(SpeechSample.status == "failed")

    providers = request.get("providers")
    if providers:
        stmt = stmt.join(Voice, SpeechSample.voice_id == Voice.id).where(
            Voice.provider.in_(providers)
        )

    result = await session.execute(stmt)
    samples = result.scalars().all()

    count = 0
    for sample in samples:
        sample.status = "pending"
        count += 1

    await session.commit()

    return {"reset": count}


# ---------------------------------------------------------------------------
# Sample browsing
# ---------------------------------------------------------------------------


class SampleBrowseResponse(BaseModel):
    id: str
    status: str
    file_path: str
    duration_s: float
    sample_rate: int
    created_at: str
    # Voice info
    voice_name: str
    voice_id_str: str  # the provider-specific voice_id string
    provider: str
    gender: str
    accent: str | None
    voice_language: str
    # Corpus info
    text: str
    category: str
    expected_intent: str | None
    expected_action: str | None
    corpus_language: str


class SampleBrowsePageResponse(BaseModel):
    items: list[SampleBrowseResponse]
    total: int
    limit: int
    offset: int


# Allowed sort columns mapped to their SQLAlchemy expressions
_SORT_COLUMNS = {
    "created_at": SpeechSample.created_at,
    "duration_s": SpeechSample.duration_s,
    "provider": Voice.provider,
    "category": CorpusEntry.category,
}


@router.get("/samples", response_model=SampleBrowsePageResponse)
async def browse_samples(
    status: str | None = None,
    provider: str | None = None,
    gender: str | None = None,
    language: str | None = None,
    corpus_language: str | None = None,
    category: str | None = None,
    accent: str | None = None,
    voice_name: str | None = None,
    text_search: str | None = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """Return a paginated, filterable list of speech samples with joined voice and corpus data."""
    # Clamp limit
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    # Base query
    base = select(SpeechSample).join(Voice).join(CorpusEntry)

    # Apply filters
    if status is not None:
        base = base.where(SpeechSample.status == status)
    if provider is not None:
        base = base.where(Voice.provider == provider)
    if gender is not None:
        base = base.where(Voice.gender == gender)
    if language is not None:
        base = base.where(Voice.language == language)
    if corpus_language is not None:
        base = base.where(CorpusEntry.language == corpus_language)
    if category is not None:
        base = base.where(CorpusEntry.category == category)
    if accent is not None:
        base = base.where(Voice.accent == accent)
    if voice_name is not None:
        base = base.where(Voice.name.ilike(f"%{voice_name}%"))
    if text_search is not None:
        base = base.where(CorpusEntry.text.ilike(f"%{text_search}%"))

    # Count total matching rows
    count_stmt = select(func.count()).select_from(
        base.with_only_columns(SpeechSample.id).subquery()
    )
    total = (await session.execute(count_stmt)).scalar() or 0

    # Sorting
    sort_col = _SORT_COLUMNS.get(sort_by, SpeechSample.created_at)
    order_func = desc if sort_dir.lower() == "desc" else asc
    query = base.order_by(order_func(sort_col)).offset(offset).limit(limit)

    result = await session.execute(query)
    samples = result.scalars().all()

    items = [
        SampleBrowseResponse(
            id=str(s.id),
            status=s.status.value if hasattr(s.status, "value") else s.status,
            file_path=s.file_path,
            duration_s=s.duration_s,
            sample_rate=s.sample_rate,
            created_at=s.created_at.isoformat() if s.created_at else "",
            voice_name=s.voice.name,
            voice_id_str=s.voice.voice_id,
            provider=s.voice.provider.value if hasattr(s.voice.provider, "value") else s.voice.provider,
            gender=s.voice.gender.value if hasattr(s.voice.gender, "value") else s.voice.gender,
            accent=s.voice.accent,
            voice_language=s.voice.language,
            text=s.corpus_entry.text,
            category=s.corpus_entry.category.value if hasattr(s.corpus_entry.category, "value") else s.corpus_entry.category,
            expected_intent=s.corpus_entry.expected_intent,
            expected_action=s.corpus_entry.expected_action,
            corpus_language=s.corpus_entry.language,
        )
        for s in samples
    ]

    return SampleBrowsePageResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/samples/filters")
async def sample_filters(session: AsyncSession = Depends(get_session)):
    """Return distinct values for each filterable field (for populating dropdowns)."""
    providers_q = select(distinct(Voice.provider))
    genders_q = select(distinct(Voice.gender))
    languages_q = select(distinct(Voice.language))
    accents_q = select(distinct(Voice.accent)).where(Voice.accent.is_not(None))
    categories_q = select(distinct(CorpusEntry.category))
    statuses_q = select(distinct(SpeechSample.status))

    (
        providers_res,
        genders_res,
        languages_res,
        accents_res,
        categories_res,
        statuses_res,
    ) = await asyncio.gather(
        session.execute(providers_q),
        session.execute(genders_q),
        session.execute(languages_q),
        session.execute(accents_q),
        session.execute(categories_q),
        session.execute(statuses_q),
    )

    def _vals(result):
        return sorted(
            v.value if hasattr(v, "value") else v
            for (v,) in result.all()
            if v is not None
        )

    return {
        "providers": _vals(providers_res),
        "genders": _vals(genders_res),
        "languages": _vals(languages_res),
        "accents": _vals(accents_res),
        "categories": _vals(categories_res),
        "statuses": _vals(statuses_res),
    }


@router.get("/samples/{sample_id}/audio")
async def get_sample_audio(
    sample_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Stream a generated speech sample audio file."""
    stmt = select(SpeechSample).where(SpeechSample.id == uuid.UUID(sample_id))
    result = await session.execute(stmt)
    sample = result.scalar_one_or_none()

    if sample is None:
        raise HTTPException(404, "Sample not found")

    if sample.status != "ready":
        raise HTTPException(400, f"Sample is not ready (status={sample.status})")

    from pathlib import Path

    file_path = Path(sample.file_path)
    if not file_path.exists():
        raise HTTPException(404, "Audio file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="audio/wav",
        filename=f"{sample_id}.wav",
    )


# ---------------------------------------------------------------------------
# SLURP import endpoint — scan existing audio files and register in DB
# ---------------------------------------------------------------------------

@router.post("/import-slurp")
async def import_slurp(
    max_per_scenario: int = Query(default=100, description="Max files per SLURP scenario"),
    session: AsyncSession = Depends(get_session),
):
    """Scan storage for SLURP audio files (WAV or FLAC) and import into DB.

    Looks in storage/audio/slurp_real/ and storage/slurp/ for audio files.
    Creates Voice, CorpusEntry, and SpeechSample records.
    """
    import subprocess
    import wave
    from pathlib import Path

    base = Path(settings.audio_storage_path).resolve().parent  # storage/
    audio_base = Path(settings.audio_storage_path).resolve()  # storage/audio/
    search_dirs = [
        audio_base / "slurp" / "audio" / "slurp_real",  # storage/audio/slurp/audio/slurp_real
        audio_base / "slurp" / "audio",
        audio_base / "slurp_real",
        audio_base / "slurp",
        base / "slurp" / "audio" / "slurp_real",
        base / "slurp" / "audio",
        base / "slurp",
    ]

    # Also check for annotation files
    annotation_dirs = [
        audio_base / "slurp" / "annotations",
        base / "slurp" / "annotations",
        audio_base / "slurp",
        base / "slurp",
    ]

    # Find all audio files (WAV and FLAC)
    audio_files: dict[str, Path] = {}
    for d in search_dirs:
        if not d.exists():
            continue
        for ext in ("*.wav", "*.flac"):
            for f in d.rglob(ext):
                audio_files[f.stem] = f  # key by stem (no extension)

    if not audio_files:
        raise HTTPException(404, f"No audio files found. Searched: {[str(d) for d in search_dirs]}")

    # Try to load annotations for metadata
    annotations: dict[str, dict] = {}
    for ad in annotation_dirs:
        if not ad.exists():
            continue
        for jsonl_file in ad.glob("*.jsonl"):
            try:
                with open(jsonl_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        entry = json_mod.loads(line)
                        # Map recordings to their entries
                        for rec in entry.get("recordings", []):
                            fname = rec.get("file", "")
                            stem = fname.rsplit(".", 1)[0] if "." in fname else fname
                            if stem:
                                annotations[stem] = entry
            except Exception:
                continue

    # SLURP scenario → category mapping
    SCENARIO_MAP = {
        "alarm": "general", "audio": "media", "calendar": "general",
        "cooking": "general", "datetime": "general", "email": "general",
        "general": "general", "iot": "general", "lists": "general",
        "music": "media", "news": "general", "play": "media",
        "qa": "general", "recommendation": "general", "social": "phone",
        "takeaway": "general", "transport": "navigation", "weather": "climate",
    }

    # Get or create SLURP voice
    voice_stmt = select(Voice).where(Voice.provider == "slurp")
    existing_voice = (await session.execute(voice_stmt)).scalar_one_or_none()

    if existing_voice is None:
        slurp_voice = Voice(
            provider="slurp",
            voice_id="slurp_real",
            name="SLURP Real Speaker",
            gender="neutral",
            age_group="adult",
            accent="mixed",
            language="en",
        )
        session.add(slurp_voice)
        await session.flush()
        voice_id = slurp_voice.id
    else:
        voice_id = existing_voice.id

    imported = 0
    skipped = 0
    converted = 0
    failed = 0
    scenario_counts: dict[str, int] = {}

    wav_output = base / "audio" / "slurp_real"
    wav_output.mkdir(parents=True, exist_ok=True)

    for stem, audio_path in audio_files.items():
        # Get annotation metadata if available
        ann = annotations.get(stem, {})
        scenario = ann.get("scenario", "general")
        category = SCENARIO_MAP.get(scenario, "general")
        sentence = ann.get("sentence", stem.replace("_", " ").replace("-", " "))
        intent = ann.get("intent", "")
        action = ann.get("action", "")

        # Cap per scenario
        sc = scenario_counts.get(scenario, 0)
        if sc >= max_per_scenario:
            skipped += 1
            continue

        # Convert FLAC → WAV if needed
        if audio_path.suffix.lower() == ".flac":
            wav_path = wav_output / f"{stem}.wav"
            if not wav_path.exists():
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(audio_path),
                         "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                         str(wav_path)],
                        capture_output=True, timeout=30, check=True,
                    )
                    converted += 1
                except Exception:
                    failed += 1
                    continue
            file_path = wav_path
        else:
            file_path = audio_path

        # Get duration
        try:
            with wave.open(str(file_path), "rb") as wf:
                duration_s = wf.getnframes() / wf.getframerate()
                sample_rate = wf.getframerate()
        except Exception:
            duration_s = 0.0
            sample_rate = 16000

        # Check if corpus entry exists
        existing_ce = (await session.execute(
            select(CorpusEntry).where(
                CorpusEntry.text == sentence,
                CorpusEntry.language == "en",
            )
        )).scalar_one_or_none()

        if existing_ce is None:
            corpus_entry = CorpusEntry(
                text=sentence,
                category=category,
                expected_intent=intent,
                expected_action=action or None,
                language="en",
            )
            session.add(corpus_entry)
            await session.flush()
            ce_id = corpus_entry.id
        else:
            ce_id = existing_ce.id

        # Check if sample exists
        existing_ss = (await session.execute(
            select(SpeechSample).where(
                SpeechSample.corpus_entry_id == ce_id,
                SpeechSample.voice_id == voice_id,
            )
        )).scalar_one_or_none()

        if existing_ss is None:
            sample = SpeechSample(
                corpus_entry_id=ce_id,
                voice_id=voice_id,
                file_path=str(file_path),
                duration_s=duration_s,
                sample_rate=sample_rate,
                status="ready",
            )
            session.add(sample)

        scenario_counts[scenario] = sc + 1
        imported += 1

        if imported % 200 == 0:
            await session.commit()

    await session.commit()

    return {
        "imported": imported,
        "converted": converted,
        "skipped": skipped,
        "failed": failed,
        "total_audio_files_found": len(audio_files),
        "has_annotations": len(annotations) > 0,
        "annotation_count": len(annotations),
        "by_scenario": scenario_counts,
    }
