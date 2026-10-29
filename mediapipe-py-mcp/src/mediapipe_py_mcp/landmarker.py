"""MediaPipe PoseLandmarker wrapper built on the Tasks API.

The legacy ``mp.solutions.pose`` API was removed from MediaPipe (it is absent in
both 0.10.35 and 1.x), so this module uses
``mediapipe.tasks.python.vision.PoseLandmarker`` with a ``.task`` model bundle.

The model file is downloaded by the installer and is never committed. Point
``MP_MODEL_PATH`` at another bundle to override it.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Sequence

#: mediapipe-py-mcp/ (``src/mediapipe_py_mcp/landmarker.py`` -> up three levels).
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PACKAGE_ROOT / "models" / "pose_landmarker_lite.task"
MODEL_PATH = Path(os.getenv("MP_MODEL_PATH") or DEFAULT_MODEL_PATH).resolve()
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)

_lock = threading.Lock()
_landmarker: Any = None


def model_present() -> bool:
    """Return True when the model bundle exists on disk."""
    return MODEL_PATH.is_file()


def mediapipe_version() -> str:
    """Return the installed MediaPipe version string."""
    import mediapipe as mp

    return getattr(mp, "__version__", "unknown")


def _create_landmarker() -> Any:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(
            f"Pose model not found: {MODEL_PATH}. Run scripts/install-windows.ps1, "
            f"or download {MODEL_URL} and set MP_MODEL_PATH."
        )

    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    options = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(options)


def landmarker() -> Any:
    """Return the cached PoseLandmarker, creating it on first use."""
    global _landmarker
    with _lock:
        if _landmarker is None:
            _landmarker = _create_landmarker()
        return _landmarker


def reset() -> None:
    """Drop the cached landmarker (used by tests and after a model change)."""
    global _landmarker
    with _lock:
        _landmarker = None


def detect_landmarks(image: Any) -> list[tuple[float, float, float]]:
    """Run pose detection on a mediapipe Image and return 33 ``(x, y, visibility)``."""
    result = landmarker().detect(image)
    if not result.pose_landmarks:
        return []
    return [
        (float(point.x), float(point.y), float(point.visibility))
        for point in result.pose_landmarks[0]
    ]


def detect_image_file(path: Path) -> tuple[list[tuple[float, float, float]], int, int]:
    """Detect a pose in an image file; return ``(landmarks, width, height)``."""
    import mediapipe as mp

    image = mp.Image.create_from_file(str(path))
    return detect_landmarks(image), int(image.width), int(image.height)


def detect_numpy(rgb: Sequence[Any]) -> list[tuple[float, float, float]]:
    """Detect a pose in an in-memory RGB array (camera path)."""
    import mediapipe as mp

    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    return detect_landmarks(image)
