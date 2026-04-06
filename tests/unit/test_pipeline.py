"""Tests for pipeline execution with mocked LLM/ASR backends."""

import asyncio
import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer, FilterSpec
from backend.app.audio.echo import EchoConfig
from backend.app.llm.base import LLMResponse, RateLimitConfig, Transcription
from backend.app.pipeline.base import PipelineInput
from backend.app.pipeline.direct_audio import DirectAudioPipeline
from backend.app.pipeline.asr_text import ASRTextPipeline


class MockAudioLLM:
    """Mock LLM backend that supports audio input."""

    def __init__(self, response_text: str = "Navigating to airport"):
        self._response_text = response_text
        self.call_count = 0

    @property
    def name(self) -> str:
        return "mock_audio_llm"

    @property
    def supports_audio_input(self) -> bool:
        return True

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig()

    async def query_with_audio(self, audio, system_prompt, context=None) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(text=self._response_text, latency_ms=50.0, model="mock")

    async def query_with_text(self, text, system_prompt, context=None) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(text=self._response_text, latency_ms=30.0, model="mock")


class MockTextOnlyLLM:
    """Mock LLM that does not support audio."""

    @property
    def name(self) -> str:
        return "mock_text_llm"

    @property
    def supports_audio_input(self) -> bool:
        return False

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig()

    async def query_with_audio(self, audio, system_prompt, context=None):
        raise NotImplementedError("No audio support")

    async def query_with_text(self, text, system_prompt, context=None) -> LLMResponse:
        return LLMResponse(text=f"Understood: {text[:50]}", latency_ms=20.0, model="mock")


class MockASR:
    """Mock ASR backend."""

    def __init__(self, transcript: str = "navigate to the airport"):
        self._transcript = transcript

    @property
    def name(self) -> str:
        return "mock_asr"

    async def transcribe(self, audio: AudioBuffer) -> Transcription:
        return Transcription(
            text=self._transcript,
            language="en",
            confidence=0.95,
            latency_ms=100.0,
        )


def _make_speech(duration_s: float = 1.0, sr: int = 16000) -> AudioBuffer:
    """Generate a synthetic speech-like signal."""
    t = np.arange(int(sr * duration_s)) / sr
    signal = 0.3 * np.sin(2 * np.pi * 300 * t)
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)
    return AudioBuffer(samples=signal * envelope, sample_rate=sr)


def _make_input(speech=None) -> PipelineInput:
    return PipelineInput(
        clean_speech=speech or _make_speech(),
        original_text="Navigate to the airport",
        expected_intent="navigation",
        expected_action="navigate_to:airport",
    )


# ---------------------------------------------------------------------------
# DirectAudioPipeline
# ---------------------------------------------------------------------------

class TestDirectAudioPipeline:
    def test_basic_execution(self):
        llm = MockAudioLLM()
        pipeline = DirectAudioPipeline(llm_backend=llm, snr_db=10.0)
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(_make_input())
        )
        assert result.error is None
        assert result.llm_response is not None
        assert result.llm_response.text == "Navigating to airport"
        assert result.degraded_audio is not None
        assert result.pipeline_type == "direct_audio"
        assert result.total_latency_ms > 0
        assert llm.call_count == 1

    def test_noise_types(self):
        for noise_type in ["pink_lpf", "white", "babble"]:
            llm = MockAudioLLM()
            pipeline = DirectAudioPipeline(llm_backend=llm, snr_db=5.0, noise_type=noise_type)
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.execute(_make_input())
            )
            assert result.error is None, f"Failed for noise_type={noise_type}"
            assert result.degraded_audio is not None

    def test_with_echo(self):
        llm = MockAudioLLM()
        echo_cfg = EchoConfig(delay_ms=50, gain_db=-10)
        pipeline = DirectAudioPipeline(
            llm_backend=llm, snr_db=10.0, echo_config=echo_cfg
        )
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(_make_input())
        )
        assert result.error is None
        assert result.echo_audio is not None

    def test_with_echo_and_eq(self):
        llm = MockAudioLLM()
        echo_cfg = EchoConfig(
            delay_ms=100, gain_db=-10,
            eq_chain=[
                FilterSpec("hpf", 80.0),
                FilterSpec("lpf", 6000.0),
                FilterSpec("peaking", 2500.0, Q=2.0, gain_db=4.0),
            ],
        )
        pipeline = DirectAudioPipeline(
            llm_backend=llm, snr_db=10.0, echo_config=echo_cfg
        )
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(_make_input())
        )
        assert result.error is None

    def test_text_only_backend_rejected(self):
        llm = MockTextOnlyLLM()
        with pytest.raises(ValueError, match="does not support audio"):
            DirectAudioPipeline(llm_backend=llm, snr_db=10.0)

    def test_negative_snr(self):
        llm = MockAudioLLM()
        pipeline = DirectAudioPipeline(llm_backend=llm, snr_db=-10.0)
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(_make_input())
        )
        assert result.error is None
        # Degraded should have higher RMS than clean (noise dominates)
        clean_rms = _make_speech().rms
        assert result.degraded_audio.rms > clean_rms * 0.5

    def test_seed_determinism(self):
        llm = MockAudioLLM()
        p1 = DirectAudioPipeline(llm_backend=llm, snr_db=5.0, noise_seed=42)
        p2 = DirectAudioPipeline(llm_backend=llm, snr_db=5.0, noise_seed=42)
        inp = _make_input()
        r1 = asyncio.get_event_loop().run_until_complete(p1.execute(inp))
        r2 = asyncio.get_event_loop().run_until_complete(p2.execute(inp))
        np.testing.assert_array_almost_equal(
            r1.degraded_audio.samples, r2.degraded_audio.samples
        )


# ---------------------------------------------------------------------------
# ASRTextPipeline
# ---------------------------------------------------------------------------

class TestASRTextPipeline:
    def test_basic_execution(self):
        asr = MockASR()
        llm = MockTextOnlyLLM()
        pipeline = ASRTextPipeline(asr_backend=asr, llm_backend=llm, snr_db=10.0)
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(_make_input())
        )
        assert result.error is None
        assert result.transcription is not None
        assert result.transcription.text == "navigate to the airport"
        assert result.llm_response is not None
        assert "Understood:" in result.llm_response.text
        assert result.pipeline_type == "asr_text"

    def test_noise_types(self):
        for noise_type in ["pink_lpf", "white", "babble"]:
            asr = MockASR()
            llm = MockTextOnlyLLM()
            pipeline = ASRTextPipeline(
                asr_backend=asr, llm_backend=llm, snr_db=5.0, noise_type=noise_type
            )
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.execute(_make_input())
            )
            assert result.error is None, f"Failed for noise_type={noise_type}"

    def test_with_echo(self):
        asr = MockASR()
        llm = MockTextOnlyLLM()
        echo_cfg = EchoConfig(delay_ms=100, gain_db=-10)
        pipeline = ASRTextPipeline(
            asr_backend=asr, llm_backend=llm, snr_db=10.0, echo_config=echo_cfg
        )
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(_make_input())
        )
        assert result.error is None
        assert result.transcription is not None

    def test_with_audio_capable_backend(self):
        """ASR pipeline should work with any backend (audio or text-only)."""
        asr = MockASR()
        llm = MockAudioLLM()
        pipeline = ASRTextPipeline(asr_backend=asr, llm_backend=llm, snr_db=10.0)
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.execute(_make_input())
        )
        assert result.error is None
