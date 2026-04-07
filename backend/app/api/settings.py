"""API settings management — read/update API keys and service config at runtime."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings

router = APIRouter()

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _mask(key: str) -> str | None:
    """Return masked version of a key, or None if empty."""
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


# ---------------------------------------------------------------------------
# Response / request schemas
# ---------------------------------------------------------------------------

class SettingsResponse(BaseModel):
    openai_api_key: str | None = None
    google_api_key: str | None = None
    anthropic_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    deepgram_api_key: str | None = None
    azure_speech_key: str | None = None
    azure_speech_region: str = "eastus"
    ollama_base_url: str = ""
    default_sample_rate: int = 16000
    max_concurrent_workers: int = 50
    default_llm_backend: str = ""
    default_stt_backend: str = ""
    default_tts_provider: str = ""


class UpdateKeysRequest(BaseModel):
    openai_api_key: str | None = None
    google_api_key: str | None = None
    anthropic_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    deepgram_api_key: str | None = None
    azure_speech_key: str | None = None
    azure_speech_region: str | None = None
    ollama_base_url: str | None = None
    default_llm_backend: str | None = None
    default_stt_backend: str | None = None
    default_tts_provider: str | None = None


class KeyValidationResponse(BaseModel):
    provider: str
    valid: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# .env persistence
# ---------------------------------------------------------------------------

_KEY_TO_ENV = {
    "openai_api_key": "ALT_OPENAI_API_KEY",
    "google_api_key": "ALT_GOOGLE_API_KEY",
    "anthropic_api_key": "ALT_ANTHROPIC_API_KEY",
    "elevenlabs_api_key": "ALT_ELEVENLABS_API_KEY",
    "deepgram_api_key": "ALT_DEEPGRAM_API_KEY",
    "azure_speech_key": "ALT_AZURE_SPEECH_KEY",
    "azure_speech_region": "ALT_AZURE_SPEECH_REGION",
    "ollama_base_url": "ALT_OLLAMA_BASE_URL",
    "default_llm_backend": "ALT_DEFAULT_LLM_BACKEND",
    "default_stt_backend": "ALT_DEFAULT_STT_BACKEND",
    "default_tts_provider": "ALT_DEFAULT_TTS_PROVIDER",
}


def _persist_to_env(updates: dict[str, str]) -> None:
    """Write updated keys into the .env file so they survive restarts."""
    lines: list[str] = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text().splitlines()

    env_updates = {_KEY_TO_ENV[k]: v for k, v in updates.items() if k in _KEY_TO_ENV}

    # Update existing lines in-place
    updated_keys: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            env_key = stripped.split("=", 1)[0].strip()
            if env_key in env_updates:
                lines[i] = f"{env_key}={env_updates[env_key]}"
                updated_keys.add(env_key)

    # Append any new keys not already in the file
    for env_key, value in env_updates.items():
        if env_key not in updated_keys:
            lines.append(f"{env_key}={value}")

    _ENV_FILE.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _is_valid_key(key: str) -> bool:
    """Check if a key looks like a real API key (not a placeholder)."""
    if not key or len(key) < 10:
        return False
    # Common placeholders
    if key in ("sk-...", "sk-ant-...", "AI...", "xi-...", "..."):
        return False
    if key.startswith("sk-...") or key.startswith("..."):
        return False
    return True


class KeyStatusResponse(BaseModel):
    openai: bool = False
    google: bool = False
    anthropic: bool = False
    elevenlabs: bool = False
    deepgram: bool = False
    azure: bool = False
    ollama: bool = True  # Always available if URL is set


@router.get("/key-status", response_model=KeyStatusResponse)
async def get_key_status():
    """Return which API keys are valid (not placeholders)."""
    return KeyStatusResponse(
        openai=_is_valid_key(settings.openai_api_key),
        google=_is_valid_key(settings.google_api_key),
        anthropic=_is_valid_key(settings.anthropic_api_key),
        elevenlabs=_is_valid_key(settings.elevenlabs_api_key),
        deepgram=_is_valid_key(settings.deepgram_api_key),
        azure=_is_valid_key(settings.azure_speech_key),
        ollama=bool(settings.ollama_base_url),
    )


@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Return current settings with API keys masked."""
    return SettingsResponse(
        openai_api_key=_mask(settings.openai_api_key),
        google_api_key=_mask(settings.google_api_key),
        anthropic_api_key=_mask(settings.anthropic_api_key),
        elevenlabs_api_key=_mask(settings.elevenlabs_api_key),
        deepgram_api_key=_mask(settings.deepgram_api_key),
        azure_speech_key=_mask(settings.azure_speech_key),
        azure_speech_region=settings.azure_speech_region,
        ollama_base_url=settings.ollama_base_url,
        default_sample_rate=settings.default_sample_rate,
        max_concurrent_workers=settings.max_concurrent_workers,
        default_llm_backend=settings.default_llm_backend,
        default_stt_backend=settings.default_stt_backend,
        default_tts_provider=settings.default_tts_provider,
    )


@router.patch("", response_model=dict)
async def update_settings(req: UpdateKeysRequest):
    """Update API keys at runtime and persist to .env file."""
    updates: dict[str, str] = {}

    if req.openai_api_key is not None:
        settings.openai_api_key = req.openai_api_key
        updates["openai_api_key"] = req.openai_api_key
    if req.google_api_key is not None:
        settings.google_api_key = req.google_api_key
        updates["google_api_key"] = req.google_api_key
    if req.anthropic_api_key is not None:
        settings.anthropic_api_key = req.anthropic_api_key
        updates["anthropic_api_key"] = req.anthropic_api_key
    if req.elevenlabs_api_key is not None:
        settings.elevenlabs_api_key = req.elevenlabs_api_key
        updates["elevenlabs_api_key"] = req.elevenlabs_api_key
    if req.deepgram_api_key is not None:
        settings.deepgram_api_key = req.deepgram_api_key
        updates["deepgram_api_key"] = req.deepgram_api_key
    if req.azure_speech_key is not None:
        settings.azure_speech_key = req.azure_speech_key
        updates["azure_speech_key"] = req.azure_speech_key
    if req.azure_speech_region is not None:
        settings.azure_speech_region = req.azure_speech_region
        updates["azure_speech_region"] = req.azure_speech_region
    if req.ollama_base_url is not None:
        settings.ollama_base_url = req.ollama_base_url
        updates["ollama_base_url"] = req.ollama_base_url
    if req.default_llm_backend is not None:
        settings.default_llm_backend = req.default_llm_backend
        updates["default_llm_backend"] = req.default_llm_backend
    if req.default_stt_backend is not None:
        settings.default_stt_backend = req.default_stt_backend
        updates["default_stt_backend"] = req.default_stt_backend
    if req.default_tts_provider is not None:
        settings.default_tts_provider = req.default_tts_provider
        updates["default_tts_provider"] = req.default_tts_provider

    if updates:
        _persist_to_env(updates)

    return {"status": "updated", "keys_changed": list(updates.keys())}


# ---------------------------------------------------------------------------
# LLM Connection Test
# ---------------------------------------------------------------------------

class TestLLMRequest(BaseModel):
    backend: str  # e.g. "ollama:mistral", "openai:gpt-4o-mini"
    prompt: str = "Say hello in one sentence."


class TestLLMResponse(BaseModel):
    success: bool
    response: str | None = None
    error: str | None = None
    latency_ms: float | None = None


@router.post("/test-llm", response_model=TestLLMResponse)
async def test_llm(req: TestLLMRequest):
    """Send a quick test prompt to an LLM backend to verify connectivity."""
    import asyncio
    import time

    try:
        prefix, _, model = req.backend.partition(":")

        start = time.time()

        if prefix == "ollama":
            import httpx
            url = f"{settings.ollama_base_url}/api/generate"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json={
                    "model": model or "mistral",
                    "prompt": req.prompt,
                    "stream": False,
                })
                resp.raise_for_status()
                data = resp.json()
                answer = data.get("response", "")

        elif prefix == "openai":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            resp = await client.chat.completions.create(
                model=model or "gpt-4o-mini",
                messages=[{"role": "user", "content": req.prompt}],
                max_tokens=100,
            )
            answer = resp.choices[0].message.content or ""

        elif prefix == "anthropic":
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            resp = await client.messages.create(
                model=model or "claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": req.prompt}],
            )
            answer = resp.content[0].text if resp.content else ""

        elif prefix == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=settings.google_api_key)
            gm = genai.GenerativeModel(model or "gemini-2.0-flash")
            resp = await asyncio.to_thread(
                lambda: gm.generate_content(req.prompt)
            )
            answer = resp.text or ""

        else:
            return TestLLMResponse(success=False, error=f"Unknown backend: {prefix}")

        latency = (time.time() - start) * 1000
        return TestLLMResponse(success=True, response=answer.strip(), latency_ms=round(latency, 1))

    except Exception as e:
        return TestLLMResponse(success=False, error=f"{type(e).__name__}: {e}")
