"""Environment checks: interpreter, libs, model file, dependency pins."""

from __future__ import annotations

import re
import sys

from .common import PYTHON, ROOT
from .registry import check


def _version(module: str) -> str:
    import importlib.metadata as metadata

    return metadata.version(module)


@check("env.python.version", desc="Python >= 3.10")
def python_version() -> None:
    assert sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} is too old (need >= 3.10)"
    assert PYTHON, "no interpreter resolved"


@check("env.mediapipe.import", desc="import mediapipe")
def mediapipe_import() -> None:
    import mediapipe  # noqa: F401


@check("env.mediapipe.version", desc="mediapipe version is readable")
def mediapipe_version() -> None:
    version = _version("mediapipe")
    parts = version.split(".")
    assert parts[0].isdigit(), f"unexpected mediapipe version {version!r}"


@check("env.cv2", desc="opencv import + version")
def cv2_check() -> None:
    import cv2

    assert cv2.__version__, "cv2.__version__ empty"
    assert hasattr(cv2, "VideoCapture"), "cv2 lacks VideoCapture"


@check("env.numpy", desc="numpy import")
def numpy_check() -> None:
    import numpy

    assert numpy.__version__, "numpy.__version__ empty"


@check("env.pythonosc", desc="python-osc import (OSC renderer path)")
def pythonosc_check() -> None:
    from pythonosc import udp_client  # noqa: F401


@check("env.model.file", desc="models/pose_landmarker_lite.task exists")
def model_file() -> None:
    model = ROOT / "models" / "pose_landmarker_lite.task"
    assert model.exists(), "models/pose_landmarker_lite.task is missing"
    size = model.stat().st_size
    assert size > 1_000_000, f"model file is suspiciously small: {size} bytes"


@check("env.requirements.pin", desc="requirements.txt mediapipe pin matches installed")
def requirements_pin() -> None:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(r"mediapipe\s*([<>=!~][^\s#]*)", text)
    assert match, "no mediapipe constraint in requirements.txt"
    pin = match.group(1)
    installed = _version("mediapipe")
    drift = (installed.startswith("1.") and "<0.11" in pin) or (
        installed.startswith("0.10") and pin.startswith(">=1")
    )
    assert not drift, (
        f"requirements pin mediapipe{pin} vs installed {installed}: "
        "align them (pip install 'mediapipe>=0.10.20,<0.11' or migrate to Tasks API)"
    )


@check("env.mcp.client", desc="mcp python client available (live MCP checks)")
def mcp_client() -> None:
    from mcp import ClientSession  # noqa: F401
    from mcp.client.stdio import stdio_client  # noqa: F401
