from __future__ import annotations

import asyncio
import math
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pythonosc import udp_client

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
OSC_HOST = "127.0.0.1"
OSC_PORT = 12000

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
    """Interpret pose once and publish to both the web and Processing renderers."""
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

    osc = udp_client.SimpleUDPClient(OSC_HOST, OSC_PORT)
    prev_left: tuple[float, float] | None = None
    prev_right: tuple[float, float] | None = None
    hip_x_history: deque[float] = deque(maxlen=20)

    try:
        pose_api = mp.solutions.pose
        P = pose_api.PoseLandmark
        landmark_order = [
            P.NOSE, P.LEFT_SHOULDER, P.RIGHT_SHOULDER, P.LEFT_ELBOW,
            P.RIGHT_ELBOW, P.LEFT_WRIST, P.RIGHT_WRIST, P.LEFT_HIP,
            P.RIGHT_HIP, P.LEFT_KNEE, P.RIGHT_KNEE, P.LEFT_ANKLE, P.RIGHT_ANKLE,
        ]
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

                frame = cv2.flip(frame, 1)
                height, width = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = pose.process(rgb)

                if not result.pose_landmarks:
                    set_state(
                        camera="ready", detected=False, lean=0.0,
                        arms_spread=False, crouch=False, confidence=0.0,
                    )
                    osc.send_message("/pose/points", [-1.0, -1.0] * 14)
                    osc.send_message("/left_speed", 0.0)
                    osc.send_message("/right_speed", 0.0)
                    osc.send_message("/hip_sway", 0.0)
                    prev_left = prev_right = None
                    hip_x_history.clear()
                    continue

                lm = result.pose_landmarks.landmark
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
                lean = max(-1.0, min(1.0, (shoulder_center_x - 0.5) * 2.4))
                arms_spread = (
                    left_wrist.visibility > 0.45
                    and right_wrist.visibility > 0.45
                    and wrist_span / shoulder_width > 2.0
                )
                crouch = hip_center_y > (shoulder_center_y + knee_center_y) / 2.0 + 0.015

                # OSC contract: 13 filtered landmarks plus the interpreted hip center.
                points: list[float] = []
                for landmark_type in landmark_order:
                    point = lm[landmark_type.value]
                    if point.visibility >= 0.35:
                        points.extend([float(point.x), float(point.y)])
                    else:
                        points.extend([-1.0, -1.0])

                if min(left_hip.visibility, right_hip.visibility) >= 0.35:
                    hip_x = (left_hip.x + right_hip.x) / 2.0
                    hip_y = (left_hip.y + right_hip.y) / 2.0
                    points.extend([float(hip_x), float(hip_y)])
                    hip_x_history.append(hip_x)
                    hip_sway = 0.0
                    if len(hip_x_history) >= 5:
                        mean_x = sum(hip_x_history) / len(hip_x_history)
                        variance = sum((x - mean_x) ** 2 for x in hip_x_history) / len(hip_x_history)
                        hip_sway = min(math.sqrt(variance) * width / 25.0, 1.5)
                        if hip_sway < 0.03:
                            hip_sway = 0.0
                else:
                    points.extend([-1.0, -1.0])
                    hip_sway = 0.0

                left_pos = (left_wrist.x * width, left_wrist.y * height)
                right_pos = (right_wrist.x * width, right_wrist.y * height)
                left_speed = math.hypot(left_pos[0] - prev_left[0], left_pos[1] - prev_left[1]) if prev_left else 0.0
                right_speed = math.hypot(right_pos[0] - prev_right[0], right_pos[1] - prev_right[1]) if prev_right else 0.0
                prev_left, prev_right = left_pos, right_pos

                osc.send_message("/pose/points", points)
                osc.send_message("/left_speed", float(left_speed))
                osc.send_message("/right_speed", float(right_speed))
                osc.send_message("/hip_sway", float(hip_sway))

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

    print("mpp5 web display: http://127.0.0.1:8765")
    print(f"Processing OSC output: {OSC_HOST}:{OSC_PORT}/UDP")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
