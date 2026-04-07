"""System health and worker activity monitoring API."""

from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class SystemMetrics(BaseModel):
    """Live system resource metrics."""
    cpu_percent: float
    cpu_count: int
    ram_total_gb: float
    ram_used_gb: float
    ram_percent: float
    gpu: list[dict] | None = None  # name, util%, mem_used, mem_total, temp
    disk_percent: float | None = None
    uptime_s: float | None = None
    hostname: str | None = None
    platform: str | None = None


class WorkerActivity(BaseModel):
    """Current worker activity from Redis."""
    run_id: str | None = None
    status: str = "idle"  # idle, processing, error
    current_case: dict | None = None  # case details being processed
    cases_per_min: float = 0
    last_heartbeat: str | None = None
    recent_errors: list[dict] | None = None
    error_budget: dict | None = None  # per-backend error counts & limits
    worker_log: list[dict] | None = None  # recent log entries


class HealthResponse(BaseModel):
    system: SystemMetrics
    worker: WorkerActivity
    timestamp: str


def _get_system_metrics() -> SystemMetrics:
    """Collect CPU, RAM, GPU, disk metrics."""
    import psutil

    cpu_pct = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # GPU info via nvidia-smi or sysfs (if available)
    gpu_info = _get_gpu_info()

    # Enrich GPU info with Ollama VRAM data (more accurate for AMD)
    gpu_info = _enrich_with_ollama(gpu_info)

    # System uptime
    uptime = time.time() - psutil.boot_time()

    return SystemMetrics(
        cpu_percent=cpu_pct,
        cpu_count=psutil.cpu_count() or 1,
        ram_total_gb=round(mem.total / (1024 ** 3), 1),
        ram_used_gb=round(mem.used / (1024 ** 3), 1),
        ram_percent=mem.percent,
        gpu=gpu_info,
        disk_percent=disk.percent,
        uptime_s=uptime,
        hostname=platform.node(),
        platform=f"{platform.system()} {platform.release()}",
    )


def _enrich_with_ollama(gpu_info: list[dict] | None) -> list[dict] | None:
    """Enrich GPU info with Ollama's VRAM usage (more accurate for AMD GPUs)."""
    try:
        from ..config import settings
        import urllib.request

        ollama_url = getattr(settings, "ollama_base_url", "http://localhost:11434")
        req = urllib.request.Request(f"{ollama_url}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())

        models = data.get("models", [])
        if not models:
            return gpu_info

        # Sum up VRAM usage across loaded models
        total_vram_used = sum(m.get("size_vram", 0) for m in models)
        model_names = [m.get("name", "?") for m in models]
        processor = "GPU" if total_vram_used > 0 else "CPU"

        if gpu_info and len(gpu_info) > 0:
            gpu = gpu_info[0]
            # Use Ollama's VRAM as more accurate source
            if total_vram_used > 0:
                gpu["mem_used_gb"] = round(total_vram_used / (1024 ** 3), 2)
                if gpu.get("mem_total_gb") and gpu["mem_total_gb"] > 0:
                    gpu["mem_percent"] = round(
                        (total_vram_used / (1024 ** 3)) / gpu["mem_total_gb"] * 100, 1
                    )
                gpu["ollama_models"] = model_names
                gpu["processor"] = processor
        elif total_vram_used > 0:
            # No GPU detected by sysfs but Ollama is using VRAM
            gpu_info = [{
                "name": f"GPU (via Ollama)",
                "util_percent": None,
                "mem_used_gb": round(total_vram_used / (1024 ** 3), 2),
                "mem_total_gb": None,
                "mem_percent": None,
                "temperature_c": None,
                "ollama_models": model_names,
                "processor": processor,
            }]

        return gpu_info
    except Exception:
        return gpu_info


def _get_gpu_info() -> list[dict] | None:
    """Try to get GPU info from nvidia-smi or pynvml."""
    # Try pynvml first
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        gpus = []
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except Exception:
                temp = None
            gpus.append({
                "name": name,
                "util_percent": util.gpu,
                "mem_used_gb": round(mem.used / (1024 ** 3), 2),
                "mem_total_gb": round(mem.total / (1024 ** 3), 2),
                "mem_percent": round(mem.used / mem.total * 100, 1) if mem.total > 0 else 0,
                "temperature_c": temp,
            })
        pynvml.nvmlShutdown()
        return gpus if gpus else None
    except Exception:
        pass

    # Fallback: nvidia-smi CLI
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpus = []
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    mem_used = float(parts[2])
                    mem_total = float(parts[3])
                    gpus.append({
                        "name": parts[0],
                        "util_percent": float(parts[1]),
                        "mem_used_gb": round(mem_used / 1024, 2),
                        "mem_total_gb": round(mem_total / 1024, 2),
                        "mem_percent": round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0,
                        "temperature_c": int(float(parts[4])),
                    })
            return gpus if gpus else None
    except Exception:
        pass

    # AMD GPU via rocm-smi
    try:
        import subprocess
        result = subprocess.run(
            ["rocm-smi", "--showuse", "--showmeminfo", "vram", "--showtemp", "--csv"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # rocm-smi CSV output can be tricky, fall back to sysfs
            raise ValueError("use sysfs")
    except Exception:
        pass

    # AMD GPU via sysfs (works inside Docker too if /sys is mounted)
    try:
        import glob as _glob
        cards = sorted(_glob.glob("/sys/class/drm/card[0-9]*/device/gpu_busy_percent"))
        if cards:
            gpus = []
            for busy_path in cards:
                dev_dir = os.path.dirname(busy_path)
                card_dir = os.path.dirname(dev_dir)

                def _read(path: str) -> str | None:
                    try:
                        with open(path) as f:
                            return f.read().strip()
                    except Exception:
                        return None

                # GPU name
                name_raw = _read(os.path.join(dev_dir, "product_name"))
                if not name_raw:
                    # Try PCI device name
                    vendor = _read(os.path.join(dev_dir, "vendor"))
                    device = _read(os.path.join(dev_dir, "device"))
                    name_raw = f"AMD GPU ({vendor}:{device})" if vendor else "AMD GPU"

                util = _read(busy_path)
                vram_total = _read(os.path.join(dev_dir, "mem_info_vram_total"))
                vram_used = _read(os.path.join(dev_dir, "mem_info_vram_used"))

                # Temperature from hwmon
                temp = None
                hwmon_temps = _glob.glob(os.path.join(dev_dir, "hwmon", "hwmon*", "temp1_input"))
                if hwmon_temps:
                    temp_raw = _read(hwmon_temps[0])
                    if temp_raw:
                        temp = int(temp_raw) // 1000  # millidegrees to degrees

                mem_used_gb = round(int(vram_used) / (1024 ** 3), 2) if vram_used else None
                mem_total_gb = round(int(vram_total) / (1024 ** 3), 2) if vram_total else None
                mem_pct = round(int(vram_used) / int(vram_total) * 100, 1) if (vram_used and vram_total and int(vram_total) > 0) else None

                gpus.append({
                    "name": name_raw,
                    "util_percent": int(util) if util else None,
                    "mem_used_gb": mem_used_gb,
                    "mem_total_gb": mem_total_gb,
                    "mem_percent": mem_pct,
                    "temperature_c": temp,
                })
            return gpus if gpus else None
    except Exception:
        pass

    # macOS: check for Apple Silicon GPU (unified memory)
    if platform.system() == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return [{
                    "name": "Apple Silicon (unified)",
                    "util_percent": None,
                    "mem_used_gb": None,
                    "mem_total_gb": None,
                    "mem_percent": None,
                    "temperature_c": None,
                }]
        except Exception:
            pass

    return None


async def _get_worker_activity() -> WorkerActivity:
    """Read current worker activity from Redis."""
    try:
        from arq.connections import create_pool, RedisSettings
        from ..config import settings

        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))

        # Read activity data
        activity_raw = await redis.get("worker:activity")
        heartbeat_raw = await redis.get("worker:heartbeat")
        errors_raw = await redis.get("worker:recent_errors")
        error_budget_raw = await redis.get("worker:error_budget")
        log_raw = await redis.lrange("worker:log", 0, 49)  # Last 50 entries

        await redis.close()

        def _decode(v):
            return v.decode() if isinstance(v, bytes) else v

        activity = json.loads(_decode(activity_raw)) if activity_raw else {}
        errors = json.loads(_decode(errors_raw)) if errors_raw else []
        error_budget = json.loads(_decode(error_budget_raw)) if error_budget_raw else None
        log_entries = [json.loads(_decode(entry)) for entry in (log_raw or [])]

        return WorkerActivity(
            run_id=activity.get("run_id"),
            status=activity.get("status", "idle"),
            current_case=activity.get("current_case"),
            cases_per_min=activity.get("cases_per_min", 0),
            last_heartbeat=_decode(heartbeat_raw) if heartbeat_raw else None,
            recent_errors=errors if errors else None,
            error_budget=error_budget,
            worker_log=log_entries if log_entries else None,
        )
    except Exception:
        return WorkerActivity(status="unknown")


@router.get("/system", response_model=HealthResponse)
async def get_system_health():
    """Get comprehensive system health metrics."""
    system = _get_system_metrics()
    worker = await _get_worker_activity()
    return HealthResponse(
        system=system,
        worker=worker,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
