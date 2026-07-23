import shutil
import subprocess
from typing import Any

import psutil


def gpu_status() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    gpus: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) == 5:
            gpus.append(
                {
                    "name": parts[0],
                    "memory_used_mb": int(parts[1]),
                    "memory_total_mb": int(parts[2]),
                    "utilization_percent": int(parts[3]),
                    "temperature_c": int(parts[4]),
                }
            )
    return gpus


def system_status() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.15),
        "cpu_count": psutil.cpu_count(),
        "memory": {
            "total": memory.total,
            "available": memory.available,
            "used": memory.used,
            "percent": memory.percent,
        },
        "disk": {
            "total": disk.total,
            "free": disk.free,
            "used": disk.used,
            "percent": disk.percent,
        },
        "gpus": gpu_status(),
    }
