"""OpenAI Realtime API WebSocket client.

Implements a session-based interface for streaming audio to the
OpenAI Realtime API and collecting responses.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Any

import numpy as np

from backend.app.audio.types import AudioBuffer
from backend.app.config import settings


class OpenAIRealtimeSession:
    """Async context manager for an OpenAI Realtime API session.

    Usage:
        async with OpenAIRealtimeSession(config) as session:
            await session.send_audio(chunk, sample_rate)
            await session.signal_turn_end()
            response = await session.receive_response()
    """

    def __init__(self, config: dict[str, Any]):
        self._config = config
        self._ws = None
        self._response_text = ""
        self._response_audio_chunks: list[bytes] = []
        self._first_byte_time: float | None = None
        self._start_time: float = 0
        self._response_done = asyncio.Event()
        self._listener_task: asyncio.Task | None = None

    async def __aenter__(self):
        import websockets

        model = self._config.get("model", "gpt-4o-realtime-preview")
        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError("OpenAI API key required for Realtime API")

        url = f"wss://api.openai.com/v1/realtime?model={model}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        self._ws = await websockets.connect(url, additional_headers=headers)
        self._start_time = time.monotonic()

        # Send session configuration
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": self._config.get("modalities", ["text", "audio"]),
                "instructions": self._config.get("instructions", ""),
                "voice": self._config.get("voice", "alloy"),
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "temperature": self._config.get("temperature", 0.8),
            },
        }

        # Turn detection
        td = self._config.get("turn_detection", "server_vad")
        if td == "server_vad":
            session_update["session"]["turn_detection"] = {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500,
            }
        else:
            session_update["session"]["turn_detection"] = None

        await self._ws.send(json.dumps(session_update))

        # Start listener
        self._listener_task = asyncio.create_task(self._listen())

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()

    async def send_audio(self, samples: np.ndarray, sample_rate: int = 16000):
        """Send an audio chunk to the session.

        Converts float64 [-1, 1] to PCM16 little-endian bytes at 24kHz.
        """
        if self._ws is None:
            raise RuntimeError("Session not connected")

        # Resample to 24kHz if needed (Realtime API expects 24kHz)
        if sample_rate != 24000:
            from scipy.signal import resample
            num_samples_24k = int(len(samples) * 24000 / sample_rate)
            samples = resample(samples, num_samples_24k)

        # Convert to PCM16
        pcm16 = (samples * 32767).astype(np.int16)
        audio_bytes = pcm16.tobytes()
        audio_b64 = base64.b64encode(audio_bytes).decode()

        msg = {
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }
        await self._ws.send(json.dumps(msg))

    async def signal_turn_end(self):
        """Signal that the user has finished speaking."""
        if self._ws is None:
            return

        td = self._config.get("turn_detection", "server_vad")
        if td == "manual":
            await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            await self._ws.send(json.dumps({"type": "response.create"}))

    async def receive_response(self, timeout: float = 30.0) -> dict[str, Any]:
        """Wait for and collect the complete response."""
        try:
            await asyncio.wait_for(self._response_done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        first_byte_ms = 0
        if self._first_byte_time is not None:
            first_byte_ms = (self._first_byte_time - self._start_time) * 1000

        # Convert audio chunks to AudioBuffer
        response_audio = None
        if self._response_audio_chunks:
            all_bytes = b"".join(self._response_audio_chunks)
            pcm16 = np.frombuffer(all_bytes, dtype=np.int16)
            float_samples = pcm16.astype(np.float64) / 32767.0
            response_audio = AudioBuffer(samples=float_samples, sample_rate=24000)

        return {
            "transcript": self._response_text,
            "audio": response_audio,
            "first_byte_ms": first_byte_ms,
        }

    async def _listen(self):
        """Background task to receive messages from the WebSocket."""
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                event_type = msg.get("type", "")

                if event_type == "response.audio.delta":
                    audio_b64 = msg.get("delta", "")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        if self._first_byte_time is None:
                            self._first_byte_time = time.monotonic()
                        self._response_audio_chunks.append(audio_bytes)

                elif event_type == "response.audio_transcript.delta":
                    self._response_text += msg.get("delta", "")
                    if self._first_byte_time is None:
                        self._first_byte_time = time.monotonic()

                elif event_type == "response.done":
                    self._response_done.set()

                elif event_type == "error":
                    error = msg.get("error", {})
                    raise RuntimeError(f"Realtime API error: {error.get('message', 'unknown')}")

        except asyncio.CancelledError:
            pass
