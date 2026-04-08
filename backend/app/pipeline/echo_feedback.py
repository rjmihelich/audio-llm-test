"""Echo feedback loop: simulates multi-turn conversation with acoustic echo.

In a car, when the LLM responds through the speakers, that audio leaks back
into the microphone. The next user utterance is then contaminated with echo
from the previous LLM response. This pipeline simulates that scenario.

This is a single-pass offline simulation — NOT real-time streaming.
Each turn's audio is pre-computed, making results fully reproducible.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..audio.types import AudioBuffer
from ..audio.noise import generate_noise
from ..audio.mixer import mix_with_gain
from ..audio.echo import EchoConfig, EchoPath
from ..llm.base import LLMBackend, ASRBackend
from ..speech.tts_base import TTSProvider
from .base import PipelineInput, PipelineResult


@dataclass
class EchoFeedbackResult:
    """Results from a multi-turn echo feedback test."""

    turns: list[PipelineResult]
    total_latency_ms: float = 0.0


class EchoFeedbackPipeline:
    """Multi-turn echo feedback simulation.

    Flow for each turn:
    1. Add noise to clean speech at target SNR
    2. If there's a previous LLM response audio, apply echo path and mix
    3. Send degraded+echo audio to LLM (direct or via ASR)
    4. Capture LLM response (audio or text → TTS)
    5. Use LLM response audio as echo source for next turn
    """

    def __init__(
        self,
        llm_backend: LLMBackend,
        echo_config: EchoConfig,
        noise_level_db: float,
        noise_type: str = "pink_lpf",
        noise_file: str | None = None,
        sample_rate: int = 16000,
        noise_seed: int | None = None,
        # Optional: for Pipeline B path
        asr_backend: ASRBackend | None = None,
        # Optional: for generating echo audio when LLM doesn't return audio
        tts_provider: TTSProvider | None = None,
        tts_voice_id: str = "alloy",
        num_turns: int = 2,
    ):
        self._llm = llm_backend
        self._echo_config = echo_config
        self._echo_path = EchoPath(echo_config, sample_rate)
        self._noise_level_db = noise_level_db
        self._noise_type = noise_type
        self._noise_file = noise_file
        self._sample_rate = sample_rate
        self._noise_seed = noise_seed
        self._asr = asr_backend
        self._tts = tts_provider
        self._tts_voice_id = tts_voice_id
        self._num_turns = num_turns

    @property
    def pipeline_type(self) -> str:
        return "echo_feedback"

    def _generate_noise(self, duration_s: float, num_samples: int) -> AudioBuffer:
        return generate_noise(
            self._noise_type, duration_s, num_samples,
            sample_rate=self._sample_rate, seed=self._noise_seed,
            noise_file=self._noise_file,
        )

    async def execute(self, input: PipelineInput) -> PipelineResult:
        """Execute single turn (for compatibility with Pipeline interface).

        For multi-turn, use execute_multi_turn() directly.
        """
        result = await self.execute_multi_turn([input])
        # Return the last turn's result
        return result.turns[-1] if result.turns else PipelineResult(
            pipeline_type=self.pipeline_type, error="No turns executed"
        )

    async def execute_multi_turn(
        self, inputs: list[PipelineInput]
    ) -> EchoFeedbackResult:
        """Execute multi-turn echo feedback simulation.

        Args:
            inputs: One PipelineInput per turn. If fewer inputs than num_turns,
                the last input is repeated.
        """
        t0 = time.monotonic()
        turn_results: list[PipelineResult] = []
        previous_llm_audio: AudioBuffer | None = None

        for turn_idx in range(self._num_turns):
            turn_input = inputs[min(turn_idx, len(inputs) - 1)]
            turn_t0 = time.monotonic()

            try:
                speech = turn_input.clean_speech.resample(self._sample_rate)

                # Add noise
                noise = self._generate_noise(speech.duration_s, speech.num_samples)
                degraded = mix_with_gain(speech, noise, self._noise_level_db)

                # Add echo from previous LLM response
                echo_component = None
                if previous_llm_audio is not None:
                    echo_component = self._echo_path.process_echo(previous_llm_audio)
                    degraded = self._echo_path.apply(degraded, previous_llm_audio)

                # Send to LLM
                transcription = None
                if self._asr and not self._llm.supports_audio_input:
                    # Pipeline B path
                    transcription = await self._asr.transcribe(degraded)
                    llm_response = await self._llm.query_with_text(
                        transcription.text, turn_input.system_prompt
                    )
                else:
                    # Pipeline A path
                    llm_response = await self._llm.query_with_audio(
                        degraded, turn_input.system_prompt
                    )

                # Get LLM response audio for next turn's echo
                if llm_response.audio is not None:
                    previous_llm_audio = llm_response.audio
                elif self._tts and llm_response.text:
                    previous_llm_audio = await self._tts.synthesize(
                        llm_response.text, self._tts_voice_id
                    )
                else:
                    previous_llm_audio = None

                turn_ms = (time.monotonic() - turn_t0) * 1000
                turn_results.append(PipelineResult(
                    degraded_audio=degraded,
                    echo_audio=echo_component,
                    transcription=transcription,
                    llm_response=llm_response,
                    pipeline_type=f"echo_feedback:turn_{turn_idx}",
                    total_latency_ms=turn_ms,
                ))

            except Exception as e:
                turn_ms = (time.monotonic() - turn_t0) * 1000
                turn_results.append(PipelineResult(
                    pipeline_type=f"echo_feedback:turn_{turn_idx}",
                    total_latency_ms=turn_ms,
                    error=str(e),
                ))
                break  # Stop on error

        total_ms = (time.monotonic() - t0) * 1000
        return EchoFeedbackResult(turns=turn_results, total_latency_ms=total_ms)
