"""Allow running the watchdog as: python -m backend.app.execution.watchdog"""
import asyncio
from backend.app.execution.watchdog import main

asyncio.run(main())
