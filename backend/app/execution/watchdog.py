"""Server-wide health watchdog with self-healing capabilities.

Runs as a dedicated service, monitoring:
- Ollama health (model loaded, response time, GPU VRAM)
- Docker container status (backend, worker, db, redis)
- System resources (CPU, RAM, disk, GPU temperature)
- Worker progress (stall detection, error budget)
- Stuck/zombie runs in the database

Self-healing actions:
- Restart Ollama if unresponsive
- Cancel zombie runs stuck in 'running' status
- Skip backends with too many consecutive failures
- Alert on resource exhaustion (disk, RAM, GPU temp)

Diagnostics published to Redis for the Run Monitor UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("watchdog")
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHECK_INTERVAL_S = 30          # How often to run checks
STALL_THRESHOLD_S = 300        # 5 minutes with no progress = stall
HEARTBEAT_TIMEOUT_S = 120      # 2 minutes with no heartbeat = worker dead
CONSECUTIVE_ERROR_LIMIT = 10   # Skip backend after N consecutive failures
OLLAMA_TIMEOUT_S = 10          # Ollama health check timeout
MAX_CPU_PERCENT = 95           # Alert threshold
MAX_RAM_PERCENT = 90           # Alert threshold
MAX_DISK_PERCENT = 90          # Alert threshold
MAX_GPU_TEMP_C = 85            # Alert threshold
ZOMBIE_RUN_THRESHOLD_S = 600   # Run stuck in 'running' > 10 min with no progress


class WatchdogDiagnostic:
    """A single diagnostic finding."""

    def __init__(
        self,
        level: str,      # info, warn, error, critical
        component: str,  # ollama, worker, docker, system, run
        message: str,
        action_taken: str | None = None,
        details: dict | None = None,
    ):
        self.level = level
        self.component = component
        self.message = message
        self.action_taken = action_taken
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = {
            "level": self.level,
            "component": self.component,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        if self.action_taken:
            d["action_taken"] = self.action_taken
        if self.details:
            d["details"] = self.details
        return d


class Watchdog:
    """Server-wide health monitor and self-healing agent."""

    def __init__(self, redis_url: str, ollama_url: str, db_url: str):
        self._redis_url = redis_url
        self._ollama_url = ollama_url.rstrip("/")
        self._db_url = db_url
        self._redis = None
        self._last_completed_cases: dict[str, int] = {}  # run_id -> last known count
        self._last_progress_time: dict[str, float] = {}  # run_id -> monotonic time of last progress
        self._diagnostics: list[WatchdogDiagnostic] = []
        self._cycle_count = 0

    async def _get_redis(self):
        if self._redis is None:
            from arq.connections import create_pool, RedisSettings
            self._redis = await create_pool(RedisSettings.from_dsn(self._redis_url))
        return self._redis

    def _diag(self, level: str, component: str, message: str,
              action_taken: str | None = None, **details):
        """Record a diagnostic finding."""
        d = WatchdogDiagnostic(level, component, message, action_taken, details)
        self._diagnostics.append(d)
        log_level = {"warn": "warning", "critical": "error"}.get(level, level)
        log_fn = getattr(logger, log_level)
        prefix = f"[{component}]"
        if action_taken:
            log_fn(f"{prefix} {message} -> {action_taken}")
        else:
            log_fn(f"{prefix} {message}")

    # -----------------------------------------------------------------------
    # Individual health checks
    # -----------------------------------------------------------------------

    async def check_ollama(self) -> bool:
        """Check Ollama is responsive and has models loaded."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_S) as client:
                # Basic health
                t0 = time.monotonic()
                resp = await client.get(f"{self._ollama_url}/api/tags")
                latency = (time.monotonic() - t0) * 1000

                if resp.status_code != 200:
                    self._diag("error", "ollama", f"Unhealthy: HTTP {resp.status_code}",
                               action_taken="attempting restart")
                    await self._restart_ollama()
                    return False

                if latency > 5000:
                    self._diag("warn", "ollama", f"Slow response: {latency:.0f}ms")

                # Check loaded models
                ps_resp = await client.get(f"{self._ollama_url}/api/ps")
                if ps_resp.status_code == 200:
                    data = ps_resp.json()
                    models = data.get("models", [])
                    if models:
                        names = [m["name"] for m in models]
                        total_vram = sum(m.get("size_vram", 0) for m in models)
                        self._diag("info", "ollama",
                                   f"OK: {', '.join(names)} loaded, "
                                   f"VRAM: {total_vram / 1e9:.1f}GB, "
                                   f"latency: {latency:.0f}ms")
                    else:
                        self._diag("warn", "ollama", "No models loaded — idle or cold start")
                return True

        except httpx.ConnectError:
            self._diag("critical", "ollama", "Connection refused — service down",
                        action_taken="attempting restart")
            await self._restart_ollama()
            return False
        except httpx.ReadTimeout:
            self._diag("error", "ollama", "Timeout — possibly hung on inference",
                        action_taken="attempting restart")
            await self._restart_ollama()
            return False
        except Exception as e:
            self._diag("error", "ollama", f"Health check failed: {type(e).__name__}: {e}")
            return False

    async def _restart_ollama(self):
        """Attempt to restart Ollama via systemctl."""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "ollama"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                self._diag("info", "ollama", "Restart succeeded", details={"stdout": result.stdout.strip()})
                await asyncio.sleep(5)  # Give it time to start
            else:
                self._diag("error", "ollama", f"Restart failed: {result.stderr.strip()}")
        except FileNotFoundError:
            # Not running on host with systemctl (inside Docker)
            self._diag("warn", "ollama", "Cannot restart — no systemctl access (running in container?)")
        except Exception as e:
            self._diag("error", "ollama", f"Restart attempt error: {e}")

    async def check_worker(self):
        """Check worker heartbeat and progress rate."""
        try:
            redis = await self._get_redis()

            # Check heartbeat
            heartbeat_raw = await redis.get("worker:heartbeat")
            if heartbeat_raw:
                hb_str = heartbeat_raw.decode() if isinstance(heartbeat_raw, bytes) else heartbeat_raw
                hb_time = datetime.fromisoformat(hb_str)
                age_s = (datetime.now(timezone.utc) - hb_time).total_seconds()

                if age_s > HEARTBEAT_TIMEOUT_S:
                    self._diag("error", "worker",
                               f"Heartbeat stale ({age_s:.0f}s old — threshold {HEARTBEAT_TIMEOUT_S}s)",
                               action_taken="flagged for review")
                elif age_s > 60:
                    self._diag("warn", "worker", f"Heartbeat aging: {age_s:.0f}s")
                else:
                    self._diag("info", "worker", f"Heartbeat OK ({age_s:.0f}s ago)")
            else:
                self._diag("info", "worker", "No heartbeat — worker idle or not started")

            # Check activity
            activity_raw = await redis.get("worker:activity")
            if activity_raw:
                activity = json.loads(activity_raw.decode() if isinstance(activity_raw, bytes) else activity_raw)
                status = activity.get("status", "unknown")
                run_id = activity.get("run_id")
                rate = activity.get("cases_per_min", 0)

                if status == "processing" and rate == 0 and run_id:
                    self._diag("warn", "worker",
                               f"Processing run {run_id[:8]} but rate is 0 — possible stall")

            # Check error budget
            budget_raw = await redis.get("worker:error_budget")
            if budget_raw:
                budget = json.loads(budget_raw.decode() if isinstance(budget_raw, bytes) else budget_raw)
                for backend, stats in budget.items():
                    consecutive = stats.get("consecutive", 0)
                    total = stats.get("total", 0)
                    errors = stats.get("errors", 0)
                    error_rate = errors / total * 100 if total > 0 else 0

                    if consecutive >= CONSECUTIVE_ERROR_LIMIT:
                        self._diag("critical", "worker",
                                   f"Backend {backend}: {consecutive} consecutive failures",
                                   action_taken="backend should be skipped",
                                   consecutive=consecutive, error_rate=f"{error_rate:.1f}%")
                    elif consecutive >= 5:
                        self._diag("warn", "worker",
                                   f"Backend {backend}: {consecutive} consecutive failures",
                                   consecutive=consecutive, error_rate=f"{error_rate:.1f}%")
                    elif total > 0 and error_rate > 20:
                        self._diag("warn", "worker",
                                   f"Backend {backend}: {error_rate:.1f}% error rate ({errors}/{total})")

        except Exception as e:
            self._diag("error", "worker", f"Health check failed: {e}")

    async def check_system(self):
        """Check CPU, RAM, disk, GPU temperature."""
        try:
            import psutil

            # CPU
            cpu = psutil.cpu_percent(interval=0.5)
            if cpu > MAX_CPU_PERCENT:
                self._diag("warn", "system", f"CPU high: {cpu}%")

            # RAM
            mem = psutil.virtual_memory()
            if mem.percent > MAX_RAM_PERCENT:
                self._diag("warn", "system",
                           f"RAM high: {mem.percent}% ({mem.used / 1e9:.1f}GB / {mem.total / 1e9:.1f}GB)",
                           action_taken="flagged — possible OOM risk")

            # Disk
            disk = psutil.disk_usage("/")
            if disk.percent > MAX_DISK_PERCENT:
                self._diag("error", "system",
                           f"Disk nearly full: {disk.percent}% used",
                           action_taken="flagged — may fail to save audio/results")

            # GPU temperature (AMD via sysfs)
            import glob as _glob
            temp_files = _glob.glob("/sys/class/drm/card[0-9]*/device/hwmon/hwmon*/temp1_input")
            for tf in temp_files:
                try:
                    with open(tf) as f:
                        temp_c = int(f.read().strip()) // 1000
                    if temp_c > MAX_GPU_TEMP_C:
                        self._diag("error", "system",
                                   f"GPU temperature critical: {temp_c}°C (threshold {MAX_GPU_TEMP_C}°C)",
                                   action_taken="flagged — throttling likely")
                    elif temp_c > 75:
                        self._diag("warn", "system", f"GPU temperature elevated: {temp_c}°C")
                except Exception:
                    pass

            # Log summary on every 10th cycle
            if self._cycle_count % 10 == 0:
                self._diag("info", "system",
                           f"CPU {cpu:.0f}% | RAM {mem.percent}% | Disk {disk.percent}%")

        except ImportError:
            self._diag("warn", "system", "psutil not available — skipping system checks")
        except Exception as e:
            self._diag("error", "system", f"System check failed: {e}")

    async def check_docker(self):
        """Check Docker container health (only when running on host)."""
        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                capture_output=True, text=True, timeout=10,
                cwd="/home/ryan/server/apps/audio-llm-test",
            )
            if result.returncode != 0:
                # Probably running inside Docker, skip
                return

            # Parse container statuses
            containers = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    try:
                        containers.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            for c in containers:
                name = c.get("Name", c.get("Service", "?"))
                state = c.get("State", c.get("Status", "unknown"))
                health = c.get("Health", "")

                if "unhealthy" in str(health).lower() or "restarting" in str(state).lower():
                    self._diag("error", "docker",
                               f"Container {name}: {state} {health}",
                               action_taken="flagged for review")
                elif "exited" in str(state).lower() or "dead" in str(state).lower():
                    self._diag("critical", "docker",
                               f"Container {name} is DOWN: {state}",
                               action_taken="attempting restart")
                    subprocess.run(
                        ["docker", "compose", "restart", name.split("-")[-2]],  # service name
                        capture_output=True, timeout=30,
                        cwd="/home/ryan/server/apps/audio-llm-test",
                    )

        except FileNotFoundError:
            pass  # docker not available (inside container)
        except Exception as e:
            self._diag("warn", "docker", f"Docker check failed: {e}")

    async def check_stuck_runs(self):
        """Detect and cancel zombie runs stuck in 'running' status."""
        try:
            from sqlalchemy import select, text
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker

            engine = create_async_engine(self._db_url, pool_pre_ping=True)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with async_session() as session:
                # Find runs stuck in 'running'
                result = await session.execute(
                    text("""
                        SELECT id, total_cases, completed_cases, updated_at, started_at
                        FROM test_runs
                        WHERE status = 'running'
                    """)
                )
                running_runs = result.fetchall()

                for run in running_runs:
                    run_id = str(run[0])
                    total = run[1]
                    completed = run[2]
                    updated_at = run[3]
                    started_at = run[4]

                    # Track progress
                    prev_completed = self._last_completed_cases.get(run_id, -1)
                    now = time.monotonic()

                    if completed != prev_completed:
                        # Progress was made
                        self._last_completed_cases[run_id] = completed
                        self._last_progress_time[run_id] = now
                    elif run_id not in self._last_progress_time:
                        self._last_progress_time[run_id] = now

                    stall_duration = now - self._last_progress_time.get(run_id, now)

                    if stall_duration > ZOMBIE_RUN_THRESHOLD_S:
                        self._diag("critical", "run",
                                   f"Run {run_id[:8]} stalled: {completed}/{total} cases, "
                                   f"no progress for {stall_duration:.0f}s",
                                   action_taken="cancelling zombie run",
                                   run_id=run_id, completed=completed, total=total)
                        await session.execute(
                            text("UPDATE test_runs SET status = 'cancelled', "
                                 "error_message = 'Cancelled by watchdog: stalled with no progress' "
                                 "WHERE id = :rid"),
                            {"rid": run[0]},
                        )
                        await session.commit()
                        # Clean up tracking
                        self._last_completed_cases.pop(run_id, None)
                        self._last_progress_time.pop(run_id, None)
                    elif stall_duration > STALL_THRESHOLD_S:
                        self._diag("warn", "run",
                                   f"Run {run_id[:8]} possibly stalling: {completed}/{total}, "
                                   f"no progress for {stall_duration:.0f}s")
                    elif self._cycle_count % 10 == 0:
                        pct = (completed / total * 100) if total > 0 else 0
                        self._diag("info", "run",
                                   f"Run {run_id[:8]}: {completed}/{total} ({pct:.1f}%)")

                # Clean up tracking for runs that are no longer running
                active_ids = {str(r[0]) for r in running_runs}
                for rid in list(self._last_completed_cases.keys()):
                    if rid not in active_ids:
                        self._last_completed_cases.pop(rid, None)
                        self._last_progress_time.pop(rid, None)

            await engine.dispose()

        except Exception as e:
            self._diag("error", "run", f"Stuck run check failed: {e}")

    # -----------------------------------------------------------------------
    # Publish diagnostics
    # -----------------------------------------------------------------------

    async def _publish_diagnostics(self):
        """Push diagnostic findings to Redis for the monitoring UI."""
        if not self._diagnostics:
            return

        try:
            redis = await self._get_redis()

            # Store the full report
            report = {
                "cycle": self._cycle_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "findings": [d.to_dict() for d in self._diagnostics],
                "summary": {
                    "info": sum(1 for d in self._diagnostics if d.level == "info"),
                    "warn": sum(1 for d in self._diagnostics if d.level == "warn"),
                    "error": sum(1 for d in self._diagnostics if d.level == "error"),
                    "critical": sum(1 for d in self._diagnostics if d.level == "critical"),
                },
            }
            await redis.set("watchdog:report", json.dumps(report), ex=300)  # 5 min TTL

            # Push warnings/errors to worker:log for the monitoring UI
            for d in self._diagnostics:
                if d.level in ("warn", "error", "critical"):
                    log_entry = {
                        "level": d.level,
                        "message": f"[watchdog:{d.component}] {d.message}"
                                   + (f" -> {d.action_taken}" if d.action_taken else ""),
                        "timestamp": d.timestamp,
                    }
                    await redis.lpush("worker:log", json.dumps(log_entry))

            # Trim worker log
            await redis.ltrim("worker:log", 0, 199)

            # Store historical reports (keep last 100)
            await redis.lpush("watchdog:history", json.dumps(report))
            await redis.ltrim("watchdog:history", 0, 99)

        except Exception as e:
            logger.error(f"Failed to publish diagnostics: {e}")

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------

    async def run_once(self):
        """Run all health checks once."""
        self._diagnostics = []
        self._cycle_count += 1

        await self.check_ollama()
        await self.check_worker()
        await self.check_system()
        await self.check_docker()
        await self.check_stuck_runs()

        await self._publish_diagnostics()

        # Log summary
        warns = sum(1 for d in self._diagnostics if d.level == "warn")
        errors = sum(1 for d in self._diagnostics if d.level in ("error", "critical"))
        if errors:
            logger.error(f"Cycle {self._cycle_count}: {errors} errors, {warns} warnings")
        elif warns:
            logger.warning(f"Cycle {self._cycle_count}: {warns} warnings")

    async def run_forever(self):
        """Main watchdog loop — runs checks every CHECK_INTERVAL_S."""
        logger.info(
            f"Watchdog starting: interval={CHECK_INTERVAL_S}s, "
            f"stall_threshold={STALL_THRESHOLD_S}s, "
            f"ollama={self._ollama_url}"
        )

        while True:
            try:
                await self.run_once()
            except Exception as e:
                logger.exception(f"Watchdog cycle failed: {e}")

            await asyncio.sleep(CHECK_INTERVAL_S)


# ---------------------------------------------------------------------------
# Entry point — run as standalone service
# ---------------------------------------------------------------------------

async def main():
    """Start the watchdog as a standalone async service."""
    from backend.app.config import settings

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    watchdog = Watchdog(
        redis_url=settings.redis_url,
        ollama_url=settings.ollama_base_url,
        db_url=settings.database_url,
    )
    await watchdog.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
