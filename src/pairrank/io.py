"""Results rows: every JSONL row carries enough metadata to reproduce it."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import scipy


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def _power_source() -> str:
    """Battery or AC on macOS; timings in a row should be read with this in mind."""
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return "battery" if "Battery Power" in out.stdout else "ac"


def run_metadata(master_seed: int) -> dict[str, Any]:
    return {
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": _git("status", "--porcelain") != "",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "platform": f"{sys.platform}-{platform.machine()}",
        "power": _power_source(),
        "master_seed": master_seed,
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
