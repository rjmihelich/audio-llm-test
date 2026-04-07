"""Speech corpus and TTS API endpoints."""

from __future__ import annotations

import logging
import traceback
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func
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


def _load_tts_provider(provider_name: str):
    """Instantiate a TTS provider by name."""
    if provider_name == "edge":
        from backend.app.speech.tts_edge import EdgeTTSProvider
        return EdgeTTSProvider()
    elif provider_name == "gtts":
        from backend.app.speech.tts_gtts import GTTSProvider
        return GTTSProvider()
    elif provider_name == "espeak":
        from backend.app.speech.tts_espeak import ESpeakTTSProvider
        return ESpeakTTSProvider()
    elif provider_name == "openai":
        from backend.app.speech.tts_openai import OpenAITTSProvider
        return OpenAITTSProvider(api_key=settings.openai_api_key or "")
    elif provider_name == "piper":
        from backend.app.speech.tts_piper import PiperTTSProvider
        return PiperTTSProvider()
    elif provider_name == "coqui":
        from backend.app.speech.tts_coqui import CoquiTTSProvider
        return CoquiTTSProvider()
    elif provider_name == "bark":
        from backend.app.speech.tts_bark import BarkTTSProvider
        return BarkTTSProvider()
    else:
        return None


@router.post("/generate-wavs", response_model=GenerateWavsResponse)
async def generate_wavs(
    request: GenerateWavsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create sample records AND generate WAV files in one step.

    This combines synthesize + generate-direct: builds the corpus × voice
    matrix, creates pending SpeechSample rows, then immediately renders
    each WAV file to disk.
    """
    from pathlib import Path
    import soundfile as sf

    # --- Build corpus entries query ---
    corpus_stmt = select(CorpusEntry)
    if request.categories:
        corpus_stmt = corpus_stmt.where(CorpusEntry.category.in_(request.categories))
    if request.languages:
        corpus_stmt = corpus_stmt.where(CorpusEntry.language.in_(request.languages))
    if request.max_corpus:
        corpus_stmt = corpus_stmt.limit(request.max_corpus)
    corpus_entries = (await session.execute(corpus_stmt)).scalars().all()

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
    voices = (await session.execute(voice_stmt)).scalars().all()

    if not corpus_entries:
        raise HTTPException(400, "No corpus entries matched your filters. Seed the corpus first.")
    if not voices:
        raise HTTPException(400, "No voices matched your filters. Sync voices first.")

    # --- Filter to only providers we can actually generate with ---
    supported_providers = {"edge", "gtts", "espeak", "openai", "piper", "coqui", "bark"}
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
        # Trim corpus to fit within cap
        max_corpus_for_cap = max(1, max_total // len(voices))
        corpus_entries = corpus_entries[:max_corpus_for_cap]
        logger.info(f"Capped corpus to {max_corpus_for_cap} entries (total would be {total_possible}, cap={max_total})")

    # --- Create sample records ---
    samples_by_provider: dict[str, list[SpeechSample]] = {}
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
            samples_by_provider.setdefault(provider_str, []).append(sample)
            total += 1
    await session.commit()

    # --- Generate WAV files provider by provider ---
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
        errors=errors[:50],  # cap error list
    )


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
