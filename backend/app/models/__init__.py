"""Database models package — import all models so Alembic can discover them."""

from backend.app.models.base import Base, async_session, engine, get_session
from backend.app.models.speech import (
    CorpusEntry,
    SpeechSample,
    Voice,
)
from backend.app.models.test import (
    SweepConfig,
    TestCase,
    TestSuite,
)
from backend.app.models.run import (
    TestResult,
    TestRun,
)

__all__ = [
    "Base",
    "async_session",
    "engine",
    "get_session",
    # Speech
    "Voice",
    "CorpusEntry",
    "SpeechSample",
    # Test config
    "TestSuite",
    "SweepConfig",
    "TestCase",
    # Execution
    "TestRun",
    "TestResult",
]
