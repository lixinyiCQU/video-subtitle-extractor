from __future__ import annotations

from datetime import datetime, timezone
import os
import subprocess
from pathlib import Path


def log_resource_snapshot(stage: str) -> None:
    rss_mb = _process_rss_mb()
    available_mb = _system_available_mb()
    gpu = _gpu_summary()
    print(
        f"[subtitle-extractor][resources] time={datetime.now(timezone.utc).isoformat()} "
        f"stage={stage} pid={os.getpid()} "
        f"rss={_format_mb(rss_mb)} system_available={_format_mb(available_mb)} gpu={gpu}",
        flush=True,
    )


def _process_rss_mb() -> float | None:
    status_path = Path("/proc/self/status")
    if status_path.exists():
        for line in status_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024
    try:
        import resource

        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value / 1024 if os.name != "nt" else value / (1024 * 1024)
    except (ImportError, OSError, ValueError):
        return None


def _system_available_mb() -> float | None:
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        return None
    for line in meminfo_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("MemAvailable:"):
            return float(line.split()[1]) / 1024
    return None


def _gpu_summary() -> str:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return "unavailable"
    if completed.returncode != 0 or not completed.stdout.strip():
        return "unavailable"
    return " | ".join(line.strip().replace(", ", ":") for line in completed.stdout.splitlines() if line.strip())


def _format_mb(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.0f}MiB"
