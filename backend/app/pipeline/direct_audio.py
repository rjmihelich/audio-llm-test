"""Pipeline A: Raw audio → multimodal LLM (GPT-4o, Gemini)."""

from __future__ import annotations

import time

from ..audio.types import AudioBuffer, FilterSpec
from ..audio.noise import generate_noise
from ..audio.mixer import mix_at_snr
from ..audio.echo import EchoConfig, EchoPath
from ..llm.base import LLMBackend
from .base import PipelineInput, PipelineResult


class DirectAudioPipeline:
    """Send degraded audio directly to a multimodal LLM."""

    def __init__(
        self,
        llm_backend: LLMBackend,
        snr_db: float,
        noise_type: str = "pink_lpf",
        noise_file: str | None = None,
        echo_config: EchoConfig | None = None,
        sample_rate: int = 16000,
        noise_seed: int | None = None,
    ):
        if not llm_backend.supports_audio_input:
            raise ValueError(f"Backend {llm_backend.name} does not support audio input")
        self._llm = llm_backend
        self._snr_db = snr_db
        self._noise_type = noise_type
        self._noise_file = noise_file
        self._echo_config = echo_config
        self._sample_rate = sample_rate
        self._noise_seed = noise_seed

    @property
    def pipeline_type(self) -> str:
        return "direct_audio"

    def _generate_noise(self, duration_s: float, num_samples: int) -> AudioBuffer:
        return generate_noise(
            self._noise_type, duration_s, num_samples,
            sample_rate=self._sample_rate, seed=self._noise_seed,
            noise_file=self._noise_file,
        )

    async def execute(self, input: PipelineInput) -> PipelineResult:
        t0 = time.monotonic()

        try:
            speech = input.clean_speech.resample(self._sample_rate)

            # Generate and mix noise
            noise = self._generate_noise(speech.duration_s, speech.num_samples)
            degraded = mix_at_snr(speech, noise, self._snr_db)

            # Apply echo if configured
            echo_audio = None
            if self._echo_config:
                echo_path = EchoPath(self._echo_config, self._sample_rate)
                echo_audio = echo_path.process_echo(speech)
                degraded = echo_path.apply(degraded, speech)

            # Send to LLM
            llm_response = await self._llm.query_with_audio(
                degraded, input.system_prompt
            )

            total_ms = (time.monotonic() - t0) * 1000
            return PipelineResult(
                degraded_audio=degraded,
                echo_audio=echo_audio,
                llm_response=llm_response,
                pipeline_type=self.pipeline_type,
                total_latency_ms=total_ms,
            )
        except Exception as e:
            total_ms = (time.monotonic() - t0) * 1000
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                total_latency_ms=total_ms,
                error=str(e),
            )
