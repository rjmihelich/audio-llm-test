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
    ollama_base_url: str = ""
    default_sample_rate: int = 16000
    max_concurrent_workers: int = 50


class UpdateKeysRequest(BaseModel):
    openai_api_key: str | None = None
    google_api_key: str | None = None
    anthropic_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    ollama_base_url: str | None = None


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
    "ollama_base_url": "ALT_OLLAMA_BASE_URL",
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

@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Return current settings with API keys masked."""
    return SettingsResponse(
        openai_api_key=_mask(settings.openai_api_key),
        google_api_key=_mask(settings.google_api_key),
        anthropic_api_key=_mask(settings.anthropic_api_key),
        elevenlabs_api_key=_mask(settings.elevenlabs_api_key),
        ollama_base_url=settings.ollama_base_url,
        default_sample_rate=settings.default_sample_rate,
        max_concurrent_workers=settings.max_concurrent_workers,
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
    if req.ollama_base_url is not None:
        settings.ollama_base_url = req.ollama_base_url
        updates["ollama_base_url"] = req.ollama_base_url

    if updates:
        _persist_to_env(updates)

    return {"status": "updated", "keys_changed": list(updates.keys())}
