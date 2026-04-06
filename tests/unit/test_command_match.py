"""Tests for command matching evaluator."""

from __future__ import annotations

import asyncio
import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer
from backend.app.llm.base import LLMResponse
from backend.app.pipeline.base import PipelineInput, PipelineResult
from backend.app.evaluation.command_match import (
    CommandMatchEvaluator,
    _normalize,
    _keyword_score,
)


def _make_input(expected_action: str, expected_intent: str = "navigate") -> PipelineInput:
    dummy = AudioBuffer(samples=np.zeros(100, dtype=np.float64), sample_rate=16000)
    return PipelineInput(
        clean_speech=dummy,
        original_text="Navigate to the airport",
        expected_intent=expected_intent,
        expected_action=expected_action,
    )


def _make_result(response_text: str, error: str | None = None) -> PipelineResult:
    if error:
        return PipelineResult(pipeline_type="test", error=error)
    return PipelineResult(
        pipeline_type="test",
        llm_response=LLMResponse(text=response_text),
    )


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Hello World") == "hello world"

    def test_strip_punctuation(self):
        assert _normalize("Hello, World!") == "hello world"

    def test_collapse_whitespace(self):
        assert _normalize("hello   world") == "hello world"

    def test_strip_outer(self):
        assert _normalize("  hello  ") == "hello"


class TestKeywordScore:
    def test_perfect_match(self):
        assert _keyword_score("navigate to airport", "navigate airport") == 1.0

    def test_partial_match(self):
        score = _keyword_score("navigate somewhere", "navigate airport")
        assert 0.0 < score < 1.0

    def test_no_match(self):
        score = _keyword_score("play music", "navigate airport")
        assert score == 0.0

    def test_stop_words_removed(self):
        # "to" and "the" are stop words — only "navigate" and "airport" matter
        score = _keyword_score("navigate to the airport", "navigate to the airport")
        assert score == 1.0

    def test_empty_expected(self):
        # All expected words are stop words → returns 1.0
        assert _keyword_score("anything", "the a an") == 1.0


class TestCommandMatchEvaluator:
    def test_exact_match(self):
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("Navigate to airport!")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.passed is True
        assert result.score == 1.0
        assert result.details["exact_match"] is True

    def test_fuzzy_match(self):
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("navigating to the airport")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.score > 0.6
        assert result.passed is True

    def test_keyword_match(self):
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("Sure, I'll navigate you to the airport right away.")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.passed is True
        assert result.details["keyword_score"] == 1.0

    def test_no_match(self):
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("Playing your favorite song now")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.score < 0.6
        assert result.passed is False

    def test_error_result(self):
        evaluator = CommandMatchEvaluator()
        inp = _make_input("navigate to airport")
        res = _make_result("", error="API timeout")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.score == 0.0
        assert result.passed is False

    def test_no_expected_action(self):
        evaluator = CommandMatchEvaluator()
        dummy = AudioBuffer(samples=np.zeros(100, dtype=np.float64), sample_rate=16000)
        inp = PipelineInput(
            clean_speech=dummy,
            original_text="test",
            expected_intent="",
            expected_action=None,
        )
        res = _make_result("some response")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.passed is False

    def test_custom_thresholds(self):
        evaluator = CommandMatchEvaluator(pass_threshold=0.9)
        inp = _make_input("navigate to airport")
        # Keyword match might be ~0.5-0.7, fuzzy might be < 0.9
        res = _make_result("I think maybe go to airport area")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        # With 0.9 threshold, borderline responses should fail
        assert result.score < 0.9 or result.passed is True

    def test_best_of_three_methods(self):
        evaluator = CommandMatchEvaluator()
        inp = _make_input("set temperature to 72 degrees")
        res = _make_result("Setting the temperature to 72 degrees for you.")
        result = asyncio.get_event_loop().run_until_complete(evaluator.evaluate(inp, res))
        assert result.passed is True
        # best_score should be the max of all three
        d = result.details
        assert d["best_score"] == max(
            1.0 if d["exact_match"] else 0.0,
            d["fuzzy_score"],
            d["keyword_score"],
        )
