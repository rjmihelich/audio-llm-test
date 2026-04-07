from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    model_config = {"env_prefix": "ALT_", "env_file": ".env"}

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/audio_llm_test"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Storage
    audio_storage_path: Path = Path("storage/audio")
    results_storage_path: Path = Path("storage/results")

    # API Keys (optional, loaded from env)
    openai_api_key: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    deepgram_api_key: str = ""

    # Azure Speech (for expressive TTS styles: whispering, shouting, etc.)
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Audio defaults
    default_sample_rate: int = 16000

    # Default providers (low-latency voice assistant stack)
    default_llm_backend: str = "anthropic:claude-haiku-4-5-20251001"
    default_stt_backend: str = "deepgram:nova-2"
    default_tts_provider: str = "elevenlabs"

    # Execution
    max_concurrent_workers: int = 50
    checkpoint_interval: int = 100


settings = Settings()
