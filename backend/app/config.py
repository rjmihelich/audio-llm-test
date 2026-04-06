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

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Audio defaults
    default_sample_rate: int = 16000

    # Execution
    max_concurrent_workers: int = 50
    checkpoint_interval: int = 100


settings = Settings()
