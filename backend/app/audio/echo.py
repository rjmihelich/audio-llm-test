"""Acoustic echo path simulation for car cabin testing.

Models the feedback path from car speakers back to the microphone:
  LLM audio output → delay → gain → EQ filter chain → mixed into mic input
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .types import AudioBuffer, FilterSpec
from .filters import FilterChain


@dataclass(frozen=True)
class EchoConfig:
    """Configuration for the acoustic echo path.

    Attributes:
        delay_ms: Speaker-to-mic propagation delay (0-500ms).
        gain_db: Echo attenuation (-100 to 0 dB). 0 dB = full level, -100 dB = effectively silent.
        eq_chain: Filter specs modeling the cabin frequency response.
            Typical car cabin: HPF at 80Hz (speaker rolloff), LPF at 8kHz (air absorption),
            peaking at 2-4kHz (cabin resonance).
    """

    delay_ms: float = 50.0
    gain_db: float = -20.0
    eq_chain: list[FilterSpec] = field(default_factory=list)

    def __post_init__(self):
        if not (0 <= self.delay_ms <= 500):
            raise ValueError(f"delay_ms must be 0-500, got {self.delay_ms}")
        if not (-100 <= self.gain_db <= 0):
            raise ValueError(f"gain_db must be -100 to 0, got {self.gain_db}")


class EchoPath:
    """Applies acoustic echo to simulate speaker-to-mic feedback."""

    def __init__(self, config: EchoConfig, sample_rate: int):
        self.config = config
        self.sample_rate = sample_rate
        self._delay_samples = int(config.delay_ms * sample_rate / 1000.0)
        self._gain_linear = 10 ** (config.gain_db / 20.0)
        self._filter_chain = FilterChain(config.eq_chain, sample_rate)

    def process_echo(self, speaker_audio: AudioBuffer) -> AudioBuffer:
        """Process the speaker output through the echo path (delay + gain + EQ).

        Returns the echo signal that would be picked up by the microphone.
        This does NOT add it to the mic input — use apply() for that.
        """
        if speaker_audio.sample_rate != self.sample_rate:
            speaker_audio = speaker_audio.resample(self.sample_rate)

        samples = speaker_audio.samples

        # Apply delay (prepend zeros)
        if self._delay_samples > 0:
            delayed = np.zeros(len(samples) + self._delay_samples, dtype=np.float64)
            delayed[self._delay_samples:] = samples
            samples = delayed
        else:
            samples = samples.copy()

        # Apply gain
        samples *= self._gain_linear

        # Apply EQ filter chain
        echo_buf = AudioBuffer(samples=samples, sample_rate=self.sample_rate)
        echo_buf = self._filter_chain.apply(echo_buf)

        return echo_buf

    def apply(self, mic_input: AudioBuffer, speaker_audio: AudioBuffer) -> AudioBuffer:
        """Add acoustic echo from speaker_audio into mic_input.

        The echo signal is processed (delay + gain + EQ) and then summed
        with the microphone input, simulating what the mic would capture
        in a real car cabin.

        Args:
            mic_input: The microphone signal (speech + noise).
            speaker_audio: The audio being played through the car speakers
                (typically the LLM's previous response).

        Returns:
            The mic input with echo added.
        """
        echo = self.process_echo(speaker_audio)

        # Time-align: truncate or pad echo to match mic input length
        mic_len = mic_input.num_samples
        if echo.num_samples > mic_len:
            echo_samples = echo.samples[:mic_len]
        else:
            echo_samples = np.zeros(mic_len, dtype=np.float64)
            echo_samples[: echo.num_samples] = echo.samples

        mixed = mic_input.samples + echo_samples
        return AudioBuffer(samples=mixed, sample_rate=mic_input.sample_rate)
