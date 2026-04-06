"""Expanded scheduler and rate limiter tests: stress, timeouts, edge cases."""

from __future__ import annotations

import asyncio
import time
import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer
from backend.app.audio.io import save_audio
from backend.app.llm.base import LLMResponse, RateLimitConfig, Transcription
from backend.app.evaluation.command_match import CommandMatchEvaluator
from backend.app.execution.scheduler import TestScheduler as Scheduler, TestCaseConfig
from backend.app.execution.rate_limiter import TokenBucketRateLimiter
from backend.app.pipeline.base import PipelineResult

import tempfile
import os


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FastMockLLM:
    def __init__(self, response="ok", latency=0.0):
        self._response = response
        self._latency = latency
        self.calls = 0

    @property
    def name(self): return "fast_mock"
    @property
    def supports_audio_input(self): return True
    @property
    def rate_limit(self): return RateLimitConfig(requests_per_minute=60000, max_concurrent=100)

    async def query_with_audio(self, audio, system_prompt, context=None):
        self.calls += 1
        if self._latency > 0:
            await asyncio.sleep(self._latency)
        return LLMResponse(text=self._response, latency_ms=1.0, model="mock")

    async def query_with_text(self, text, system_prompt, context=None):
        self.calls += 1
        return LLMResponse(text=self._response, latency_ms=1.0, model="mock")


class SlowMockLLM:
    """LLM that takes too long, for timeout testing."""
    @property
    def name(self): return "slow_mock"
    @property
    def supports_audio_input(self): return True
    @property
    def rate_limit(self): return RateLimitConfig(requests_per_minute=60000, max_concurrent=100)

    async def query_with_audio(self, audio, system_prompt, context=None):
        await asyncio.sleep(10)  # Simulate a hung request
        return LLMResponse(text="too late", latency_ms=10000.0, model="mock")


def _create_speech_file() -> str:
    t = np.arange(16000) / 16000
    samples = 0.3 * np.sin(2 * np.pi * 300 * t)
    buf = AudioBuffer(samples=samples, sample_rate=16000)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    save_audio(buf, path)
    return path


# ---------------------------------------------------------------------------
# Rate limiter expanded tests
# ---------------------------------------------------------------------------

class TestRateLimiterExpanded:
    def test_concurrent_tasks_respect_limit(self):
        """Multiple concurrent tasks should not exceed max_concurrent."""
        limiter = TokenBucketRateLimiter(requests_per_minute=60000, max_concurrent=5)
        max_seen = 0
        current = 0

        async def task():
            nonlocal max_seen, current
            async with limiter:
                current += 1
                if current > max_seen:
                    max_seen = current
                await asyncio.sleep(0.02)
                current -= 1

        async def run():
            await asyncio.gather(*[task() for _ in range(20)])

        asyncio.get_event_loop().run_until_complete(run())
        assert max_seen <= 5

    def test_rpm_pacing(self):
        """Low RPM should space requests appropriately."""
        limiter = TokenBucketRateLimiter(requests_per_minute=60, max_concurrent=10)

        async def run():
            t0 = time.monotonic()
            for _ in range(3):
                async with limiter:
                    pass
            return time.monotonic() - t0

        elapsed = asyncio.get_event_loop().run_until_complete(run())
        # 60 RPM = 1 req/sec, 3 requests should take ~2s
        assert elapsed >= 1.5

    def test_release_on_exception_preserves_capacity(self):
        """After exception, full capacity should be available."""
        limiter = TokenBucketRateLimiter(requests_per_minute=60000, max_concurrent=2)

        async def run():
            # Use up both slots then raise
            for _ in range(2):
                try:
                    async with limiter:
                        raise RuntimeError("boom")
                except RuntimeError:
                    pass

            # Both should be available again
            acquired = 0
            async def try_acquire():
                nonlocal acquired
                async with limiter:
                    acquired += 1
                    await asyncio.sleep(0.01)

            await asyncio.gather(try_acquire(), try_acquire())
            return acquired

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result == 2


# ---------------------------------------------------------------------------
# Scheduler stress and edge cases
# ---------------------------------------------------------------------------

class TestSchedulerExpanded:
    def test_large_batch(self):
        """50 test cases should all complete."""
        speech_file = _create_speech_file()
        try:
            llm = FastMockLLM(response="navigate to airport")
            evaluator = CommandMatchEvaluator()
            scheduler = Scheduler(
                backends={"fast_mock": llm},
                evaluators={"command_match": evaluator},
                max_workers=10,
            )
            cases = [
                TestCaseConfig(
                    id=f"tc_{i}", speech_file=speech_file,
                    original_text="Navigate to the airport",
                    expected_intent="navigation",
                    expected_action="navigate to airport",
                    snr_db=float(10 + (i % 5)),
                    pipeline="direct_audio", llm_backend="fast_mock",
                )
                for i in range(50)
            ]
            results = asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(results) == 50
            assert llm.calls == 50
            # All should pass (response matches expected)
            pass_count = sum(1 for r in results if r.evaluation_result and r.evaluation_result.passed)
            assert pass_count == 50
        finally:
            os.unlink(speech_file)

    def test_timeout_produces_error_result(self):
        """Pipeline timeout should produce error, not crash."""
        speech_file = _create_speech_file()
        try:
            llm = SlowMockLLM()
            scheduler = Scheduler(
                backends={"slow_mock": llm},
                timeout_s=0.5,  # Very short timeout
            )
            cases = [
                TestCaseConfig(
                    id="tc_0", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    pipeline="direct_audio", llm_backend="slow_mock",
                )
            ]
            results = asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(results) == 1
            assert results[0].pipeline_result.error is not None
            assert "timed out" in results[0].pipeline_result.error
        finally:
            os.unlink(speech_file)

    def test_cancel_stops_execution(self):
        """Cancelling mid-run should stop processing new cases."""
        speech_file = _create_speech_file()
        try:
            llm = FastMockLLM(latency=0.1)

            scheduler = Scheduler(
                backends={"fast_mock": llm},
                max_workers=1,
            )
            cases = [
                TestCaseConfig(
                    id=f"tc_{i}", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    pipeline="direct_audio", llm_backend="fast_mock",
                )
                for i in range(20)
            ]

            async def run_and_cancel():
                task = asyncio.ensure_future(scheduler.run(cases))
                await asyncio.sleep(0.3)  # Let some start
                scheduler.cancel()
                return await task

            results = asyncio.get_event_loop().run_until_complete(run_and_cancel())
            # Should have fewer than 20 results due to cancellation
            assert len(results) < 20
        finally:
            os.unlink(speech_file)

    def test_mixed_noise_types(self):
        """Different noise types in same batch should all work."""
        speech_file = _create_speech_file()
        try:
            llm = FastMockLLM(response="test response")
            scheduler = Scheduler(backends={"fast_mock": llm})
            cases = [
                TestCaseConfig(
                    id=f"tc_{nt}", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    noise_type=nt,
                    pipeline="direct_audio", llm_backend="fast_mock",
                )
                for nt in ["pink_lpf", "white", "babble"]
            ]
            results = asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(results) == 3
            for r in results:
                assert r.pipeline_result.error is None
        finally:
            os.unlink(speech_file)

    def test_echo_configs_in_batch(self):
        """Varying echo configurations in same batch."""
        speech_file = _create_speech_file()
        try:
            llm = FastMockLLM()
            scheduler = Scheduler(backends={"fast_mock": llm})
            cases = [
                TestCaseConfig(
                    id="tc_no_echo", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    gain_db=-100.0,  # No echo
                    pipeline="direct_audio", llm_backend="fast_mock",
                ),
                TestCaseConfig(
                    id="tc_light_echo", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    delay_ms=50.0, gain_db=-20.0,
                    pipeline="direct_audio", llm_backend="fast_mock",
                ),
                TestCaseConfig(
                    id="tc_heavy_echo", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    delay_ms=200.0, gain_db=-6.0,
                    pipeline="direct_audio", llm_backend="fast_mock",
                ),
            ]
            results = asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(results) == 3
            for r in results:
                assert r.pipeline_result.error is None
        finally:
            os.unlink(speech_file)

    def test_deterministic_hash_uniqueness(self):
        """Different parameters should produce different hashes."""
        base = dict(
            speech_file="a.wav", original_text="t", expected_intent="t",
            pipeline="direct_audio", llm_backend="mock",
        )
        configs = [
            TestCaseConfig(id="1", snr_db=5.0, **base),
            TestCaseConfig(id="2", snr_db=10.0, **base),
            TestCaseConfig(id="3", snr_db=5.0, noise_type="babble", **base),
            TestCaseConfig(id="4", snr_db=5.0, delay_ms=50.0, **base),
        ]
        hashes = [c.deterministic_hash for c in configs]
        assert len(set(hashes)) == 4  # All unique

    def test_progress_callback_accuracy(self):
        """Progress callback should report correct counts."""
        speech_file = _create_speech_file()
        try:
            llm = FastMockLLM()
            progress = []

            def on_progress(completed, total):
                progress.append((completed, total))

            scheduler = Scheduler(
                backends={"fast_mock": llm},
                on_progress=on_progress,
            )
            n = 10
            cases = [
                TestCaseConfig(
                    id=f"tc_{i}", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    snr_db=float(i),
                    pipeline="direct_audio", llm_backend="fast_mock",
                )
                for i in range(n)
            ]
            asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(progress) == n
            # Last callback should show all complete
            assert progress[-1] == (n, n)
            # All totals should be n
            for _, total in progress:
                assert total == n
        finally:
            os.unlink(speech_file)
