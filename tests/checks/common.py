"""Shared helpers for the mppdp5 check suite."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(
    os.environ.get("MPPDP5_ROOT")
    or Path(__file__).resolve().parents[2]
)
WORK = ROOT / "work"
PYTHON = os.environ.get("MPPDP5_PYTHON") or sys.executable
TIMEOUT = 180


def rel(path: Path | str) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read(rel_path: str) -> str:
    path = ROOT / rel_path
    assert path.exists(), f"{rel_path} is missing"
    return path.read_text(encoding="utf-8", errors="replace")


def run(
    args: list[str] | str,
    *,
    timeout: int = TIMEOUT,
    cwd: Path | None = None,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=shell,
    )


def cli(*args: str, timeout: int = TIMEOUT) -> subprocess.CompletedProcess:
    return run([PYTHON, "-m", "cli.main", *args], timeout=timeout)


def ensure_video(frames: int = 12, size: tuple[int, int] = (320, 240)) -> Path:
    """Create a tiny synthetic clip once; return its path."""
    import cv2
    import numpy as np

    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "test_input.mp4"
    if path.exists() and path.stat().st_size > 0:
        return path

    width, height = size
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 15.0, (width, height)
    )
    assert writer.isOpened(), "cv2.VideoWriter could not open mp4v"
    for index in range(frames):
        frame = np.full((height, width, 3), 30, dtype=np.uint8)
        cv2.circle(frame, (160, 80), 18, (200, 180, 160), -1)
        cv2.line(frame, (160, 98), (160, 160), (200, 180, 160), 6)
        cv2.line(frame, (160, 110), (110 + index, 140), (200, 180, 160), 5)
        cv2.line(frame, (160, 110), (210 - index, 140), (200, 180, 160), 5)
        writer.write(frame)
    writer.release()
    return path


def fresh(path: Path) -> Path:
    """Remove a file or directory so append-mode writers start clean."""
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_file():
                child.unlink()
    elif path.exists():
        path.unlink()
    return path


def read_jsonl(path: Path) -> list[dict]:
    assert path.exists(), f"{rel(path)} was not created"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, f"{rel(path)} is empty"
    return [json.loads(line) for line in lines]


def tail(proc: subprocess.CompletedProcess, limit: int = 12) -> str:
    text = ((proc.stderr or "") + (proc.stdout or "")).strip().splitlines()
    return " | ".join(text[-limit:])
