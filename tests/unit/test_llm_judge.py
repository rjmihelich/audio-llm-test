"""Tests for LLM-as-judge evaluator using a mock LLM backend."""

import asyncio
import json
import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer
from backend.app.llm.base import LLMResponse, RateLimitConfig
from backend.app.pipeline.base import PipelineInput, PipelineResult
from backend.app.evaluation.llm_judge import LLMJudgeEvaluator


class MockJudgeBackend:
    """Mock LLM backend that returns predefined judge scores."""

    def __init__(self, scores: list[int]):
        self._scores = scores
        self._call_count = 0

    @property
    def name(self) -> str:
        return "mock_judge"

    @property
    def supports_audio_input(self) -> bool:
        return False

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig()

    async def query_with_audio(self, audio, system_prompt, context=None):
        raise NotImplementedError

    async def query_with_text(self, text: str, system_prompt: str, context=None) -> LLMResponse:
        idx = self._call_count % len(self._scores)
        score = self._scores[idx]
        self._call_count += 1
        return LLMResponse(
            text=json.dumps({"score": score, "reasoning": f"Test score {score}"}),
            model="mock",
        )


class MockBadJudge:
    """Mock that returns unparseable JSON."""

    @property
    def name(self) -> str:
        return "bad_judge"

    @property
    def supports_audio_input(self) -> bool:
        return False

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig()

    async def query_with_audio(self, audio, system_prompt, context=None):
        raise NotImplementedError

    async def query_with_text(self, text: str, system_prompt: str, context=None) -> LLMResponse:
        return LLMResponse(text="I think this deserves a 4 out of 5", model="mock")


class MockFailingJudge:
    """Mock that always raises exceptions."""

    @property
    def name(self) -> str:
        return "failing_judge"

    @property
    def supports_audio_input(self) -> bool:
        return False

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig()

    async def query_with_audio(self, audio, system_prompt, context=None):
        raise NotImplementedError

    async def query_with_text(self, text: str, system_prompt: str, context=None) -> LLMResponse:
        raise RuntimeError("Connection timeout")


def _make_input() -> PipelineInput:
    dummy = AudioBuffer(samples=np.zeros(100, dtype=np.float64), sample_rate=16000)
    return PipelineInput(
        clean_speech=dummy,
        original_text="Navigate to the airport",
        expected_intent="navigation",
    )


def _make_result(text: str = "Navigating to airport") -> PipelineResult:
    return PipelineResult(
        pipeline_type="test",
        llm_response=LLMResponse(text=text),
    )


class TestLLMJudgeEvaluator:
    def test_perfect_scores(self):
        judge = MockJudgeBackend(scores=[5, 5, 5])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=3)
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(_make_input(), _make_result())
        )
        assert result.score == 1.0  # (5-1)/4 = 1.0
        assert result.passed is True
        assert result.details["median_score"] == 5

    def test_low_scores(self):
        judge = MockJudgeBackend(scores=[1, 1, 2])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=3)
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(_make_input(), _make_result())
        )
        assert result.score == 0.0  # median=1, (1-1)/4 = 0.0
        assert result.passed is False

    def test_mixed_scores_uses_median(self):
        judge = MockJudgeBackend(scores=[2, 4, 5])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=3)
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(_make_input(), _make_result())
        )
        assert result.details["median_score"] == 4
        assert result.score == pytest.approx(0.75)  # (4-1)/4

    def test_error_result(self):
        judge = MockJudgeBackend(scores=[5])
        evaluator = LLMJudgeEvaluator(judge_backend=judge)
        res = PipelineResult(pipeline_type="test", error="API error")
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(_make_input(), res)
        )
        assert result.score == 0.0
        assert result.passed is False

    def test_fallback_number_extraction(self):
        """When JSON parse fails, should extract digit from text."""
        judge = MockBadJudge()
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=1)
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(_make_input(), _make_result())
        )
        # Should extract "4" from "I think this deserves a 4 out of 5"
        assert result.details["median_score"] == 4
        assert result.score == pytest.approx(0.75)

    def test_all_judges_fail(self):
        judge = MockFailingJudge()
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=3)
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(_make_input(), _make_result())
        )
        assert result.score == 0.0
        assert result.passed is False
        assert "All judge calls failed" in result.details.get("error", "")

    def test_evaluator_name(self):
        judge = MockJudgeBackend(scores=[5])
        evaluator = LLMJudgeEvaluator(judge_backend=judge)
        assert evaluator.name == "llm_judge:mock_judge"

    def test_single_judge(self):
        judge = MockJudgeBackend(scores=[3])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=1)
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(_make_input(), _make_result())
        )
        assert result.details["median_score"] == 3
        assert result.score == pytest.approx(0.5)
        assert result.passed is False  # 0.5 < 0.6

    def test_normalization_range(self):
        """Score should always be 0.0-1.0."""
        for raw in [1, 2, 3, 4, 5]:
            judge = MockJudgeBackend(scores=[raw])
            evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=1)
            result = asyncio.get_event_loop().run_until_complete(
                evaluator.evaluate(_make_input(), _make_result())
            )
            assert 0.0 <= result.score <= 1.0
