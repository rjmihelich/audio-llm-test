"""Pipeline B: Audio → Whisper ASR → text → LLM."""

from __future__ import annotations

import time

from ..audio.types import AudioBuffer
from ..audio.noise import generate_noise
from ..audio.mixer import mix_at_snr
from ..audio.echo import EchoConfig, EchoPath
from ..llm.base import LLMBackend, ASRBackend
from .base import PipelineInput, PipelineResult



class ASRTextPipeline:
    """Transcribe degraded audio via ASR, then send text to an LLM."""

    def __init__(
        self,
        asr_backend: ASRBackend,
        llm_backend: LLMBackend,
        snr_db: float,
        noise_type: str = "pink_lpf",
        noise_file: str | None = None,
        echo_config: EchoConfig | None = None,
        sample_rate: int = 16000,
        noise_seed: int | None = None,
    ):
        self._asr = asr_backend
        self._llm = llm_backend
        self._snr_db = snr_db
        self._noise_type = noise_type
        self._noise_file = noise_file
        self._echo_config = echo_config
        self._sample_rate = sample_rate
        self._noise_seed = noise_seed

    @property
    def pipeline_type(self) -> str:
        return "asr_text"

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

            # ASR: transcribe the degraded audio
            transcription = await self._asr.transcribe(degraded)

            # Send transcript to LLM
            llm_response = await self._llm.query_with_text(
                transcription.text, input.system_prompt
            )

            total_ms = (time.monotonic() - t0) * 1000
            return PipelineResult(
                degraded_audio=degraded,
                transcription=transcription,
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
