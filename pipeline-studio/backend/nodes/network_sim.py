"""Network simulator node executor."""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np

from backend.app.audio.types import AudioBuffer

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_network_sim(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Simulate network conditions: latency, jitter, packet loss.

    Polymorphic: passes through audio or text, applying degradation.
    """
    latency_ms = config.get("latency_ms", 50)
    jitter_ms = config.get("jitter_ms", 10)
    packet_loss_pct = config.get("packet_loss_pct", 0)
    bandwidth_kbps = config.get("bandwidth_kbps", 0)

    # Determine input type
    audio_in = inputs.get("audio_in")
    text_in = inputs.get("text_in")

    if audio_in is not None and isinstance(audio_in, AudioBuffer):
        result_audio = _simulate_audio_network(
            audio_in, latency_ms, jitter_ms, packet_loss_pct, bandwidth_kbps
        )
        # Simulate latency
        actual_latency = max(0, latency_ms + np.random.normal(0, jitter_ms))
        await asyncio.sleep(actual_latency / 1000)
        return {"audio_out": result_audio, "text_out": text_in}

    elif text_in is not None:
        # Text passthrough with latency simulation
        actual_latency = max(0, latency_ms + np.random.normal(0, jitter_ms))
        await asyncio.sleep(actual_latency / 1000)
        return {"text_out": text_in, "audio_out": audio_in}

    else:
        raise ValueError("Network sim: at least one of audio_in or text_in must be connected")


def _simulate_audio_network(
    audio: AudioBuffer,
    latency_ms: float,
    jitter_ms: float,
    packet_loss_pct: float,
    bandwidth_kbps: float,
) -> AudioBuffer:
    """Apply network degradation to audio."""
    samples = audio.samples.copy()

    # Packet loss: zero out random chunks
    if packet_loss_pct > 0:
        chunk_size = int(audio.sample_rate * 0.02)  # 20ms chunks
        num_chunks = len(samples) // chunk_size
        rng = np.random.default_rng()
        for i in range(num_chunks):
            if rng.random() < packet_loss_pct / 100:
                start = i * chunk_size
                end = min(start + chunk_size, len(samples))
                samples[start:end] = 0.0

    # Bandwidth limiting: low-pass filter to simulate compression
    if bandwidth_kbps > 0:
        from scipy.signal import butter, sosfilt
        # Rough approximation: bandwidth maps to max frequency
        max_freq = min(bandwidth_kbps * 50, audio.sample_rate / 2 - 1)  # very rough
        if max_freq > 100:
            sos = butter(4, max_freq, btype='low', fs=audio.sample_rate, output='sos')
            samples = sosfilt(sos, samples)

    return AudioBuffer(samples=samples, sample_rate=audio.sample_rate)
