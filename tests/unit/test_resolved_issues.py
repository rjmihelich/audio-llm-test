"""Tests for the four resolved limitations:
1. Negation detection in command_match
2. Soft-clip preserves SNR at moderate levels
3. Multi-language stop words
4. Disk checkpointing for scheduler crash recovery
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer
from backend.app.audio.mixer import mix_at_snr, _soft_clip
from backend.app.audio.noise import white_noise
from backend.app.llm.base import LLMResponse, RateLimitConfig
from backend.app.pipeline.base import PipelineInput, PipelineResult
from backend.app.evaluation.command_match import (
    CommandMatchEvaluator,
    _detect_negation,
    _get_stop_words,
    _keyword_score,
    STOP_WORDS,
    NEGATION_PATTERNS,
)
from backend.app.execution.scheduler import (
    TestScheduler as Scheduler,
    TestCaseConfig,
    TestResultRecord,
    CheckpointStore,
)
from backend.app.audio.io import save_audio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dummy_input(expected_action="navigate to airport"):
    dummy = AudioBuffer(samples=np.zeros(100, dtype=np.float64), sample_rate=16000)
    return PipelineInput(
        clean_speech=dummy, original_text="test",
        expected_intent="test", expected_action=expected_action,
    )

def _dummy_result(text):
    return PipelineResult(
        pipeline_type="test", llm_response=LLMResponse(text=text),
    )

def _sine(freq=300.0, dur=1.0, sr=16000, amp=0.5):
    t = np.arange(int(sr * dur)) / sr
    return AudioBuffer(samples=amp * np.sin(2 * np.pi * freq * t), sample_rate=sr)


# ===========================================================================
# 1. Negation detection
# ===========================================================================

class TestNegationDetection:
    def test_basic_negation_words(self):
        assert _detect_negation("I can't do that") is True
        assert _detect_negation("I cannot do that") is True
        assert _detect_negation("I won't do that") is True
        assert _detect_negation("I don't know") is True
        assert _detect_negation("It doesn't work") is True

    def test_no_negation(self):
        assert _detect_negation("I will navigate to the airport") is False
        assert _detect_negation("Setting temperature to 72") is False
        assert _detect_negation("Playing your favorite song") is False

    def test_contraction_variants(self):
        assert _detect_negation("I don't want that") is True
        assert _detect_negation("I dont want that") is True
        assert _detect_negation("She isn't here") is True
        assert _detect_negation("They aren't ready") is True

    def test_unable_refuse(self):
        assert _detect_negation("I'm unable to perform that action") is True
        assert _detect_negation("I refuse to do that") is True

    def test_sorry_cant(self):
        assert _detect_negation("Sorry, I can't help with that") is True

    def test_negation_penalty_applied(self):
        evaluator = CommandMatchEvaluator()
        inp = _dummy_input("turn on lights")
        # Affirmative response
        res_pos = _dummy_result("Turning on the lights now")
        result_pos = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(inp, res_pos)
        )
        # Negated response
        res_neg = _dummy_result("I can't turn on the lights right now")
        result_neg = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(inp, res_neg)
        )
        assert result_neg.details["negated"] is True
        assert result_pos.details["negated"] is False
        # Negated response should score lower
        assert result_neg.score < result_pos.score

    def test_negation_causes_failure(self):
        """Negated response with default penalty should fail for borderline scores."""
        evaluator = CommandMatchEvaluator(pass_threshold=0.6, negation_penalty=0.5)
        inp = _dummy_input("navigate to airport")
        res = _dummy_result("I can't navigate to the airport right now")
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(inp, res)
        )
        assert result.details["negated"] is True
        # Keyword score ~1.0 * (1 - 0.5) = 0.5, below 0.6 threshold
        assert result.passed is False

    def test_custom_negation_penalty(self):
        # With 0 penalty, negation doesn't affect score
        evaluator = CommandMatchEvaluator(negation_penalty=0.0)
        inp = _dummy_input("navigate to airport")
        res = _dummy_result("I can't navigate to the airport")
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(inp, res)
        )
        assert result.details["negated"] is True
        assert result.score > 0.5  # Score unaffected

    def test_german_negation(self):
        assert _detect_negation("Ich kann das nicht machen", lang="de") is True
        assert _detect_negation("Ich mache das gerne", lang="de") is False

    def test_french_negation(self):
        assert _detect_negation("Je ne peux pas faire ça", lang="fr") is True
        assert _detect_negation("Je fais ça maintenant", lang="fr") is False

    def test_spanish_negation(self):
        assert _detect_negation("No puedo hacer eso", lang="es") is True
        assert _detect_negation("Hago eso ahora", lang="es") is False


# ===========================================================================
# 2. Soft-clip preserves SNR
# ===========================================================================

class TestSoftClipSNRPreservation:
    def test_below_threshold_passthrough(self):
        """Signals under 0.95 peak should be completely unchanged."""
        samples = np.array([0.0, 0.3, -0.5, 0.9, -0.94])
        result = _soft_clip(samples)
        np.testing.assert_array_equal(result, samples)

    def test_above_threshold_compressed(self):
        """Signals over 0.95 should be compressed into (0.95, 1.0]."""
        samples = np.array([0.0, 0.5, 1.5, 2.0, -1.5])
        result = _soft_clip(samples)
        assert np.all(np.abs(result) <= 1.0)
        # Below-threshold samples unchanged
        assert result[0] == 0.0
        assert result[1] == 0.5

    def test_snr_preserved_at_moderate_levels(self):
        """At +20 dB SNR with amplitude 0.3, mixed signal stays below threshold.
        SNR should be perfectly preserved (no clipping distortion)."""
        speech = _sine(amp=0.3)
        noise = white_noise(1.0, 16000, seed=42)
        mixed = mix_at_snr(speech, noise, 20.0)

        # The mixed signal should be unchanged (peak << 0.95)
        assert mixed.peak < 0.95

        # Verify actual SNR
        noise_rms_target = speech.rms / (10 ** (20.0 / 20.0))
        noise_samples = noise.loop_to_length(speech.num_samples).samples
        scale = noise_rms_target / np.sqrt(np.mean(noise_samples ** 2))
        raw_mixed = speech.samples + scale * noise_samples
        # Since no clipping occurred, mixed should equal raw_mixed exactly
        np.testing.assert_array_almost_equal(mixed.samples, raw_mixed)

    def test_extreme_signal_bounded(self):
        """Even with very large input, output stays within [-1, 1]."""
        samples = np.array([10.0, -10.0, 100.0, -100.0])
        result = _soft_clip(samples)
        assert np.all(result >= -1.0)
        assert np.all(result <= 1.0)

    def test_monotonicity(self):
        """Soft-clip should be monotonically increasing."""
        x = np.linspace(-3, 3, 1000)
        y = _soft_clip(x)
        diffs = np.diff(y)
        assert np.all(diffs >= 0)

    def test_continuity_at_threshold(self):
        """No discontinuity at the threshold boundary."""
        threshold = 0.95
        x = np.array([threshold - 0.001, threshold, threshold + 0.001])
        y = _soft_clip(x)
        # Differences should be small (continuous)
        assert abs(y[1] - y[0]) < 0.005
        assert abs(y[2] - y[1]) < 0.005


# ===========================================================================
# 3. Multi-language stop words
# ===========================================================================

class TestMultiLanguageStopWords:
    def test_english_stop_words(self):
        sw = _get_stop_words("en")
        assert "the" in sw
        assert "is" in sw
        assert "navigate" not in sw

    def test_german_stop_words(self):
        sw = _get_stop_words("de")
        assert "der" in sw
        assert "und" in sw

    def test_french_stop_words(self):
        sw = _get_stop_words("fr")
        assert "le" in sw
        assert "est" in sw

    def test_spanish_stop_words(self):
        sw = _get_stop_words("es")
        assert "el" in sw
        assert "de" in sw

    def test_japanese_stop_words(self):
        sw = _get_stop_words("ja")
        assert "の" in sw

    def test_unknown_language_falls_back_to_english(self):
        sw = _get_stop_words("xx")
        assert sw == STOP_WORDS["en"]

    def test_keyword_score_with_german(self):
        # "der" is a German stop word, should be removed
        score = _keyword_score("Navigiere zum Flughafen", "Navigiere der Flughafen", lang="de")
        # "der" removed from expected, "navigiere" and "flughafen" remain
        assert score == 1.0

    def test_evaluator_lang_parameter(self):
        evaluator = CommandMatchEvaluator(lang="de")
        inp = _dummy_input("Navigiere zum Flughafen")
        res = _dummy_result("Ich navigiere zum Flughafen")
        result = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(inp, res)
        )
        assert result.passed is True


# ===========================================================================
# 4. Disk checkpointing
# ===========================================================================

class TestCheckpointStore:
    def test_append_and_load(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            store = CheckpointStore(path)
            store.append({"test_case_hash": "abc123", "score": 0.9})
            store.append({"test_case_hash": "def456", "score": 0.7})

            hashes = store.load_completed_hashes()
            assert hashes == {"abc123", "def456"}

            records = store.load_records()
            assert len(records) == 2
            assert records[0]["score"] == 0.9
        finally:
            os.unlink(path)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            store = CheckpointStore(path)
            assert store.load_completed_hashes() == set()
            assert store.load_records() == []
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        store = CheckpointStore("/tmp/nonexistent_checkpoint_xyz.jsonl")
        assert store.load_completed_hashes() == set()
        assert store.load_records() == []

    def test_corrupt_lines_skipped(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            f.write('{"test_case_hash": "good"}\n')
            f.write("not valid json\n")
            f.write('{"test_case_hash": "also_good"}\n')
            path = f.name
        try:
            store = CheckpointStore(path)
            hashes = store.load_completed_hashes()
            assert hashes == {"good", "also_good"}
        finally:
            os.unlink(path)

    def test_incremental_append(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            store = CheckpointStore(path)
            store.append({"test_case_hash": "first"})
            assert len(store.load_completed_hashes()) == 1

            store.append({"test_case_hash": "second"})
            assert len(store.load_completed_hashes()) == 2
        finally:
            os.unlink(path)


class TestSchedulerCheckpointing:
    def _create_speech_file(self):
        t = np.arange(16000) / 16000
        samples = 0.3 * np.sin(2 * np.pi * 300 * t)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        save_audio(buf, path)
        return path

    def test_checkpoint_written_on_completion(self):
        speech_file = self._create_speech_file()
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            ckpt_path = f.name
        try:
            class MockLLM:
                @property
                def name(self): return "mock"
                @property
                def supports_audio_input(self): return True
                @property
                def rate_limit(self):
                    return RateLimitConfig(requests_per_minute=60000, max_concurrent=100)
                async def query_with_audio(self, audio, prompt, context=None):
                    return LLMResponse(text="ok", latency_ms=1.0, model="mock")

            llm = MockLLM()
            scheduler = Scheduler(
                backends={"mock": llm},
                checkpoint_path=ckpt_path,
            )
            cases = [
                TestCaseConfig(
                    id=f"tc_{i}", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    snr_db=float(i), pipeline="direct_audio", llm_backend="mock",
                )
                for i in range(5)
            ]
            results = asyncio.get_event_loop().run_until_complete(scheduler.run(cases))
            assert len(results) == 5

            # Verify checkpoint file has all 5 records
            store = CheckpointStore(ckpt_path)
            hashes = store.load_completed_hashes()
            assert len(hashes) == 5
        finally:
            os.unlink(speech_file)
            os.unlink(ckpt_path)

    def test_resume_from_checkpoint(self):
        """Run 3 cases, then resume — checkpoint should skip the first 3."""
        speech_file = self._create_speech_file()
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            ckpt_path = f.name
        try:
            class MockLLM:
                def __init__(self):
                    self.calls = 0
                @property
                def name(self): return "mock"
                @property
                def supports_audio_input(self): return True
                @property
                def rate_limit(self):
                    return RateLimitConfig(requests_per_minute=60000, max_concurrent=100)
                async def query_with_audio(self, audio, prompt, context=None):
                    self.calls += 1
                    return LLMResponse(text="ok", latency_ms=1.0, model="mock")

            cases = [
                TestCaseConfig(
                    id=f"tc_{i}", speech_file=speech_file,
                    original_text="test", expected_intent="test",
                    snr_db=float(i), pipeline="direct_audio", llm_backend="mock",
                )
                for i in range(5)
            ]

            # Run 1: execute first 3 (by giving last 2 as completed_ids so
            # we can control which get checkpointed)
            llm1 = MockLLM()
            scheduler1 = Scheduler(
                backends={"mock": llm1},
                checkpoint_path=ckpt_path,
            )
            skip = {cases[i].deterministic_hash for i in range(2)}
            results1 = asyncio.get_event_loop().run_until_complete(
                scheduler1.run(cases, completed_ids=skip)
            )
            assert llm1.calls == 3

            # Run 2: new scheduler, same checkpoint — should skip the 3 we just ran
            llm2 = MockLLM()
            scheduler2 = Scheduler(
                backends={"mock": llm2},
                checkpoint_path=ckpt_path,
            )
            results2 = asyncio.get_event_loop().run_until_complete(
                scheduler2.run(cases)
            )
            # Only the 2 we skipped in run 1 should need running
            assert llm2.calls == 2
        finally:
            os.unlink(speech_file)
            os.unlink(ckpt_path)
