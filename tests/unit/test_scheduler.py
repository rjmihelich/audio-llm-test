"""Tests for the test execution scheduler."""

import asyncio
import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer
from backend.app.audio.io import save_audio
from backend.app.llm.base import LLMResponse, RateLimitConfig, Transcription
from backend.app.evaluation.command_match import CommandMatchEvaluator
from backend.app.execution.scheduler import TestScheduler as Scheduler, TestCaseConfig, TestResultRecord

import tempfile
import os


class MockSchedulerLLM:
    """Mock LLM for scheduler tests."""

    def __init__(self, response: str = "navigate to airport"):
        self._response = response
        self.calls = 0

    @property
    def name(self) -> str:
        return "mock"

    @property
    def supports_audio_input(self) -> bool:
        return True

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(requests_per_minute=6000, max_concurrent=50)

    async def query_with_audio(self, audio, system_prompt, context=None) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self._response, latency_ms=10.0, model="mock")

    async def query_with_text(self, text, system_prompt, context=None) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self._response, latency_ms=10.0, model="mock")


class MockSchedulerASR:
    @property
    def name(self) -> str:
        return "mock_asr"

    async def transcribe(self, audio) -> Transcription:
        return Transcription(text="navigate to the airport", language="en", confidence=0.9)


def _create_speech_file() -> str:
    """Create a temporary WAV file for testing."""
    t = np.arange(16000) / 16000
    samples = 0.3 * np.sin(2 * np.pi * 300 * t)
    buf = AudioBuffer(samples=samples, sample_rate=16000)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    save_audio(buf, path)
    return path


class TestTestCaseConfig:
    def test_deterministic_hash(self):
        c1 = TestCaseConfig(
            id="1", speech_file="a.wav", original_text="hello",
            expected_intent="test", snr_db=5.0, pipeline="direct_audio",
            llm_backend="mock",
        )
        c2 = TestCaseConfig(
            id="2", speech_file="a.wav", original_text="world",
            expected_intent="test", snr_db=5.0, pipeline="direct_audio",
            llm_backend="mock",
        )
        # Same audio params → same hash (id and text don't affect hash)
        assert c1.deterministic_hash == c2.deterministic_hash

    def test_different_params_different_hash(self):
        c1 = TestCaseConfig(
            id="1", speech_file="a.wav", original_text="test",
            expected_intent="test", snr_db=5.0, pipeline="direct_audio",
            llm_backend="mock",
        )
        c2 = TestCaseConfig(
            id="2", speech_file="a.wav", original_text="test",
            expected_intent="test", snr_db=10.0, pipeline="direct_audio",
            llm_backend="mock",
        )
        assert c1.deterministic_hash != c2.deterministic_hash


class TestSchedulerExecution:
    def test_run_direct_audio(self):
        speech_file = _create_speech_file()
        try:
            llm = MockSchedulerLLM()
            evaluator = CommandMatchEvaluator()
            scheduler = Scheduler(
                backends={"mock": llm},
                evaluators={"command_match": evaluator},
                max_workers=5,
            )
            cases = [
                TestCaseConfig(
                    id=f"tc_{i}", speech_file=speech_file,
                    original_text="Navigate to the airport",
                    expected_intent="navigation",
                    expected_action="navigate to airport",
                    snr_db=10.0, pipeline="direct_audio", llm_backend="mock",
                )
                for i in range(5)
            ]
            results = asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(results) == 5
            assert llm.calls == 5
            for r in results:
                assert r.pipeline_result.error is None
                assert r.evaluation_result is not None
                assert r.evaluation_result.passed is True
        finally:
            os.unlink(speech_file)

    def test_run_asr_text(self):
        speech_file = _create_speech_file()
        try:
            llm = MockSchedulerLLM(response="navigate to airport")
            asr = MockSchedulerASR()
            evaluator = CommandMatchEvaluator()
            scheduler = Scheduler(
                backends={"mock": llm},
                asr_backend=asr,
                evaluators={"command_match": evaluator},
            )
            cases = [
                TestCaseConfig(
                    id="tc_0", speech_file=speech_file,
                    original_text="Navigate to the airport",
                    expected_intent="navigation",
                    expected_action="navigate to airport",
                    snr_db=10.0, pipeline="asr_text", llm_backend="mock",
                )
            ]
            results = asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(results) == 1
            assert results[0].pipeline_result.transcription is not None
        finally:
            os.unlink(speech_file)

    def test_resume_skips_completed(self):
        speech_file = _create_speech_file()
        try:
            llm = MockSchedulerLLM()
            scheduler = Scheduler(backends={"mock": llm})
            cases = [
                TestCaseConfig(
                    id=f"tc_{i}", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    snr_db=float(i), pipeline="direct_audio", llm_backend="mock",
                )
                for i in range(5)
            ]
            # Pre-complete first 3 via their hashes
            completed = {cases[i].deterministic_hash for i in range(3)}
            results = asyncio.get_event_loop().run_until_complete(
                scheduler.run(cases, completed_ids=completed)
            )
            assert len(results) == 2  # Only 2 new ones
            assert llm.calls == 2
        finally:
            os.unlink(speech_file)

    def test_callbacks(self):
        speech_file = _create_speech_file()
        try:
            llm = MockSchedulerLLM()
            on_result_calls = []
            progress_calls = []

            async def on_result(record):
                on_result_calls.append(record)

            def on_progress(completed, total):
                progress_calls.append((completed, total))

            scheduler = Scheduler(
                backends={"mock": llm},
                on_result=on_result,
                on_progress=on_progress,
            )
            cases = [
                TestCaseConfig(
                    id=f"tc_{i}", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    snr_db=10.0, pipeline="direct_audio", llm_backend="mock",
                )
                for i in range(3)
            ]
            asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(on_result_calls) == 3
            assert len(progress_calls) == 3
            assert progress_calls[-1] == (3, 3)
        finally:
            os.unlink(speech_file)

    def test_unknown_backend_skipped(self):
        speech_file = _create_speech_file()
        try:
            scheduler = Scheduler(backends={})
            cases = [
                TestCaseConfig(
                    id="tc_0", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    pipeline="direct_audio", llm_backend="nonexistent",
                )
            ]
            results = asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(results) == 0
        finally:
            os.unlink(speech_file)
