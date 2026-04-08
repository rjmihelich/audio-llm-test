"""Pipeline C: Full telephony signal chain → LLM (direct or via ASR).

Applies the complete BT HFP telephony processing path (noise, echo, AEC
residual, AGC, codec, network degradation) before feeding the result to
the LLM via direct audio or ASR+text, depending on backend capabilities.
"""

from __future__ import annotations

import time

from ..audio.types import AudioBuffer
from ..audio.telephony_chain import TelephonyChain, TelephonyChainConfig
from ..llm.base import LLMBackend, ASRBackend
from .base import PipelineInput, PipelineResult


class TelephonyPipeline:
    """Pipeline C: telephony signal chain followed by LLM inference.

    The audio degradation path is fully configurable via TelephonyChainConfig.
    After degradation, audio is sent to the LLM either directly (if the
    backend supports audio input) or transcribed first via ASR.
    """

    def __init__(
        self,
        llm_backend: LLMBackend,
        chain_config: TelephonyChainConfig,
        asr_backend: ASRBackend | None = None,
    ):
        self._llm = llm_backend
        self._chain_config = chain_config
        self._asr = asr_backend
        self._chain = TelephonyChain(chain_config)

    @property
    def pipeline_type(self) -> str:
        return "telephony"

    async def execute(self, input: PipelineInput) -> PipelineResult:
        t0 = time.monotonic()

        try:
            # Run the full telephony chain
            chain_result = self._chain.process(input.clean_speech)
            degraded = chain_result.degraded_audio

            # Build telephony metadata for result storage
            telephony_metadata: dict = {
                "stages_applied": chain_result.stages_applied,
                "codec": (
                    self._chain_config.codec_config.codec_type.value
                    if self._chain_config.codec_config
                    else "none"
                ),
                "agc_preset": _agc_preset_name(self._chain_config),
                "aec_suppression_db": (
                    self._chain_config.aec_config.suppression_db
                    if self._chain_config.aec_config
                    else None
                ),
                "packet_loss_pct": (
                    self._chain_config.network_config.packet_loss_pct
                    if self._chain_config.network_config
                    else 0.0
                ),
                "jitter_ms": (
                    self._chain_config.network_config.jitter_ms
                    if self._chain_config.network_config
                    else 0.0
                ),
                "snr_db": self._chain_config.snr_db,
                "noise_type": self._chain_config.noise_type,
            }

            # Choose inference path based on backend capability
            if self._llm.supports_audio_input:
                llm_response = await self._llm.query_with_audio(
                    degraded, input.system_prompt
                )
                total_ms = (time.monotonic() - t0) * 1000
                return PipelineResult(
                    degraded_audio=degraded,
                    echo_audio=chain_result.echo_audio,
                    llm_response=llm_response,
                    pipeline_type=self.pipeline_type,
                    total_latency_ms=total_ms,
                    telephony_metadata=telephony_metadata,
                )
            else:
                # Fallback: ASR → text → LLM
                if self._asr is None:
                    total_ms = (time.monotonic() - t0) * 1000
                    return PipelineResult(
                        pipeline_type=self.pipeline_type,
                        total_latency_ms=total_ms,
                        error=(
                            "Backend does not support audio input and no ASR backend "
                            "is configured. Provide an asr_backend to use telephony pipeline "
                            "with text-only LLMs."
                        ),
                    )
                transcription = await self._asr.transcribe(degraded)
                llm_response = await self._llm.query_with_text(
                    transcription.text, input.system_prompt
                )
                total_ms = (time.monotonic() - t0) * 1000
                return PipelineResult(
                    degraded_audio=degraded,
                    echo_audio=chain_result.echo_audio,
                    transcription=transcription,
                    llm_response=llm_response,
                    pipeline_type=self.pipeline_type,
                    total_latency_ms=total_ms,
                    telephony_metadata=telephony_metadata,
                )

        except Exception as e:
            total_ms = (time.monotonic() - t0) * 1000
            return PipelineResult(
                pipeline_type=self.pipeline_type,
                total_latency_ms=total_ms,
                error=f"{type(e).__name__}: {e}",
            )


def _agc_preset_name(cfg: TelephonyChainConfig) -> str | None:
    """Return the AGC preset name for metadata, or None if no AGC."""
    if cfg.agc_config is None:
        return None
    from ..audio.agc import AGC_OFF, AGC_MILD, AGC_AGGRESSIVE
    if cfg.agc_config == AGC_OFF:
        return "off"
    if cfg.agc_config == AGC_MILD:
        return "mild"
    if cfg.agc_config == AGC_AGGRESSIVE:
        return "aggressive"
    return "custom"
