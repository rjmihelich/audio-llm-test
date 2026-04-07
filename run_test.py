#!/usr/bin/env python3
"""Directly run the test suite task, bypassing arq."""
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

from backend.app.execution.worker import run_test_suite


async def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not run_id:
        # Get latest pending run from DB
        from sqlalchemy import text
        from backend.app.models.base import async_session

        async with async_session() as s:
            r = await s.execute(
                text("SELECT id FROM test_runs WHERE status='pending' ORDER BY created_at DESC LIMIT 1")
            )
            row = r.fetchone()
            if row:
                run_id = str(row[0])
            else:
                print("No pending runs found", file=sys.stderr)
                return

    print(f"Running test: {run_id}", file=sys.stderr)
    await run_test_suite({}, run_id)
    print("Done!", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
