"""Probe Ollama server for hardware capabilities and compute optimal concurrency.

Queries the Ollama API to discover:
  - GPU VRAM available and in use
  - Model parameter size / VRAM footprint
  - OLLAMA_NUM_PARALLEL setting (inferred from server behavior)

Returns an optimal max_concurrent value for the given model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OllamaHardwareInfo:
    """Hardware and model info from Ollama server."""

    total_vram_bytes: int = 0
    free_vram_bytes: int = 0
    model_size_bytes: int = 0  # Size of the requested model on disk
    model_vram_bytes: int = 0  # VRAM currently used by the model (from /api/ps)
    model_loaded: bool = False
    num_parallel: int = 1  # Inferred OLLAMA_NUM_PARALLEL
    gpu_name: str = ""
    recommended_concurrency: int = 1


# Known GPU VRAM sizes (bytes) for common GPUs — fallback if detection fails
_KNOWN_GPUS_GB = {
    "4090": 24, "4080": 16, "4070 Ti Super": 16, "4070 Ti": 12, "4070": 12,
    "3090": 24, "3080": 10, "3070": 8, "3060": 12,
    "A100": 80, "A6000": 48, "A5000": 24, "A4000": 16,
    "H100": 80, "L40S": 48, "L4": 24,
    "RTX 6000": 48, "RTX 5000": 32,
    # Apple Silicon (unified memory — Ollama reports as VRAM)
    "Apple M1": 16, "Apple M1 Pro": 16, "Apple M1 Max": 32, "Apple M1 Ultra": 64,
    "Apple M2": 8, "Apple M2 Pro": 16, "Apple M2 Max": 32, "Apple M2 Ultra": 64,
    "Apple M3": 8, "Apple M3 Pro": 18, "Apple M3 Max": 36, "Apple M3 Ultra": 128,
    "Apple M4": 16, "Apple M4 Pro": 24, "Apple M4 Max": 36, "Apple M4 Ultra": 128,
}

# Model size tiers and their approximate VRAM usage per concurrent instance (GB)
# These are rough estimates for the KV cache overhead per parallel slot
_KV_CACHE_OVERHEAD_GB = {
    "tiny": 0.3,     # <1B params
    "small": 0.5,    # 1-3B params
    "medium": 1.0,   # 3-8B params
    "large": 2.0,    # 8-14B params
    "xlarge": 3.5,   # 14-34B params
    "xxlarge": 6.0,  # 34-70B params
    "huge": 12.0,    # 70B+ params
}


def _model_size_tier(size_bytes: int) -> str:
    """Classify model into a size tier based on disk/VRAM size."""
    gb = size_bytes / (1024 ** 3)
    if gb < 1:
        return "tiny"
    elif gb < 2.5:
        return "small"
    elif gb < 5:
        return "medium"
    elif gb < 10:
        return "large"
    elif gb < 22:
        return "xlarge"
    elif gb < 45:
        return "xxlarge"
    else:
        return "huge"


def _compute_optimal_concurrency(
    total_vram_bytes: int,
    model_vram_bytes: int,
    model_size_bytes: int,
    num_parallel: int,
) -> int:
    """Compute optimal concurrency from hardware and model info.

    Strategy:
    - Start with VRAM headroom after model is loaded
    - Estimate KV cache overhead per concurrent slot
    - Cap at OLLAMA_NUM_PARALLEL (server-side limit)
    - Minimum of 1, maximum of 32
    """
    if total_vram_bytes == 0 or model_size_bytes == 0:
        # Can't determine — use conservative default
        return min(num_parallel, 4)

    # VRAM available after loading the model
    model_vram = model_vram_bytes if model_vram_bytes > 0 else model_size_bytes
    headroom_bytes = total_vram_bytes - model_vram
    headroom_gb = headroom_bytes / (1024 ** 3)

    # Estimate per-slot KV cache overhead
    tier = _model_size_tier(model_size_bytes)
    kv_overhead_gb = _KV_CACHE_OVERHEAD_GB[tier]

    # How many additional concurrent slots can we fit?
    if kv_overhead_gb > 0 and headroom_gb > 0:
        extra_slots = int(headroom_gb / kv_overhead_gb)
    else:
        extra_slots = 0

    # Total = 1 (base) + extra slots, capped by server's num_parallel
    optimal = max(1, min(1 + extra_slots, num_parallel, 32))

    logger.info(
        f"Ollama concurrency: total_vram={total_vram_bytes / 1e9:.1f}GB, "
        f"model_vram={model_vram / 1e9:.1f}GB, headroom={headroom_gb:.1f}GB, "
        f"tier={tier}, kv_overhead={kv_overhead_gb}GB/slot, "
        f"extra_slots={extra_slots}, num_parallel={num_parallel}, "
        f"optimal={optimal}"
    )

    return optimal


async def probe_ollama(
    base_url: str = "http://localhost:11434",
    model: str = "llama3.1",
    timeout: float = 10.0,
) -> OllamaHardwareInfo:
    """Probe Ollama server for hardware info and compute optimal concurrency.

    Makes best-effort queries to /api/ps and /api/show. If the server is
    unreachable or the model isn't loaded, returns conservative defaults.
    """
    info = OllamaHardwareInfo()

    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(connect=5.0, read=timeout, write=5.0, pool=5.0),
    ) as client:
        # --- Query /api/ps for running models and VRAM usage ---
        try:
            resp = await client.get("/api/ps")
            resp.raise_for_status()
            ps_data = resp.json()

            for m in ps_data.get("models", []):
                # Total VRAM = size_vram across all loaded models
                size_vram = m.get("size_vram", 0)
                size_total = m.get("size", 0)
                info.total_vram_bytes = max(info.total_vram_bytes, size_vram + size_total)

                # Check if our target model is loaded
                m_name = m.get("name", "")
                if model in m_name or m_name.startswith(model):
                    info.model_vram_bytes = size_vram
                    info.model_loaded = True
                    info.model_size_bytes = size_total

                # Extract GPU info from details
                details = m.get("details", {})
                if details.get("gpu"):
                    info.gpu_name = details["gpu"]

        except Exception as e:
            logger.debug(f"Ollama /api/ps probe failed: {e}")

        # --- Query /api/show for model details ---
        try:
            resp = await client.post("/api/show", json={"name": model})
            resp.raise_for_status()
            show_data = resp.json()

            # Model size from modelfile info
            model_info = show_data.get("model_info", {})

            # Get parameter count for better size estimation
            param_count = model_info.get("general.parameter_count", 0)
            if param_count and not info.model_size_bytes:
                # Rough estimate: each param ≈ 2 bytes (Q4 quantization average)
                info.model_size_bytes = param_count * 2

            # Get size from details
            details = show_data.get("details", {})
            param_size = details.get("parameter_size", "")
            if param_size and not info.model_size_bytes:
                # Parse "7B", "13B", "70B" etc.
                try:
                    multiplier = {"B": 1e9, "M": 1e6, "K": 1e3}
                    suffix = param_size[-1].upper()
                    num = float(param_size[:-1])
                    params = num * multiplier.get(suffix, 1)
                    # Q4 quantization: ~0.5 bytes per param
                    info.model_size_bytes = int(params * 0.5)
                except (ValueError, IndexError):
                    pass

        except Exception as e:
            logger.debug(f"Ollama /api/show probe failed: {e}")

        # --- Infer OLLAMA_NUM_PARALLEL ---
        # Default is 1 for most setups, 4 for high-VRAM GPUs
        # We can't directly query this, so we estimate from VRAM
        if info.total_vram_bytes > 0:
            total_gb = info.total_vram_bytes / (1024 ** 3)
            if total_gb >= 48:
                info.num_parallel = 8
            elif total_gb >= 24:
                info.num_parallel = 4
            elif total_gb >= 12:
                info.num_parallel = 2
            else:
                info.num_parallel = 1
        else:
            info.num_parallel = 4  # Reasonable default

        # --- Compute optimal concurrency ---
        info.recommended_concurrency = _compute_optimal_concurrency(
            total_vram_bytes=info.total_vram_bytes,
            model_vram_bytes=info.model_vram_bytes,
            model_size_bytes=info.model_size_bytes,
            num_parallel=info.num_parallel,
        )

    logger.info(
        f"Ollama probe result: model={model}, loaded={info.model_loaded}, "
        f"vram={info.total_vram_bytes / 1e9:.1f}GB, "
        f"model_size={info.model_size_bytes / 1e9:.1f}GB, "
        f"gpu={info.gpu_name or 'unknown'}, "
        f"recommended_concurrency={info.recommended_concurrency}"
    )

    return info
