"""arq worker settings and task definitions for background test execution."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from arq.connections import RedisSettings, create_pool
from sqlalchemy import select

from ..config import settings
from ..models.base import async_session
from ..models.run import TestRun, TestResult
from ..models.test import TestCase, TestSuite
from ..models.speech import SpeechSample, CorpusEntry, Voice
from ..execution.scheduler import TestScheduler, TestCaseConfig, TestResultRecord
from ..llm.openai_audio import OpenAIAudioBackend
from ..llm.openai_realtime import OpenAIRealtimeBackend
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

# ---------------------------------------------------------------------------
# Redis activity tracking
# ---------------------------------------------------------------------------

_redis_pool = None


async def _get_redis():
    """Get or create Redis connection for activity publishing."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _redis_pool


async def publish_activity(run_id: str, data: dict):
    """Publish current worker activity to Redis for monitoring."""
    try:
        redis = await _get_redis()
        data["run_id"] = run_id
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        await redis.set("worker:activity", json.dumps(data), ex=120)
        await redis.set("worker:heartbeat", datetime.now(timezone.utc).isoformat(), ex=120)
    except Exception:
        pass  # Don't let monitoring failures break execution


async def publish_log(level: str, message: str, **extra):
    """Push a log entry to Redis for the monitoring UI."""
    try:
        redis = await _get_redis()
        entry = {
            "level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        await redis.lpush("worker:log", json.dumps(entry))
        await redis.ltrim("worker:log", 0, 99)  # Keep last 100
    except Exception:
        pass


async def publish_error(run_id: str, error_msg: str, backend: str = "", stage: str = ""):
    """Record an error for monitoring and error-budget tracking."""
    try:
        redis = await _get_redis()
        entry = {
            "run_id": run_id,
            "error": error_msg,
            "backend": backend,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Append to recent errors (capped at 50)
        raw = await redis.get("worker:recent_errors")
        errors = json.loads(raw) if raw else []
        errors.append(entry)
        errors = errors[-50:]
        await redis.set("worker:recent_errors", json.dumps(errors), ex=7200)

        # Update per-backend error budget
        budget_raw = await redis.get("worker:error_budget")
        budget = json.loads(budget_raw) if budget_raw else {}
        if backend:
            bdata = budget.get(backend, {"errors": 0, "total": 0, "consecutive": 0})
            bdata["errors"] = bdata.get("errors", 0) + 1
            bdata["consecutive"] = bdata.get("consecutive", 0) + 1
            budget[backend] = bdata
            await redis.set("worker:error_budget", json.dumps(budget), ex=7200)
    except Exception:
        pass


async def clear_backend_consecutive(backend: str):
    """Reset consecutive error count on success (for self-healing)."""
    try:
        redis = await _get_redis()
        budget_raw = await redis.get("worker:error_budget")
        budget = json.loads(budget_raw) if budget_raw else {}
        if backend in budget:
            budget[backend]["consecutive"] = 0
            budget[backend]["total"] = budget[backend].get("total", 0) + 1
            await redis.set("worker:error_budget", json.dumps(budget), ex=7200)
        else:
            budget[backend] = {"errors": 0, "total": 1, "consecutive": 0}
            await redis.set("worker:error_budget", json.dumps(budget), ex=7200)
    except Exception:
        pass


def _init_backend(backend_key: str):
    """Instantiate an LLM backend from a backend key like 'openai:gpt-4o-audio-preview'."""
    prefix, _, model = backend_key.partition(":")
    if prefix == "openai":
        kwargs = {"api_key": settings.openai_api_key}
        if model:
            kwargs["model"] = model
        return OpenAIAudioBackend(**kwargs)
    elif prefix == "openai-realtime":
        kwargs = {"api_key": settings.openai_api_key}
        if model:
            kwargs["model"] = model
        return OpenAIRealtimeBackend(**kwargs)
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


async def run_test_suite(ctx: dict, run_id: str, sample_size: int | None = None):
    """Background task: execute all test cases in a test run.

    This is the main entry point called by the arq worker.
    It loads the test suite configuration, creates the execution
    scheduler, and runs all test cases with progress reporting.
    If sample_size is set, only a random subset of cases is executed.
    """
    logger.info(f"Starting test run: {run_id} (sample_size={sample_size})")

    async with async_session() as session:
        try:
            # 1. Load TestRun
            await broadcast_progress(run_id, {"type": "info", "message": "Loading test run..."})
            run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
            test_run = await session.get(TestRun, run_uuid)
            if not test_run:
                logger.error(f"TestRun not found: {run_id}")
                return

            # 2. Load TestSuite with test cases
            await broadcast_progress(run_id, {"type": "info", "message": "Loading test suite configuration..."})
            test_suite = await session.get(TestSuite, test_run.test_suite_id)
            if not test_suite:
                logger.error(f"TestSuite not found: {test_run.test_suite_id}")
                return

            # Load test cases for this suite
            await broadcast_progress(run_id, {"type": "info", "message": f"Loading test cases for suite '{test_suite.name}'..."})
            tc_result = await session.execute(
                select(TestCase).where(TestCase.test_suite_id == test_suite.id)
            )
            test_cases = list(tc_result.scalars().all())
            await broadcast_progress(run_id, {"type": "info", "message": f"Loaded {len(test_cases)} test cases"})

            # Random subset if sample_size specified
            if sample_size and sample_size < len(test_cases):
                import random
                test_cases = random.sample(test_cases, sample_size)
                logger.info(f"Quick test: selected {sample_size} random cases from {len(test_cases) + sample_size - sample_size}")
                await broadcast_progress(run_id, {"type": "info", "message": f"Quick test mode: randomly selected {sample_size} cases"})

            # Eagerly load speech_sample and corpus_entry for each test case
            await broadcast_progress(run_id, {"type": "info", "message": f"Loading audio samples for {len(test_cases)} test cases..."})
            for i, tc in enumerate(test_cases):
                if tc.speech_sample_id:
                    sample = await session.get(SpeechSample, tc.speech_sample_id)
                    if sample and sample.corpus_entry_id:
                        await session.get(CorpusEntry, sample.corpus_entry_id)
                # Broadcast progress every 500 cases for large suites
                if (i + 1) % 500 == 0:
                    await broadcast_progress(run_id, {"type": "info", "message": f"Loaded {i + 1}/{len(test_cases)} audio samples..."})
            await broadcast_progress(run_id, {"type": "info", "message": f"All {len(test_cases)} audio samples loaded"})

            # 3. Query already-completed TestResult test_case_ids for resume
            await broadcast_progress(run_id, {"type": "info", "message": "Checking for previously completed results..."})
            completed_result = await session.execute(
                select(TestResult.test_case_id).where(TestResult.test_run_id == run_uuid)
            )
            completed_tc_ids = {str(row) for row in completed_result.scalars().all()}

            # Also collect deterministic hashes of completed cases for the scheduler
            completed_hashes: set[str] = set()
            for tc in test_cases:
                if str(tc.id) in completed_tc_ids:
                    completed_hashes.add(tc.deterministic_hash)

            if completed_tc_ids:
                await broadcast_progress(run_id, {"type": "info", "message": f"Found {len(completed_tc_ids)} previously completed results (will skip)"})
            else:
                await broadcast_progress(run_id, {"type": "info", "message": "No previous results found — starting fresh"})

            # 4. Update TestRun status to running
            test_run.status = "running"
            test_run.started_at = datetime.utcnow()
            test_run.total_cases = len(test_cases)
            await session.commit()
            await broadcast_progress(run_id, {"type": "info", "message": "Run status set to running"})

            # 5. Initialize LLM backends
            unique_backends = {tc.llm_backend for tc in test_cases}
            await broadcast_progress(run_id, {"type": "info", "message": f"Initializing {len(unique_backends)} LLM backend(s): {', '.join(sorted(unique_backends))}"})
            backends: dict[str, object] = {}
            init_errors: list[str] = []
            for backend_key in unique_backends:
                try:
                    backends[backend_key] = _init_backend(backend_key)
                    logger.info(f"Backend initialized: {backend_key}")
                    await broadcast_progress(run_id, {"type": "info", "message": f"✓ Backend ready: {backend_key}"})
                except Exception as e:
                    error_msg = f"Failed to init backend '{backend_key}': {type(e).__name__}: {e}"
                    logger.error(error_msg, exc_info=True)
                    init_errors.append(error_msg)
                    await broadcast_progress(run_id, {
                        "type": "error",
                        "error": error_msg,
                        "error_stage": "backend_init",
                    })

            if not backends:
                error_msg = f"No backends initialized successfully. Errors: {'; '.join(init_errors)}"
                logger.error(error_msg)
                test_run.status = "failed"
                test_run.completed_at = datetime.utcnow()
                test_run.error_message = error_msg
                test_run.error_details = {"init_errors": init_errors}
                await session.commit()
                await broadcast_progress(run_id, {"type": "error", "error": error_msg})
                return

            # Build a quick lookup: test_case_id -> backend key
            case_backend_map: dict[str, str] = {
                str(tc.id): tc.llm_backend for tc in test_cases
            }

            # 6. Initialize evaluators
            await broadcast_progress(run_id, {"type": "info", "message": "Initializing evaluators..."})
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

            eval_names = list(evaluators.keys())
            await broadcast_progress(run_id, {"type": "info", "message": f"✓ Evaluators ready: {', '.join(eval_names)}"})

            # 7. Initialize ASR backend if any test case uses asr_text pipeline
            asr_backend = None
            asr_needed = any(tc.pipeline == "asr_text" for tc in test_cases)
            if not asr_needed:
                await broadcast_progress(run_id, {"type": "info", "message": "No ASR pipeline cases — skipping STT init"})
            if asr_needed:
                try:
                    if settings.default_stt_backend.startswith("deepgram") and settings.deepgram_api_key:
                        asr_backend = DeepgramSTTBackend(api_key=settings.deepgram_api_key)
                        logger.info("ASR backend: Deepgram Nova-2")
                    elif settings.openai_api_key and not settings.openai_api_key.startswith("sk-..."):
                        asr_backend = WhisperAPIBackend(api_key=settings.openai_api_key)
                        logger.info("ASR backend: Whisper API (OpenAI)")
                    else:
                        logger.info("No valid STT API key found — using local Whisper")
                        asr_backend = WhisperLocalBackend(model_size="base")
                        asr_backend._ensure_model()
                        logger.info("ASR backend: Whisper Local (faster-whisper, base model)")
                    await broadcast_progress(run_id, {
                        "type": "info",
                        "message": f"ASR backend ready: {type(asr_backend).__name__}",
                    })
                except Exception as e:
                    error_msg = f"Failed to initialize ASR backend: {type(e).__name__}: {e}"
                    logger.error(error_msg, exc_info=True)
                    await broadcast_progress(run_id, {
                        "type": "error",
                        "error": error_msg,
                        "error_stage": "asr_init",
                    })

            # 8. Convert TestCase DB objects to TestCaseConfig
            await broadcast_progress(run_id, {"type": "info", "message": f"Preparing {len(test_cases)} test configurations..."})
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
                    speech_level_db=getattr(tc, "speech_level_db", None) or 0.0,
                    noise_type=tc.noise_type or "pink_lpf",
                    delay_ms=tc.delay_ms if tc.delay_ms is not None else 0.0,
                    gain_db=tc.gain_db if tc.gain_db is not None else -100.0,
                    eq_config=tc.eq_config_json,
                    pipeline=tc.pipeline,
                    llm_backend=tc.llm_backend,
                )
                test_case_configs.append(config)

            await broadcast_progress(run_id, {"type": "info", "message": f"✓ {len(test_case_configs)} test configurations ready"})

            # 9. Create callbacks with activity tracking
            _result_times: list[float] = []  # Track timestamps for rate calculation

            async def on_result_callback(record: TestResultRecord):
                async with async_session() as result_session:
                    pr = record.pipeline_result
                    er = record.evaluation_result
                    has_error = record.is_error
                    backend_key = case_backend_map.get(record.test_case_id, "")

                    test_result = TestResult(
                        test_run_id=run_uuid,
                        test_case_id=uuid.UUID(record.test_case_id),
                        llm_response_text=pr.llm_response.text if pr.llm_response else None,
                        llm_latency_ms=pr.llm_response.latency_ms if pr.llm_response else None,
                        asr_transcript=pr.transcription.text if pr.transcription else None,
                        evaluation_score=er.score if er else (0.0 if has_error else None),
                        evaluation_passed=er.passed if er else (False if has_error else None),
                        evaluation_details_json=er.details if er else None,
                        evaluator_type=er.evaluator if er else None,
                        error=pr.error,
                        error_stage=record.error_stage,
                    )
                    result_session.add(test_result)

                    # Update TestRun counters
                    tr = await result_session.get(TestRun, run_uuid)
                    if tr:
                        tr.completed_cases += 1
                        if has_error:
                            tr.failed_cases += 1
                        elif er and not er.passed:
                            tr.failed_cases += 1
                        tr.progress_pct = (tr.completed_cases / tr.total_cases * 100.0) if tr.total_cases > 0 else 0.0

                    await result_session.commit()

                # Track rate
                now = time.monotonic()
                _result_times.append(now)
                # Keep last 60s of timestamps for rate calc
                cutoff = now - 60
                while _result_times and _result_times[0] < cutoff:
                    _result_times.pop(0)
                cases_per_min = len(_result_times)  # count in last 60s = per min

                # Find the test case config for this result
                tc_cfg = None
                for cfg in test_case_configs:
                    if cfg.id == record.test_case_id:
                        tc_cfg = cfg
                        break

                # Publish activity to Redis
                completed_so_far = len(_result_times) + (test_run.completed_cases if test_run else 0)
                await publish_activity(run_id, {
                    "status": "processing",
                    "current_case": {
                        "test_case_id": record.test_case_id,
                        "backend": backend_key,
                        "pipeline": tc_cfg.pipeline if tc_cfg else "",
                        "noise_type": tc_cfg.noise_type if tc_cfg else "",
                        "snr_db": tc_cfg.snr_db if tc_cfg else None,
                        "original_text": (tc_cfg.original_text[:100] if tc_cfg and tc_cfg.original_text else ""),
                        "latency_ms": pr.llm_response.latency_ms if pr.llm_response else None,
                        "passed": er.passed if er else None,
                        "error": pr.error[:200] if pr.error else None,
                    },
                    "cases_per_min": cases_per_min,
                })

                # Track errors per backend for self-healing
                if has_error and backend_key:
                    await publish_error(run_id, pr.error or "Unknown error", backend=backend_key, stage=record.error_stage or "")
                    await publish_log("error", f"Case failed: {pr.error[:150] if pr.error else 'Unknown'}", backend=backend_key)
                elif backend_key:
                    await clear_backend_consecutive(backend_key)

                # Broadcast via WebSocket — include error details
                ws_msg = {
                    "type": "result",
                    "test_case_id": record.test_case_id,
                    "backend": backend_key,
                    "score": er.score if er else None,
                    "passed": er.passed if er else False,
                    "latency_ms": pr.llm_response.latency_ms if pr.llm_response else None,
                    "error": pr.error,
                    "error_stage": record.error_stage,
                }
                await broadcast_progress(run_id, ws_msg)

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

            remaining = len(test_case_configs) - len(completed_hashes)
            await broadcast_progress(run_id, {"type": "info", "message": f"Starting execution: {remaining} cases with {max_workers} workers"})
            await publish_activity(run_id, {
                "status": "processing",
                "cases_per_min": 0,
                "current_case": {"stage": "starting", "total": remaining, "workers": max_workers},
            })
            await publish_log("info", f"Run started: {remaining} cases, {max_workers} workers, backends: {', '.join(sorted(unique_backends))}", run_id=run_id)

            await scheduler.run(test_case_configs, completed_ids=completed_hashes)

            # 11. Update TestRun status to completed
            await session.refresh(test_run)
            test_run.status = "completed"
            test_run.completed_at = datetime.utcnow()
            test_run.progress_pct = 100.0
            await session.commit()
            await publish_activity(run_id, {"status": "idle"})
            await publish_log("info", f"Run completed: {test_run.completed_cases}/{test_run.total_cases} cases, {test_run.failed_cases} failures", run_id=run_id)

            await broadcast_progress(run_id, {
                "type": "completed",
                "summary": {
                    "total": test_run.total_cases,
                    "completed": test_run.completed_cases,
                    "failed": test_run.failed_cases,
                },
            })

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.exception(f"Test run failed: {run_id}")
            try:
                await session.refresh(test_run)
                test_run.status = "failed"
                test_run.completed_at = datetime.utcnow()
                test_run.error_message = f"{type(e).__name__}: {e}"
                test_run.error_details = {
                    "exception_type": type(e).__name__,
                    "message": str(e),
                    "traceback": tb,
                }
                await session.commit()
            except Exception:
                logger.exception("Failed to update test run status to failed")

            await publish_activity(run_id, {"status": "error", "error": str(e)})
            await publish_log("error", f"Run FAILED: {type(e).__name__}: {e}", run_id=run_id)
            await broadcast_progress(run_id, {
                "type": "error",
                "error": f"{type(e).__name__}: {e}",
                "traceback": tb,
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
