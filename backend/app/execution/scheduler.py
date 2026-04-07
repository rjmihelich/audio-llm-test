"""Async test execution scheduler with per-backend rate limiting and checkpointing."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..audio.types import AudioBuffer, FilterSpec
from ..audio.echo import EchoConfig
from ..audio.io import load_audio
from ..llm.base import LLMBackend, ASRBackend, RateLimitConfig
from ..pipeline.base import PipelineInput, PipelineResult
from ..pipeline.direct_audio import DirectAudioPipeline
from ..pipeline.asr_text import ASRTextPipeline
from ..evaluation.base import Evaluator, EvaluationResult
from .rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Disk checkpoint helpers
# ---------------------------------------------------------------------------

class CheckpointStore:
    """Persist completed test-case hashes and result dicts to a JSONL file.

    Each line is a JSON object with at minimum ``{"test_case_hash": "<hex>", ...}``.
    On load the file is scanned to rebuild the set of completed hashes and
    optionally the full result records.
    """

    def __init__(self, path: Path | str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # -- write ---------------------------------------------------------------

    def append(self, record_dict: dict) -> None:
        """Append a single completed record (as returned by ``to_dict()``)."""
        with open(self._path, "a") as f:
            f.write(json.dumps(record_dict, default=str) + "\n")

    # -- read ----------------------------------------------------------------

    def load_completed_hashes(self) -> set[str]:
        """Return the set of ``test_case_hash`` values already on disk."""
        hashes: set[str] = set()
        if not self._path.exists():
            return hashes
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    h = obj.get("test_case_hash")
                    if h:
                        hashes.add(h)
                except json.JSONDecodeError:
                    continue
        return hashes

    def load_records(self) -> list[dict]:
        """Return every record stored on disk."""
        records: list[dict] = []
        if not self._path.exists():
            return records
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    @property
    def path(self) -> Path:
        return self._path


@dataclass
class TestCaseConfig:
    """Configuration for a single test case."""

    id: str
    speech_file: str
    original_text: str
    expected_intent: str
    expected_action: str | None = None
    snr_db: float = 10.0
    speech_level_db: float = 0.0  # Digital gain on speech before mixing. 0=original.
    noise_type: str = "pink_lpf"
    noise_file: str | None = None
    delay_ms: float = 0.0
    gain_db: float = -100.0  # -100 dB = no echo
    eq_config: list[dict] | None = None
    pipeline: str = "direct_audio"  # or "asr_text"
    llm_backend: str = ""
    system_prompt: str = (
        "You are an in-car voice assistant. Respond ONLY with a short action command. "
        "Examples: navigate, distance_query, poi_search, route_query, play_music, set_temperature, call_contact. "
        "Do NOT explain, ask questions, or give conversational responses. Just output the action word."
    )

    @property
    def deterministic_hash(self) -> str:
        """Hash of all parameters for checkpointing."""
        key = json.dumps({
            "speech_file": self.speech_file,
            "snr_db": self.snr_db,
            "speech_level_db": self.speech_level_db,
            "noise_type": self.noise_type,
            "delay_ms": self.delay_ms,
            "gain_db": self.gain_db,
            "eq_config": self.eq_config,
            "pipeline": self.pipeline,
            "llm_backend": self.llm_backend,
        }, sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass
class TestResultRecord:
    """Complete result record for a single test case."""

    test_case_id: str
    test_case_hash: str
    pipeline_result: PipelineResult
    evaluation_result: EvaluationResult | None = None
    error_stage: str | None = None
    timestamp: float = field(default_factory=time.time)

    @property
    def is_error(self) -> bool:
        return self.pipeline_result.error is not None

    def to_dict(self) -> dict:
        return {
            "test_case_id": self.test_case_id,
            "test_case_hash": self.test_case_hash,
            "pipeline_type": self.pipeline_result.pipeline_type,
            "llm_response_text": self.pipeline_result.llm_response.text if self.pipeline_result.llm_response else None,
            "llm_latency_ms": self.pipeline_result.llm_response.latency_ms if self.pipeline_result.llm_response else None,
            "total_latency_ms": self.pipeline_result.total_latency_ms,
            "asr_transcript": self.pipeline_result.transcription.text if self.pipeline_result.transcription else None,
            "error": self.pipeline_result.error,
            "error_stage": self.error_stage,
            "eval_score": self.evaluation_result.score if self.evaluation_result else None,
            "eval_passed": self.evaluation_result.passed if self.evaluation_result else None,
            "eval_details": self.evaluation_result.details if self.evaluation_result else None,
            "timestamp": self.timestamp,
        }


class TestScheduler:
    """Orchestrates parallel test execution with per-backend rate limiting."""

    def __init__(
        self,
        backends: dict[str, LLMBackend],
        asr_backend: ASRBackend | None = None,
        evaluators: dict[str, Evaluator] | None = None,
        max_workers: int = 50,
        timeout_s: float = 120.0,
        on_result: Callable[[TestResultRecord], Any] | None = None,
        on_progress: Callable[[int, int], Any] | None = None,
        checkpoint_path: Path | str | None = None,
    ):
        self._backends = backends
        self._asr = asr_backend
        self._evaluators = evaluators or {}
        self._max_workers = max_workers
        self._timeout_s = timeout_s
        self._on_result = on_result
        self._on_progress = on_progress
        self._checkpoint: CheckpointStore | None = (
            CheckpointStore(checkpoint_path) if checkpoint_path else None
        )

        # Create per-backend rate limiters
        self._rate_limiters: dict[str, TokenBucketRateLimiter] = {}
        for name, backend in backends.items():
            rl = backend.rate_limit
            self._rate_limiters[name] = TokenBucketRateLimiter(
                requests_per_minute=rl.requests_per_minute,
                max_concurrent=rl.max_concurrent,
            )

        self._completed = 0
        self._total = 0
        self._cancelled = False

    def cancel(self):
        """Cancel the test run."""
        self._cancelled = True

    def _make_error_record(
        self, case: TestCaseConfig, error_msg: str, error_stage: str
    ) -> TestResultRecord:
        """Create an error result record for a failed test case."""
        logger.error(f"[{error_stage}] Case {case.id[:8]}: {error_msg}")
        return TestResultRecord(
            test_case_id=case.id,
            test_case_hash=case.deterministic_hash,
            pipeline_result=PipelineResult(
                pipeline_type=case.pipeline,
                error=error_msg,
            ),
            error_stage=error_stage,
        )

    async def _load_graph_pipeline(self, pipeline_id: str) -> dict:
        """Load a graph pipeline's JSON from the database."""
        from backend.app.models.base import async_session
        from sqlalchemy import select, text

        async with async_session() as session:
            row = await session.execute(
                text("SELECT graph_json FROM pipelines WHERE id = :pid"),
                {"pid": pipeline_id},
            )
            result = row.fetchone()
            if not result:
                raise ValueError(f"Pipeline {pipeline_id} not found")
            return result[0]

    async def _execute_single(
        self, case: TestCaseConfig, completed_ids: set[str]
    ) -> TestResultRecord | None:
        """Execute a single test case with rate limiting."""
        if self._cancelled:
            return None
        if case.deterministic_hash in completed_ids:
            return None

        backend = self._backends.get(case.llm_backend)
        if not backend:
            record = self._make_error_record(
                case,
                f"Backend not available: {case.llm_backend}. Check that the backend initialized successfully.",
                "backend_init",
            )
            await self._emit_result(record)
            return record

        rate_limiter = self._rate_limiters[case.llm_backend]

        # Load speech audio
        try:
            speech = load_audio(case.speech_file, target_sample_rate=16000)
        except Exception as e:
            record = self._make_error_record(
                case,
                f"Failed to load audio '{case.speech_file}': {type(e).__name__}: {e}",
                "audio_load",
            )
            await self._emit_result(record)
            return record

        # Build echo config
        echo_config = None
        if case.gain_db > -100:
            eq_specs = []
            if case.eq_config:
                for eq in case.eq_config:
                    eq_specs.append(FilterSpec(**eq))
            echo_config = EchoConfig(
                delay_ms=case.delay_ms,
                gain_db=case.gain_db,
                eq_chain=eq_specs,
            )

        # Apply speech level gain (digital gain before mixing)
        if case.speech_level_db != 0.0:
            import numpy as np
            gain_linear = 10 ** (case.speech_level_db / 20.0)
            gained_samples = speech.samples * gain_linear
            # Hard-clip at ±1.0 to simulate ADC overload
            gained_samples = np.clip(gained_samples, -1.0, 1.0)
            speech = AudioBuffer(samples=gained_samples, sample_rate=speech.sample_rate)

        # Build pipeline input
        pipeline_input = PipelineInput(
            clean_speech=speech,
            original_text=case.original_text,
            expected_intent=case.expected_intent,
            expected_action=case.expected_action,
            system_prompt=case.system_prompt,
        )

        # Execute with rate limiting
        async with rate_limiter:
            if case.pipeline == "direct_audio":
                pipeline = DirectAudioPipeline(
                    llm_backend=backend,
                    snr_db=case.snr_db,
                    noise_type=case.noise_type,
                    noise_file=case.noise_file,
                    echo_config=echo_config,
                )
            elif case.pipeline == "asr_text":
                if not self._asr:
                    record = self._make_error_record(
                        case,
                        "ASR backend required for asr_text pipeline but none is configured. Check STT settings.",
                        "backend_init",
                    )
                    await self._emit_result(record)
                    return record
                pipeline = ASRTextPipeline(
                    asr_backend=self._asr,
                    llm_backend=backend,
                    snr_db=case.snr_db,
                    noise_type=case.noise_type,
                    noise_file=case.noise_file,
                    echo_config=echo_config,
                )
            elif str(case.pipeline).startswith("custom:"):
                # Custom graph pipeline from pipeline-studio
                pipeline_id = str(case.pipeline).split(":", 1)[1]
                try:
                    from pipeline_studio.backend.engine.graph_executor import GraphPipeline
                    graph_json = await self._load_graph_pipeline(pipeline_id)
                    pipeline = GraphPipeline(
                        graph_json=graph_json,
                        backends=self._backends,
                        asr_backend=self._asr,
                        snr_db=case.snr_db,
                        noise_type=case.noise_type,
                        echo_config=echo_config,
                    )
                except Exception as e:
                    record = self._make_error_record(
                        case,
                        f"Failed to load graph pipeline '{pipeline_id}': {e}",
                        "pipeline_init",
                    )
                    await self._emit_result(record)
                    return record
            else:
                record = self._make_error_record(
                    case,
                    f"Unknown pipeline type: '{case.pipeline}'. Expected 'direct_audio', 'asr_text', or 'custom:<id>'.",
                    "pipeline_init",
                )
                await self._emit_result(record)
                return record

            try:
                result = await asyncio.wait_for(
                    pipeline.execute(pipeline_input), timeout=self._timeout_s
                )
            except asyncio.TimeoutError:
                result = PipelineResult(
                    pipeline_type=case.pipeline,
                    error=f"Pipeline timed out after {self._timeout_s}s",
                )
            except Exception as e:
                result = PipelineResult(
                    pipeline_type=case.pipeline,
                    error=f"Pipeline execution error: {type(e).__name__}: {e}",
                )
                logger.error(f"[pipeline] Case {case.id[:8]}: {result.error}", exc_info=True)

        # Evaluate
        eval_result = None
        error_stage = None
        if result.error:
            error_stage = "pipeline" if not isinstance(result.error, str) or "timed out" not in result.error else "timeout"
        else:
            evaluator_name = "command_match" if case.expected_action else "llm_judge"
            evaluator = self._evaluators.get(evaluator_name)
            if evaluator:
                try:
                    eval_result = await evaluator.evaluate(pipeline_input, result)
                except Exception as e:
                    logger.error(f"[evaluation] Case {case.id[:8]}: {type(e).__name__}: {e}", exc_info=True)
                    error_stage = "evaluation"
                    # Still create the record with pipeline data, just mark eval as failed
                    result.error = f"Evaluation error ({evaluator_name}): {type(e).__name__}: {e}"

        record = TestResultRecord(
            test_case_id=case.id,
            test_case_hash=case.deterministic_hash,
            pipeline_result=result,
            evaluation_result=eval_result,
            error_stage=error_stage,
        )

        # Persist to disk checkpoint
        if self._checkpoint:
            try:
                self._checkpoint.append(record.to_dict())
            except Exception as e:
                logger.warning(f"Failed to write checkpoint for {case.id}: {e}")

        # Callbacks
        await self._emit_result(record)

        return record

    async def _emit_result(self, record: TestResultRecord):
        """Fire callbacks for a completed (or errored) test case."""
        self._completed += 1
        if self._on_result:
            if asyncio.iscoroutinefunction(self._on_result):
                await self._on_result(record)
            else:
                self._on_result(record)
        if self._on_progress:
            self._on_progress(self._completed, self._total)

    async def run(
        self,
        test_cases: list[TestCaseConfig],
        completed_ids: set[str] | None = None,
    ) -> list[TestResultRecord]:
        """Run all test cases with parallel execution and rate limiting.

        Args:
            test_cases: List of test cases to execute.
            completed_ids: Set of already-completed deterministic hashes (for resume).
        """
        completed_ids = set(completed_ids) if completed_ids else set()

        # Merge with on-disk checkpoint if available
        if self._checkpoint:
            disk_hashes = self._checkpoint.load_completed_hashes()
            completed_ids |= disk_hashes
            if disk_hashes:
                logger.info(f"Loaded {len(disk_hashes)} completed hashes from checkpoint")

        self._total = len(test_cases)
        self._completed = 0
        self._cancelled = False

        # Filter out already completed
        pending = [tc for tc in test_cases if tc.deterministic_hash not in completed_ids]
        logger.info(f"Running {len(pending)} test cases ({len(test_cases) - len(pending)} already completed)")

        # Execute with bounded concurrency
        semaphore = asyncio.Semaphore(self._max_workers)

        async def bounded_execute(case):
            async with semaphore:
                return await self._execute_single(case, completed_ids)

        tasks = [bounded_execute(case) for case in pending]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        records = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                # Task threw an unhandled exception — create error record
                logger.error(f"Task failed with exception: {r}", exc_info=r)
                case = pending[i]
                error_record = self._make_error_record(
                    case,
                    f"Unhandled exception: {type(r).__name__}: {r}",
                    "pipeline",
                )
                await self._emit_result(error_record)
                records.append(error_record)
            elif r is not None:
                records.append(r)

        return records
