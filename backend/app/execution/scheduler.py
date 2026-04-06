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
    noise_type: str = "pink_lpf"
    noise_file: str | None = None
    delay_ms: float = 0.0
    gain_db: float = -100.0  # -100 dB = no echo
    eq_config: list[dict] | None = None
    pipeline: str = "direct_audio"  # or "asr_text"
    llm_backend: str = ""
    system_prompt: str = "You are a helpful in-car voice assistant."

    @property
    def deterministic_hash(self) -> str:
        """Hash of all parameters for checkpointing."""
        key = json.dumps({
            "speech_file": self.speech_file,
            "snr_db": self.snr_db,
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
    timestamp: float = field(default_factory=time.time)

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
            logger.error(f"Unknown backend: {case.llm_backend}")
            return None

        rate_limiter = self._rate_limiters[case.llm_backend]

        # Load speech audio
        try:
            speech = load_audio(case.speech_file, target_sample_rate=16000)
        except Exception as e:
            logger.error(f"Failed to load audio {case.speech_file}: {e}")
            return None

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
                    logger.error("ASR backend required for asr_text pipeline")
                    return None
                pipeline = ASRTextPipeline(
                    asr_backend=self._asr,
                    llm_backend=backend,
                    snr_db=case.snr_db,
                    noise_type=case.noise_type,
                    noise_file=case.noise_file,
                    echo_config=echo_config,
                )
            else:
                logger.error(f"Unknown pipeline: {case.pipeline}")
                return None

            try:
                result = await asyncio.wait_for(
                    pipeline.execute(pipeline_input), timeout=self._timeout_s
                )
            except asyncio.TimeoutError:
                result = PipelineResult(
                    pipeline_type=case.pipeline,
                    error=f"Pipeline timed out after {self._timeout_s}s",
                )

        # Evaluate
        eval_result = None
        evaluator_name = "command_match" if case.expected_action else "llm_judge"
        evaluator = self._evaluators.get(evaluator_name)
        if evaluator:
            try:
                eval_result = await evaluator.evaluate(pipeline_input, result)
            except Exception as e:
                logger.error(f"Evaluation failed for {case.id}: {e}")

        record = TestResultRecord(
            test_case_id=case.id,
            test_case_hash=case.deterministic_hash,
            pipeline_result=result,
            evaluation_result=eval_result,
        )

        # Persist to disk checkpoint
        if self._checkpoint:
            try:
                self._checkpoint.append(record.to_dict())
            except Exception as e:
                logger.warning(f"Failed to write checkpoint for {case.id}: {e}")

        # Callbacks
        self._completed += 1
        if self._on_result:
            if asyncio.iscoroutinefunction(self._on_result):
                await self._on_result(record)
            else:
                self._on_result(record)
        if self._on_progress:
            self._on_progress(self._completed, self._total)

        return record

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
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Task failed with exception: {r}")
            elif r is not None:
                records.append(r)

        return records
