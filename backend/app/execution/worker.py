"""arq worker settings and task definitions for background test execution."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from arq.connections import RedisSettings
from sqlalchemy import select

from ..config import settings
from ..models.base import async_session
from ..models.run import TestRun, TestResult
from ..models.test import TestCase, TestSuite
from ..models.speech import SpeechSample, CorpusEntry, Voice
from ..execution.scheduler import TestScheduler, TestCaseConfig, TestResultRecord
from ..llm.openai_audio import OpenAIAudioBackend
from ..llm.gemini import GeminiBackend
from ..llm.anthropic_backend import AnthropicBackend
from ..llm.ollama import OllamaBackend
from ..llm.whisper import WhisperAPIBackend, WhisperLocalBackend
from ..llm.deepgram_stt import DeepgramSTTBackend
from ..evaluation.command_match import CommandMatchEvaluator
from ..evaluation.llm_judge import LLMJudgeEvaluator
from ..speech.tts_openai import OpenAITTSProvider
try:
    from ..speech.tts_google import GoogleTTSProvider
except ImportError:
    GoogleTTSProvider = None  # type: ignore
try:
    from ..speech.tts_elevenlabs import ElevenLabsTTSProvider
except ImportError:
    ElevenLabsTTSProvider = None  # type: ignore
from ..audio.io import save_audio
from ..api.ws import broadcast_progress

logger = logging.getLogger(__name__)


def _init_backend(backend_key: str):
    """Instantiate an LLM backend from a backend key like 'openai:gpt-4o-audio-preview'."""
    prefix, _, model = backend_key.partition(":")
    if prefix == "openai":
        kwargs = {"api_key": settings.openai_api_key}
        if model:
            kwargs["model"] = model
        return OpenAIAudioBackend(**kwargs)
    elif prefix == "gemini":
        kwargs = {"api_key": settings.google_api_key}
        if model:
            kwargs["model"] = model
        return GeminiBackend(**kwargs)
    elif prefix == "anthropic":
        kwargs = {"api_key": settings.anthropic_api_key}
        if model:
            kwargs["model"] = model
        return AnthropicBackend(**kwargs)
    elif prefix == "ollama":
        kwargs = {"base_url": settings.ollama_base_url}
        if model:
            kwargs["model"] = model
        return OllamaBackend(**kwargs)
    else:
        raise ValueError(f"Unknown LLM backend prefix: {prefix}")


async def run_test_suite(ctx: dict, run_id: str):
    """Background task: execute all test cases in a test run.

    This is the main entry point called by the arq worker.
    It loads the test suite configuration, creates the execution
    scheduler, and runs all test cases with progress reporting.
    """
    logger.info(f"Starting test run: {run_id}")

    async with async_session() as session:
        try:
            # 1. Load TestRun
            run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
            test_run = await session.get(TestRun, run_uuid)
            if not test_run:
                logger.error(f"TestRun not found: {run_id}")
                return

            # 2. Load TestSuite with test cases
            test_suite = await session.get(TestSuite, test_run.test_suite_id)
            if not test_suite:
                logger.error(f"TestSuite not found: {test_run.test_suite_id}")
                return

            # Load test cases for this suite
            tc_result = await session.execute(
                select(TestCase).where(TestCase.test_suite_id == test_suite.id)
            )
            test_cases = list(tc_result.scalars().all())

            # Eagerly load speech_sample and corpus_entry for each test case
            for tc in test_cases:
                if tc.speech_sample_id:
                    sample = await session.get(SpeechSample, tc.speech_sample_id)
                    if sample and sample.corpus_entry_id:
                        await session.get(CorpusEntry, sample.corpus_entry_id)

            # 3. Query already-completed TestResult test_case_ids for resume
            completed_result = await session.execute(
                select(TestResult.test_case_id).where(TestResult.test_run_id == run_uuid)
            )
            completed_tc_ids = {str(row) for row in completed_result.scalars().all()}

            # Also collect deterministic hashes of completed cases for the scheduler
            completed_hashes: set[str] = set()
            for tc in test_cases:
                if str(tc.id) in completed_tc_ids:
                    completed_hashes.add(tc.deterministic_hash)

            # 4. Update TestRun status to running
            test_run.status = "running"
            test_run.started_at = datetime.utcnow()
            test_run.total_cases = len(test_cases)
            await session.commit()

            # 5. Initialize LLM backends
            unique_backends = {tc.llm_backend for tc in test_cases}
            backends: dict[str, object] = {}
            for backend_key in unique_backends:
                try:
                    backends[backend_key] = _init_backend(backend_key)
                except Exception as e:
                    logger.error(f"Failed to init backend {backend_key}: {e}")

            # 6. Initialize evaluators
            # Use the first OpenAI backend as the judge LLM, or create one
            judge_backend = None
            for bk, bv in backends.items():
                if bk.startswith("openai:"):
                    judge_backend = bv
                    break
            if judge_backend is None and settings.openai_api_key:
                judge_backend = OpenAIAudioBackend(api_key=settings.openai_api_key)

            evaluators: dict[str, object] = {
                "command_match": CommandMatchEvaluator(),
            }
            if judge_backend:
                evaluators["llm_judge"] = LLMJudgeEvaluator(judge_backend=judge_backend)

            # 7. Initialize ASR backend if any test case uses asr_text pipeline
            asr_backend = None
            if any(tc.pipeline == "asr_text" for tc in test_cases):
                if settings.default_stt_backend.startswith("deepgram") and settings.deepgram_api_key:
                    asr_backend = DeepgramSTTBackend(api_key=settings.deepgram_api_key)
                elif settings.openai_api_key and not settings.openai_api_key.startswith("sk-..."):
                    asr_backend = WhisperAPIBackend(api_key=settings.openai_api_key)
                else:
                    # Fall back to local Whisper (free, no API key needed)
                    logger.info("No valid STT API key found — using local Whisper")
                    asr_backend = WhisperLocalBackend(model_size="base")
                    # Pre-load the model to avoid concurrent loading issues
                    asr_backend._ensure_model()
                    logger.info("Whisper model loaded successfully")

            # 8. Convert TestCase DB objects to TestCaseConfig
            test_case_configs: list[TestCaseConfig] = []
            for tc in test_cases:
                speech_sample = await session.get(SpeechSample, tc.speech_sample_id)
                corpus_entry = await session.get(CorpusEntry, speech_sample.corpus_entry_id) if speech_sample else None

                config = TestCaseConfig(
                    id=str(tc.id),
                    speech_file=speech_sample.file_path if speech_sample else "",
                    original_text=corpus_entry.text if corpus_entry else "",
                    expected_intent=corpus_entry.expected_intent or "" if corpus_entry else "",
                    expected_action=corpus_entry.expected_action if corpus_entry else None,
                    snr_db=tc.snr_db if tc.snr_db is not None else 10.0,
                    noise_type=tc.noise_type or "pink_lpf",
                    delay_ms=tc.delay_ms if tc.delay_ms is not None else 0.0,
                    gain_db=tc.gain_db if tc.gain_db is not None else -100.0,
                    eq_config=tc.eq_config_json,
                    pipeline=tc.pipeline,
                    llm_backend=tc.llm_backend,
                )
                test_case_configs.append(config)

            # 9. Create callbacks
            async def on_result_callback(record: TestResultRecord):
                async with async_session() as result_session:
                    pr = record.pipeline_result
                    er = record.evaluation_result

                    test_result = TestResult(
                        test_run_id=run_uuid,
                        test_case_id=uuid.UUID(record.test_case_id),
                        llm_response_text=pr.llm_response.text if pr.llm_response else None,
                        llm_latency_ms=pr.llm_response.latency_ms if pr.llm_response else None,
                        asr_transcript=pr.transcription.text if pr.transcription else None,
                        evaluation_score=er.score if er else None,
                        evaluation_passed=er.passed if er else None,
                        evaluation_details_json=er.details if er else None,
                        evaluator_type=er.evaluator if er else None,
                    )
                    result_session.add(test_result)

                    # Update TestRun counters
                    tr = await result_session.get(TestRun, run_uuid)
                    if tr:
                        tr.completed_cases += 1
                        if er and not er.passed:
                            tr.failed_cases += 1
                        tr.progress_pct = (tr.completed_cases / tr.total_cases * 100.0) if tr.total_cases > 0 else 0.0

                    await result_session.commit()

                # Broadcast via WebSocket
                await broadcast_progress(run_id, {
                    "type": "result",
                    "test_case_id": record.test_case_id,
                    "score": er.score if er else None,
                    "passed": er.passed if er else None,
                })

            def on_progress_callback(completed: int, total: int):
                pct = (completed / total * 100.0) if total > 0 else 0.0
                asyncio.ensure_future(broadcast_progress(run_id, {
                    "type": "progress",
                    "completed": completed,
                    "total": total,
                    "pct": round(pct, 1),
                }))

            # 10. Create and run scheduler
            # Use lower concurrency when running local inference
            has_local_backend = any(
                k.startswith("ollama") for k in backends
            )
            max_workers = min(
                settings.max_concurrent_workers,
                2 if has_local_backend else settings.max_concurrent_workers,
            )

            scheduler = TestScheduler(
                backends=backends,
                asr_backend=asr_backend,
                evaluators=evaluators,
                max_workers=max_workers,
                on_result=on_result_callback,
                on_progress=on_progress_callback,
            )

            await scheduler.run(test_case_configs, completed_ids=completed_hashes)

            # 11. Update TestRun status to completed
            await session.refresh(test_run)
            test_run.status = "completed"
            test_run.completed_at = datetime.utcnow()
            test_run.progress_pct = 100.0
            await session.commit()

            await broadcast_progress(run_id, {
                "type": "completed",
                "summary": {
                    "total": test_run.total_cases,
                    "completed": test_run.completed_cases,
                    "failed": test_run.failed_cases,
                },
            })

        except Exception as e:
            logger.exception(f"Test run failed: {run_id}")
            try:
                await session.refresh(test_run)
                test_run.status = "failed"
                test_run.completed_at = datetime.utcnow()
                await session.commit()
            except Exception:
                logger.exception("Failed to update test run status to failed")

            await broadcast_progress(run_id, {
                "type": "error",
                "error": str(e),
            })

    logger.info(f"Test run completed: {run_id}")


async def synthesize_speech_batch(ctx: dict, task_id: str):
    """Background task: batch TTS generation.

    Generates speech samples for all specified corpus entry x voice combinations.
    """
    logger.info(f"Starting speech synthesis batch: {task_id}")

    async with async_session() as session:
        try:
            # 1. Query all pending SpeechSample records
            result = await session.execute(
                select(SpeechSample).where(SpeechSample.status == "pending")
            )
            samples = list(result.scalars().all())

            if not samples:
                logger.info("No pending speech samples found")
                return

            # 2. Load related Voice and CorpusEntry for each sample
            voices_cache: dict[uuid.UUID, Voice] = {}
            entries_cache: dict[uuid.UUID, CorpusEntry] = {}

            for sample in samples:
                if sample.voice_id not in voices_cache:
                    voice = await session.get(Voice, sample.voice_id)
                    if voice:
                        voices_cache[sample.voice_id] = voice
                if sample.corpus_entry_id not in entries_cache:
                    entry = await session.get(CorpusEntry, sample.corpus_entry_id)
                    if entry:
                        entries_cache[sample.corpus_entry_id] = entry

            # 3. Initialize TTS providers based on unique providers found
            unique_providers = {v.provider for v in voices_cache.values()}
            tts_providers: dict[str, object] = {}

            for provider in unique_providers:
                if provider == "openai":
                    tts_providers["openai"] = OpenAITTSProvider(api_key=settings.openai_api_key)
                elif provider == "google":
                    tts_providers["google"] = GoogleTTSProvider()
                elif provider == "elevenlabs":
                    tts_providers["elevenlabs"] = ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key)
                else:
                    logger.warning(f"Unknown TTS provider: {provider}")

            # 4. Process each sample
            storage_path = Path(settings.audio_storage_path)
            storage_path.mkdir(parents=True, exist_ok=True)

            batch_count = 0
            for sample in samples:
                voice = voices_cache.get(sample.voice_id)
                entry = entries_cache.get(sample.corpus_entry_id)

                if not voice or not entry:
                    logger.error(f"Missing voice or corpus entry for sample {sample.id}")
                    sample.status = "failed"
                    batch_count += 1
                    if batch_count % 10 == 0:
                        await session.commit()
                    continue

                provider = tts_providers.get(voice.provider)
                if not provider:
                    logger.error(f"No TTS provider for {voice.provider}")
                    sample.status = "failed"
                    batch_count += 1
                    if batch_count % 10 == 0:
                        await session.commit()
                    continue

                try:
                    # Update status to generating
                    sample.status = "generating"
                    await session.commit()

                    # Synthesize speech
                    audio_buffer = await provider.synthesize(entry.text, voice.voice_id)

                    # Save audio file
                    output_path = storage_path / f"{sample.id}.wav"
                    save_audio(audio_buffer, output_path)

                    # Update sample record
                    sample.file_path = str(output_path)
                    sample.duration_s = audio_buffer.duration_s
                    sample.sample_rate = audio_buffer.sample_rate
                    sample.status = "ready"

                except Exception as e:
                    logger.error(f"Failed to synthesize sample {sample.id}: {e}")
                    sample.status = "failed"

                batch_count += 1
                if batch_count % 10 == 0:
                    await session.commit()

            # Final commit for remaining samples
            await session.commit()

        except Exception:
            logger.exception(f"Speech synthesis batch failed: {task_id}")

    logger.info(f"Speech synthesis batch completed: {task_id}")


async def startup(ctx: dict):
    """Worker startup hook."""
    logger.info("arq worker starting up")


async def shutdown(ctx: dict):
    """Worker shutdown hook."""
    logger.info("arq worker shutting down")


class WorkerSettings:
    """arq worker configuration."""

    functions = [run_test_suite, synthesize_speech_batch]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 3600  # 1 hour max per job
