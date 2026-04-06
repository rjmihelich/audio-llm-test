"""Speech corpus and TTS API endpoints."""

from __future__ import annotations

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
    expand_templates,
)

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

    await session.commit()

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


@router.post("/corpus/seed")
async def seed_corpus(session: AsyncSession = Depends(get_session)):
    """Seed the corpus with Harvard sentences and command templates."""
    count = 0

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

    # Expand command templates (50 each)
    for category in COMMAND_TEMPLATES:
        expanded = expand_templates(category, 50)
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

    await session.commit()
    return {"status": "seeded", "entries_created": count}


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_speech(
    request: SynthesizeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Trigger batch TTS generation for corpus entries x voices.

    This creates SpeechSample records with status=pending for all
    specified combinations. The actual TTS generation is the worker's job.
    """
    # Build corpus entry query
    corpus_stmt = select(CorpusEntry)
    if request.corpus_entry_ids:
        corpus_stmt = corpus_stmt.where(
            CorpusEntry.id.in_([uuid.UUID(cid) for cid in request.corpus_entry_ids])
        )
    if request.categories:
        corpus_stmt = corpus_stmt.where(CorpusEntry.category.in_(request.categories))
    if request.languages:
        corpus_stmt = corpus_stmt.where(CorpusEntry.language.in_(request.languages))

    corpus_result = await session.execute(corpus_stmt)
    corpus_entries = corpus_result.scalars().all()

    # Build voice query
    voice_stmt = select(Voice)
    if request.voice_ids:
        voice_stmt = voice_stmt.where(
            Voice.id.in_([uuid.UUID(vid) for vid in request.voice_ids])
        )

    voice_result = await session.execute(voice_stmt)
    voices = voice_result.scalars().all()

    if not corpus_entries or not voices:
        raise HTTPException(400, "No corpus entries or voices matched the filters")

    task_id = str(uuid.uuid4())
    total = 0

    for entry in corpus_entries:
        for voice in voices:
            file_path = str(
                settings.audio_storage_path
                / f"{voice.provider}_{voice.voice_id}"
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

    return SynthesizeResponse(
        task_id=task_id,
        total_combinations=total,
        status="queued",
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
