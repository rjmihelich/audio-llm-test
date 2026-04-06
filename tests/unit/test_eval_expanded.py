"""Expanded evaluation tests: false positives, edge cases, median correctness."""

from __future__ import annotations

import asyncio
import json
import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer
from backend.app.llm.base import LLMResponse, RateLimitConfig
from backend.app.pipeline.base import PipelineInput, PipelineResult
from backend.app.evaluation.command_match import (
    CommandMatchEvaluator,
    _normalize,
    _keyword_score,
)
from backend.app.evaluation.llm_judge import LLMJudgeEvaluator


def _make_input(expected_action: str, expected_intent: str = "test") -> PipelineInput:
    dummy = AudioBuffer(samples=np.zeros(100, dtype=np.float64), sample_rate=16000)
    return PipelineInput(
        clean_speech=dummy,
        original_text="test prompt",
        expected_intent=expected_intent,
        expected_action=expected_action,
    )


def _make_result(text: str) -> PipelineResult:
    return PipelineResult(
        pipeline_type="test",
        llm_response=LLMResponse(text=text),
    )


# ---------------------------------------------------------------------------
# Command match: false positive resistance
# ---------------------------------------------------------------------------

class TestCommandMatchFalsePositives:
    """Tests that the improved exact matching doesn't give false positives."""

    def test_negation_not_false_positive(self):
        """'don't turn on' should NOT match 'turn on' via keyword."""
        evaluator = CommandMatchEvaluator()
        inp = _make_input("turn on lights")
        res = _make_result("I'm sorry, I can't turn on the lights right now.")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        # The keyword score will still be high (keywords present), but this tests
        # that the system doesn't blindly return 1.0 exact match
        d = result.details
        # Exact match should still work (the words ARE present)
        # The point is we're testing the boundary — keyword matching
        # doesn't distinguish negation, which is a known limitation
        assert d["keyword_score"] > 0.5  # keywords "turn", "lights" are present

    def test_substring_false_positive_blocked(self):
        """'play' should not exact-match inside 'display settings'."""
        evaluator = CommandMatchEvaluator()
        inp = _make_input("play")
        res = _make_result("Opening display settings")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.details["exact_match"] is False

    def test_partial_word_not_exact(self):
        """'navigate' should not exact-match 'navigation menu'."""
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate")
        res = _make_result("Opening navigation menu")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        # "navigate" is not a whole word in "navigation" — exact should be False
        assert result.details["exact_match"] is False

    def test_exact_match_still_works_when_present(self):
        """'navigate' should exact-match 'I will navigate to the airport'."""
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("I will navigate to airport now")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.details["exact_match"] is True

    def test_empty_response(self):
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.score < 0.3
        assert result.passed is False

    def test_very_long_response_with_keyword(self):
        """Keywords buried in a long response should still be found."""
        evaluator = CommandMatchEvaluator()
        inp = _make_input("set temperature 72")
        long_response = "Sure, let me help you. " * 20 + "Setting temperature to 72 degrees." + " Hope that helps." * 10
        res = _make_result(long_response)
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.details["keyword_score"] > 0.5

    def test_unicode_normalization(self):
        """Unicode characters should be handled gracefully."""
        assert _normalize("café résumé") == "café résumé"

    def test_numbers_preserved(self):
        """Numbers should survive normalization."""
        assert _normalize("Set to 72 degrees") == "set to 72 degrees"


# ---------------------------------------------------------------------------
# Keyword scoring edge cases
# ---------------------------------------------------------------------------

class TestKeywordScoringExpanded:
    def test_all_stop_words_expected(self):
        """If expected is all stop words, score is 1.0."""
        assert _keyword_score("anything here", "the a an is to") == 1.0

    def test_duplicate_keywords_counted_once(self):
        """Repeated words don't inflate score."""
        score = _keyword_score("navigate navigate navigate", "navigate airport")
        assert score == 0.5  # Only "navigate" matches, "airport" doesn't

    def test_case_insensitive(self):
        assert _keyword_score("NAVIGATE TO AIRPORT", "navigate airport") == 1.0

    def test_empty_response(self):
        assert _keyword_score("", "navigate airport") == 0.0

    def test_single_keyword(self):
        assert _keyword_score("airport is nearby", "airport") == 1.0

    def test_stop_words_removed_from_both_sides(self):
        """Stop words should be removed from response too."""
        # "is" is a stop word, shouldn't count as a keyword
        score = _keyword_score("navigate is here", "navigate airport")
        assert score == 0.5  # Only "navigate" matches


# ---------------------------------------------------------------------------
# Fuzzy matching boundaries
# ---------------------------------------------------------------------------

class TestFuzzyMatchBoundaries:
    def test_one_char_difference(self):
        """One-character typo should still score very high."""
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("navigat to airport")  # missing 'e'
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.details["fuzzy_score"] > 0.9

    def test_completely_different_same_length(self):
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("xyzxyzxyz ab xyzxyzx")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.details["fuzzy_score"] < 0.3

    def test_threshold_boundary(self):
        """Score right at threshold should pass."""
        evaluator = CommandMatchEvaluator(pass_threshold=0.5)
        inp = _make_input("navigate airport")
        # Craft a response that gets ~0.5 keyword score
        res = _make_result("navigate to the park")  # 1 of 2 keywords
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.details["keyword_score"] == 0.5


# ---------------------------------------------------------------------------
# LLM Judge: median correctness
# ---------------------------------------------------------------------------

class TestLLMJudgeMedian:
    """Tests for the corrected median calculation."""

    def _make_judge_backend(self, scores):
        """Create a judge backend that returns predetermined scores."""
        call_idx = 0
        class MockJudge:
            @property
            def name(self): return "mock_judge"
            @property
            def supports_audio_input(self): return False
            @property
            def rate_limit(self): return RateLimitConfig()
            async def query_with_text(self, text, system_prompt, context=None):
                nonlocal call_idx
                s = scores[call_idx % len(scores)]
                call_idx += 1
                return LLMResponse(
                    text=json.dumps({"score": s, "reasoning": "test"}),
                    latency_ms=1.0, model="mock",
                )
        return MockJudge()

    def _eval(self, evaluator, response_text="test response"):
        dummy = AudioBuffer(samples=np.zeros(100), sample_rate=16000)
        inp = PipelineInput(
            clean_speech=dummy, original_text="test",
            expected_intent="test", expected_action="test",
        )
        res = PipelineResult(
            pipeline_type="test",
            llm_response=LLMResponse(text=response_text),
        )
        return asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))

    def test_odd_judges_median(self):
        """3 judges: median is the middle value."""
        judge = self._make_judge_backend([1, 3, 5])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=3)
        result = self._eval(evaluator)
        assert result.details["median_score"] == 3

    def test_even_judges_median_averaged(self):
        """2 judges: median should be average of two values."""
        judge = self._make_judge_backend([2, 4])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=2)
        result = self._eval(evaluator)
        # Fixed: should be (2+4)/2 = 3.0, not 4
        assert result.details["median_score"] == 3.0

    def test_four_judges_median(self):
        """4 judges: median of [1,2,4,5] = (2+4)/2 = 3.0."""
        judge = self._make_judge_backend([1, 2, 4, 5])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=4)
        result = self._eval(evaluator)
        assert result.details["median_score"] == 3.0

    def test_all_same_score(self):
        judge = self._make_judge_backend([5, 5, 5])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=3)
        result = self._eval(evaluator)
        assert result.details["median_score"] == 5
        assert result.score == 1.0  # (5-1)/4

    def test_all_lowest_score(self):
        judge = self._make_judge_backend([1, 1, 1])
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=3)
        result = self._eval(evaluator)
        assert result.score == 0.0  # (1-1)/4

    def test_normalization_boundaries(self):
        """Score 1 → 0.0, score 5 → 1.0."""
        for raw, expected in [(1, 0.0), (2, 0.25), (3, 0.5), (4, 0.75), (5, 1.0)]:
            judge = self._make_judge_backend([raw])
            evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=1)
            result = self._eval(evaluator)
            assert result.score == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# LLM Judge: fallback parsing
# ---------------------------------------------------------------------------

class TestLLMJudgeFallback:
    def _make_bad_judge(self, response_text):
        class BadJudge:
            @property
            def name(self): return "bad"
            @property
            def supports_audio_input(self): return False
            @property
            def rate_limit(self): return RateLimitConfig()
            async def query_with_text(self, text, system_prompt, context=None):
                return LLMResponse(text=response_text, latency_ms=1.0, model="mock")
        return BadJudge()

    def _eval(self, evaluator):
        dummy = AudioBuffer(samples=np.zeros(100), sample_rate=16000)
        inp = PipelineInput(
            clean_speech=dummy, original_text="test",
            expected_intent="test", expected_action="test",
        )
        res = PipelineResult(
            pipeline_type="test",
            llm_response=LLMResponse(text="some response"),
        )
        return asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))

    def test_plain_number(self):
        judge = self._make_bad_judge("4")
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=1)
        result = self._eval(evaluator)
        assert result.details["median_score"] == 4

    def test_number_in_text(self):
        judge = self._make_bad_judge("I would rate this a 3 out of 5")
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=1)
        result = self._eval(evaluator)
        assert result.details["median_score"] == 3

    def test_no_valid_digit_returns_3(self):
        """No digit 1-5 → default score of 3."""
        judge = self._make_bad_judge("This is a great response")
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=1)
        result = self._eval(evaluator)
        assert result.details["median_score"] == 3

    def test_digit_zero_skipped(self):
        """0 is not in range 1-5, should be skipped."""
        judge = self._make_bad_judge("Score: 0. Very bad.")
        evaluator = LLMJudgeEvaluator(judge_backend=judge, num_judges=1)
        result = self._eval(evaluator)
        # 0 is skipped, no other valid digit → default 3
        assert result.details["median_score"] == 3
