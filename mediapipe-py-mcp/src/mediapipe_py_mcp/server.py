"""MCP tools that run MediaPipe Pose over local images and the local camera.

The server never executes shell commands and never writes image data: frames are
read from ``MP_MEDIA_ROOT`` (or the camera) and analysed in memory, and only
numeric pose features are returned or forwarded over OSC.

The OSC contract matches ``mppdp5/server.py``: ``/pose/points``,
``/left_speed``, ``/right_speed`` and ``/hip_sway``.
"""
from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pythonosc.udp_client import SimpleUDPClient

from . import landmarker
from .pose import POINTS_PER_FRAME, PoseFrame, PoseInterpreter, named_landmarks

mcp = FastMCP("mediapipe-py-mcp")

HOST = os.getenv("MP_OSC_HOST", "127.0.0.1")
PORT = int(os.getenv("MP_OSC_PORT", "12000"))
MEDIA_ROOT = Path(os.getenv("MP_MEDIA_ROOT", str(Path.cwd() / "media"))).resolve()
CAMERA_INDEX = int(os.getenv("MP_CAMERA_INDEX", "0"))
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# Camera captures share one interpreter so wrist speed and hip sway build up.
_camera_interpreter = PoseInterpreter()


def _media_path(filename: str) -> Path:
    candidate = (MEDIA_ROOT / filename).resolve()
    if candidate != MEDIA_ROOT and MEDIA_ROOT not in candidate.parents:
        raise ValueError("Image path must stay inside MP_MEDIA_ROOT")
    if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(
            "Unsupported image type "
            f"'{candidate.suffix}'. Allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}"
        )
    return candidate


def _payload(
    source: str,
    width: int,
    height: int,
    landmarks: list[tuple[float, float, float]],
    frame: PoseFrame,
) -> dict[str, Any]:
    payload = frame.to_dict()
    payload.update(
        {
            "source": source,
            "width": width,
            "height": height,
            "landmark_count": len(landmarks),
            "landmarks": named_landmarks(landmarks),
        }
    )
    return payload


@mcp.tool()
def mp_status() -> dict[str, Any]:
    """Report MediaPipe, model, media-root and OSC configuration.

    Detection is not attempted, so a missing model or an unimportable MediaPipe
    is reported instead of raised.
    """
    try:
        version: str | None = landmarker.mediapipe_version()
        import_error: str | None = None
    except Exception as exc:  # depends on the environment, not on the request
        version = None
        import_error = str(exc)

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", 0))
        udp_available = True
    except OSError:
        udp_available = False
    finally:
        probe.close()

    return {
        "server": "mediapipe-py-mcp",
        "mediapipe_version": version,
        "mediapipe_error": import_error,
        "model_path": str(landmarker.MODEL_PATH),
        "model_present": landmarker.model_present(),
        "media_root": str(MEDIA_ROOT),
        "media_root_present": MEDIA_ROOT.is_dir(),
        "osc_host": HOST,
        "osc_port": PORT,
        "camera_index": CAMERA_INDEX,
        "udp_available": udp_available,
        "points_per_frame": POINTS_PER_FRAME,
        "note": "Frames are analysed in memory and never written to disk.",
    }


@mcp.tool()
def mp_list_media() -> list[dict[str, Any]]:
    """List analysable image files under MP_MEDIA_ROOT."""
    if not MEDIA_ROOT.is_dir():
        return []
    files = sorted(
        path
        for path in MEDIA_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES
    )
    return [
        {
            "name": str(path.relative_to(MEDIA_ROOT)).replace("\\", "/"),
            "bytes": path.stat().st_size,
        }
        for path in files
    ]


@mcp.tool()
def mp_analyze_image(filename: str) -> dict[str, Any]:
    """Run MediaPipe Pose on one image under MP_MEDIA_ROOT and return the features.

    Wrist speed and hip sway need consecutive frames, so a still image reports
    them as 0. Use mp_analyze_frame for the stateful camera path.
    """
    path = _media_path(filename)
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    landmarks, width, height = landmarker.detect_image_file(path)
    frame = PoseInterpreter().update(landmarks, width, height)
    return _payload(path.name, width, height, landmarks, frame)


@mcp.tool()
def mp_analyze_frame() -> dict[str, Any]:
    """Capture one camera frame, analyse it, and keep tracking state.

    Consecutive calls build the wrist-speed and hip-sway history, so prefer this
    over mp_analyze_image when tracking a live body.
    """
    import cv2

    capture = cv2.VideoCapture(
        CAMERA_INDEX, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0
    )
    if not capture.isOpened():
        capture.release()
        capture = cv2.VideoCapture(CAMERA_INDEX)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(
            f"Could not open camera {CAMERA_INDEX}. "
            "Check the Windows camera privacy settings."
        )
    try:
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise RuntimeError("Camera opened but returned no frame.")

    frame = cv2.flip(frame, 1)
    height, width = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    landmarks = landmarker.detect_numpy(rgb)
    interpreted = _camera_interpreter.update(landmarks, width, height)
    return _payload(f"camera[{CAMERA_INDEX}]", width, height, landmarks, interpreted)


@mcp.tool()
def mp_emit_osc(filename: str) -> dict[str, Any]:
    """Analyse an image and forward the pose contract to the Processing renderer.

    Sends ``/pose/points``, ``/left_speed``, ``/right_speed`` and ``/hip_sway``
    to ``MP_OSC_HOST:MP_OSC_PORT``.
    """
    path = _media_path(filename)
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    landmarks, width, height = landmarker.detect_image_file(path)
    frame = PoseInterpreter().update(landmarks, width, height)
    client = SimpleUDPClient(HOST, PORT)
    addresses: list[str] = []
    for address, value in frame.osc_messages():
        client.send_message(address, value)
        addresses.append(address)
    return {
        "sent": True,
        "to": f"{HOST}:{PORT}",
        "addresses": addresses,
        "detected": frame.detected,
        "points": len(frame.points),
        "source": path.name,
    }


@mcp.tool()
def mp_reset_tracking() -> dict[str, Any]:
    """Clear the camera wrist-speed and hip-sway history."""
    _camera_interpreter.reset()
    return {"reset": True}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
