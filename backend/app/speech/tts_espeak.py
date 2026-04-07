"""eSpeak/system TTS provider — system-level speech synthesis (offline, free).

On macOS: uses the `say` command (NSSpeechSynthesizer) which outputs AIFF.
On Linux: uses pyttsx3 → eSpeak.
On Windows: uses pyttsx3 → SAPI5.

Quality is low (robotic) but works offline with zero setup.
"""

from __future__ import annotations

import platform
import subprocess
import tempfile
import wave

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

_IS_MACOS = platform.system() == "Darwin"


class ESpeakTTSProvider:
    """TTS provider using the system speech engine."""

    provider_name: str = "espeak"

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text, voice_id)

    def _synthesize_sync(self, text: str, voice_id: str) -> AudioBuffer:
        if _IS_MACOS:
            return self._synthesize_macos(text, voice_id)
        return self._synthesize_pyttsx3(text, voice_id)

    def _synthesize_macos(self, text: str, voice_id: str) -> AudioBuffer:
        """Use macOS `say` command → AIFF → convert to float samples."""
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
            aiff_path = f.name

        # `say` voice names: the voice_id from list_voices is the full
        # system id, but `say -v` wants just the short name.
        voice_name = voice_id.split(".")[-1] if "." in voice_id else voice_id

        try:
            subprocess.run(
                ["say", "-v", voice_name, "-o", aiff_path, "--", text],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise RuntimeError("macOS `say` command not found")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"`say` failed: {e.stderr.decode()}")

        # Convert AIFF to WAV using afconvert (ships with macOS)
        wav_path = aiff_path.replace(".aiff", ".wav")
        try:
            subprocess.run(
                [
                    "afconvert",
                    "-f", "WAVE",
                    "-d", "LEI16@22050",
                    aiff_path,
                    wav_path,
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except Exception as e:
            raise RuntimeError(f"afconvert failed: {e}")
        finally:
            import os
            os.unlink(aiff_path)

        try:
            with wave.open(wav_path, "rb") as wav:
                sample_rate = wav.getframerate()
                n_channels = wav.getnchannels()
                raw = wav.readframes(wav.getnframes())
        finally:
            import os
            os.unlink(wav_path)

        samples_int16 = np.frombuffer(raw, dtype=np.int16)
        if n_channels == 2:
            samples_int16 = samples_int16.reshape(-1, 2).mean(axis=1).astype(np.int16)
        samples_f64 = samples_int16.astype(np.float64) / 32768.0
        return AudioBuffer(samples=samples_f64, sample_rate=sample_rate)

    def _synthesize_pyttsx3(self, text: str, voice_id: str) -> AudioBuffer:
        """Use pyttsx3 (Linux/Windows) which outputs proper WAV."""
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("voice", voice_id)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        engine.save_to_file(text, wav_path)
        engine.runAndWait()

        try:
            with wave.open(wav_path, "rb") as wav:
                sample_rate = wav.getframerate()
                n_channels = wav.getnchannels()
                raw = wav.readframes(wav.getnframes())
        finally:
            import os
            os.unlink(wav_path)

        samples_int16 = np.frombuffer(raw, dtype=np.int16)
        if n_channels == 2:
            samples_int16 = samples_int16.reshape(-1, 2).mean(axis=1).astype(np.int16)
        samples_f64 = samples_int16.astype(np.float64) / 32768.0
        return AudioBuffer(samples=samples_f64, sample_rate=sample_rate)

    async def list_voices(self) -> list[VoiceInfo]:
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._list_voices_sync)

    def _list_voices_sync(self) -> list[VoiceInfo]:
        if _IS_MACOS:
            return self._list_voices_macos()
        return self._list_voices_pyttsx3()

    def _list_voices_macos(self) -> list[VoiceInfo]:
        """Parse `say -v ?` output."""
        try:
            result = subprocess.run(
                ["say", "-v", "?"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
        except Exception:
            return []

        voices = []
        for line in result.stdout.strip().splitlines():
            # Format: "Alex                en_US    # Most people ..."
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[0]
            lang_code = parts[1] if len(parts) > 1 else "en"
            lang = lang_code.split("_")[0] if "_" in lang_code else lang_code

            voices.append(
                VoiceInfo(
                    provider=self.provider_name,
                    voice_id=name,
                    name=name,
                    gender="neutral",
                    age_group="adult",
                    accent="system",
                    language=lang,
                )
            )

        return voices

    def _list_voices_pyttsx3(self) -> list[VoiceInfo]:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            system_voices = engine.getProperty("voices")
        except Exception:
            return []

        voices = []
        for v in system_voices:
            lang = "en"
            if hasattr(v, "languages") and v.languages:
                raw_lang = v.languages[0]
                if isinstance(raw_lang, bytes):
                    raw_lang = raw_lang.decode("utf-8", errors="ignore")
                lang = raw_lang.strip("\x00").split("_")[0] if raw_lang else "en"

            name_lower = (v.name or "").lower()
            gender = "neutral"
            if any(w in name_lower for w in ("female", "woman", "girl")):
                gender = "female"
            elif any(w in name_lower for w in ("male", "man", "boy")):
                gender = "male"

            voices.append(
                VoiceInfo(
                    provider=self.provider_name,
                    voice_id=v.id,
                    name=v.name or v.id,
                    gender=gender,
                    age_group="adult",
                    accent="system",
                    language=lang,
                )
            )

        return voices
