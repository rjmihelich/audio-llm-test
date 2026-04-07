"""Pipeline Studio configuration — extends the parent project's settings."""

import sys
from pathlib import Path

# Add project root to sys.path so we can import from backend.app.*
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.config import settings  # noqa: E402, F401
