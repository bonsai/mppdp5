from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="mpp5 local pose bridge")
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "type": "pose",
    "camera": "starting",
    "detected": False,
    "lean": 0.0,
    "arms_spread": False,
    "crouch": False,
    "confidence": 0.0,
    "timestamp": time.time(),
}
_stop = threading.Event()


def set_state(**values: Any) -> None:
    with _lock:
        _state.update(values, timestamp=time.time())


def camera_worker() -> None:
    """Read the local camera and publish only derived pose features."""
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        set_state(camera="unavailable", detected=False, confidence=0.0)
        print("ERROR: Could not open camera 0. Check Windows camera privacy settings.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    set_state(camera="ready")
    print("Camera ready. Raw frames are processed in memory and never saved.")

    try:
        pose_api = mp.solutions.pose
        with pose_api.Pose(
            static_image_mode=False,
            model_complexity=0,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as pose:
            while not _stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    set_state(camera="read_error", detected=False, confidence=0.0)
                    time.sleep(0.1)
                    continue

                # Mirror the input so leaning feels like a mirror.
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = pose.process(rgb)

                if not result.pose_landmarks:
                    set_state(
                        camera="ready",
                        detected=False,
                        lean=0.0,
                        arms_spread=False,
                        crouch=False,
                        confidence=0.0,
                    )
                    continue

                lm = result.pose_landmarks.landmark
                P = pose_api.PoseLandmark
                left_sh = lm[P.LEFT_SHOULDER.value]
                right_sh = lm[P.RIGHT_SHOULDER.value]
                left_wrist = lm[P.LEFT_WRIST.value]
                right_wrist = lm[P.RIGHT_WRIST.value]
                left_hip = lm[P.LEFT_HIP.value]
                right_hip = lm[P.RIGHT_HIP.value]
                left_knee = lm[P.LEFT_KNEE.value]
                right_knee = lm[P.RIGHT_KNEE.value]

                required = [left_sh, right_sh, left_hip, right_hip]
                confidence = sum(p.visibility for p in required) / len(required)
                shoulder_center_x = (left_sh.x + right_sh.x) / 2.0
                shoulder_center_y = (left_sh.y + right_sh.y) / 2.0
                hip_center_y = (left_hip.y + right_hip.y) / 2.0
                knee_center_y = (left_knee.y + right_knee.y) / 2.0
                shoulder_width = max(abs(left_sh.x - right_sh.x), 0.05)
                wrist_span = abs(left_wrist.x - right_wrist.x)

                # Lean is relative to the image center, clamped to [-1, 1].
                lean = max(-1.0, min(1.0, (shoulder_center_x - 0.5) * 2.4))
                arms_spread = (
                    left_wrist.visibility > 0.45
                    and right_wrist.visibility > 0.45
                    and wrist_span / shoulder_width > 2.0
                )
                # A simple normalized hip-to-knee heuristic; validate for each setup.
                crouch = hip_center_y > (shoulder_center_y + knee_center_y) / 2.0 + 0.015

                set_state(
                    camera="ready",
                    detected=confidence >= 0.35,
                    lean=round(lean, 3),
                    arms_spread=bool(arms_spread),
                    crouch=bool(crouch),
                    confidence=round(float(confidence), 3),
                )
    except Exception as exc:
        set_state(camera="error", detected=False, confidence=0.0)
        print(f"Camera/MediaPipe error: {exc}")
    finally:
        cap.release()
        print("Camera released.")


@app.on_event("startup")
def start_camera() -> None:
    _stop.clear()
    threading.Thread(target=camera_worker, name="mpp5-camera", daemon=True).start()


@app.on_event("shutdown")
def stop_camera() -> None:
    _stop.set()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            with _lock:
                payload = dict(_state)
            await websocket.send_json(payload)
            await asyncio.sleep(1 / 30)
    except (WebSocketDisconnect, RuntimeError):
        return


if __name__ == "__main__":
    import uvicorn

    print("mpp5 display: http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
