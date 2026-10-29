from __future__ import annotations

import asyncio
import math
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pythonosc import udp_client

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
OSC_HOST = "127.0.0.1"
OSC_PORT = 9000

# ── 共有状態 ──────────────────────────────────────────────
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

# ── カメラワーカー ────────────────────────────────────────
def set_state(**values: Any) -> None:
    with _lock:
        _state.update(values, timestamp=time.time())


def camera_worker() -> None:
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
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision import PoseLandmarkerOptions, RunningMode
        import mediapipe as mp

        base_options = BaseOptions(
            model_asset_path=str(Path(__file__).parent / "models" / "pose_landmarker_lite.task"),
            delegate=BaseOptions.Delegate.CPU,
        )
        options = PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.VIDEO,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        pose = vision.PoseLandmarker.create_from_options(options)

        # Landmark index mapping for 14 key points
        idx_map = {
            0: 0,   # NOSE
            11: 11, # LEFT_SHOULDER
            12: 12, # RIGHT_SHOULDER
            13: 13, # LEFT_ELBOW
            14: 14, # RIGHT_ELBOW
            15: 15, # LEFT_WRIST
            16: 16, # RIGHT_WRIST
            23: 23, # LEFT_HIP
            24: 24, # RIGHT_HIP
            25: 25, # LEFT_KNEE
            26: 26, # RIGHT_KNEE
        }
        with pose:
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


# ── 釣り・漫画化 用 モックデータ生成 ──────────────────────
def generate_fish_catch(pose_state: dict) -> dict:
    """姿勢から釣果を生成"""
    if not pose_state.get("detected"):
        return {"caught": False, "reason": "no_pose"}
    
    lean = abs(pose_state.get("lean", 0))
    arms_spread = pose_state.get("arms_spread", False)
    crouch = pose_state.get("crouch", False)
    confidence = pose_state.get("confidence", 0)
    
    # 釣り判定ロジック
    base_chance = 0.3
    if arms_spread:  # 竿を振る動作
        base_chance += 0.4
    if crouch:  # しゃがんで待機
        base_chance += 0.2
    if lean > 0.5:  # 大きく傾けてアワセ
        base_chance += 0.3
    
    import random
    caught = random.random() < min(base_chance * confidence, 0.95)
    
    fish_types = ["タイ", "ブリ", "ヒラメ", "マグロ", "カツオ", "サケ", "アジ", "イワシ"]
    sizes = ["小", "中", "大", "特大"]
    
    return {
        "caught": caught,
        "fish": random.choice(fish_types) if caught else None,
        "size": random.choice(sizes) if caught else None,
        "weight_kg": round(random.uniform(0.5, 50), 1) if caught else None,
        "pose_confidence": confidence,
        "action": "cast" if arms_spread else ("hook" if lean > 0.5 else "wait"),
    }


def generate_manga_panels(pose_state: dict, num_panels: int = 4) -> dict:
    """姿勢から漫画コマを生成"""
    if not pose_state.get("detected"):
        return {"panels": [], "reason": "no_pose"}
    
    lean = pose_state.get("lean", 0)
    arms_spread = pose_state.get("arms_spread", False)
    crouch = pose_state.get("crouch", False)
    confidence = pose_state.get("confidence", 0)
    
    # ポーズに基づくコマ割りテンプレート
    templates = {
        "action": ["構え", "溜め", "放出", "決着"],
        "drama": ["日常", "異変", "決意", "行動"],
        "comedy": ["平和", "ハプニング", "大慌て", "オチ"],
    }
    
    # ポーズからジャンル判定
    if arms_spread and lean > 0.3:
        genre = "action"
    elif crouch:
        genre = "drama"
    else:
        genre = "comedy"
    
    panel_titles = templates[genre]
    
    import random
    panels = []
    for i, title in enumerate(panel_titles[:num_panels]):
        panels.append({
            "index": i + 1,
            "title": title,
            "genre": genre,
            "pose_snapshot": {
                "lean": lean,
                "arms_spread": arms_spread,
                "crouch": crouch,
            },
            "suggested_dialogue": f"[{genre}] コマ{i+1}: {title}",
            "effect_lines": random.randint(3, 8),
        })
    
    return {
        "genre": genre,
        "panels": panels,
        "total_panels": len(panels),
        "source_confidence": confidence,
    }


# ── ライフサイクル ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _stop.clear()
    threading.Thread(target=camera_worker, name="mpp5-camera", daemon=True).start()
    yield
    _stop.set()


# ── FastAPI アプリ ────────────────────────────────────────
app = FastAPI(title="mpp5 - Pose Bridge + Fishing + Manga + MMX", lifespan=lifespan)
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
app.mount("/models", StaticFiles(directory=ROOT / "models"), name="models")


# ── ルート定義 ────────────────────────────────────────────

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")

@app.get("/mmx")
async def mmx_viewer() -> FileResponse:
    return FileResponse(WEB_DIR / "mmx.html")


@app.get("/api/state")
async def get_state() -> JSONResponse:
    """現在の姿勢状態を取得（ポーリング用）"""
    with _lock:
        return JSONResponse(dict(_state))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """リアルタイム姿勢ストリーム（WebSocket）"""
    await websocket.accept()
    try:
        while True:
            with _lock:
                payload = dict(_state)
            await websocket.send_json(payload)
            await asyncio.sleep(1 / 30)
    except (WebSocketDisconnect, RuntimeError):
        return


# ── 釣りルート ────────────────────────────────────────────

class FishRequest(BaseModel):
    pose_state: dict | None = None


@app.post("/api/fishing/cast")
async def fishing_cast(req: FishRequest) -> JSONResponse:
    """キャスト（投げる）"""
    with _lock:
        current = dict(_state) if req.pose_state is None else req.pose_state
    result = generate_fish_catch(current)
    result["action"] = "cast"
    return JSONResponse(result)


@app.post("/api/fishing/hook")
async def fishing_hook(req: FishRequest) -> JSONResponse:
    """アワセ（合わせる）"""
    with _lock:
        current = dict(_state) if req.pose_state is None else req.pose_state
    # アワセ時は lean を強制的に大きくする
    current["lean"] = max(abs(current.get("lean", 0)), 0.7) * (1 if current.get("lean", 0) > 0 else -1)
    result = generate_fish_catch(current)
    result["action"] = "hook"
    return JSONResponse(result)


@app.post("/api/fishing/reel")
async def fishing_reel(req: FishRequest) -> JSONResponse:
    """リール（巻く）"""
    with _lock:
        current = dict(_state) if req.pose_state is None else req.pose_state
    result = generate_fish_catch(current)
    result["action"] = "reel"
    return JSONResponse(result)


@app.get("/api/fishing/status")
async def fishing_status() -> JSONResponse:
    """釣り状態取得"""
    with _lock:
        current = dict(_state)
    return JSONResponse({
        "ready": current.get("detected", False),
        "pose": current,
    })


# ── 漫画化ルート ──────────────────────────────────────────

class MangaRequest(BaseModel):
    num_panels: int = 4
    pose_state: dict | None = None


@app.post("/api/manga/generate")
async def manga_generate(req: MangaRequest) -> JSONResponse:
    """漫画コマ生成"""
    with _lock:
        current = dict(_state) if req.pose_state is None else req.pose_state
    result = generate_manga_panels(current, req.num_panels)
    return JSONResponse(result)


@app.post("/api/manga/panel")
async def manga_single_panel(
    panel_index: int,
    req: MangaRequest
) -> JSONResponse:
    """単一コマ生成"""
    with _lock:
        current = dict(_state) if req.pose_state is None else req.pose_state
    result = generate_manga_panels(current, req.num_panels)
    if 0 <= panel_index < len(result["panels"]):
        return JSONResponse(result["panels"][panel_index])
    raise HTTPException(404, "Panel not found")


@app.get("/api/manga/templates")
async def manga_templates() -> JSONResponse:
    """利用可能なテンプレート一覧"""
    return JSONResponse({
        "templates": {
            "action": ["構え", "溜め", "放出", "決着"],
            "drama": ["日常", "異変", "決意", "行動"],
            "comedy": ["平和", "ハプニング", "大慌て", "オチ"],
            "horror": ["静寂", "予兆", "恐怖", "絶望"],
            "romance": ["出会い", "ときめき", "すれ違い", "結ばれ"],
        },
        "default_panels": 4,
        "max_panels": 8,
    })


# ── ヘルスチェック ────────────────────────────────────────

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "camera": _state.get("camera")})


if __name__ == "__main__":
    import uvicorn
    print("mpp5 web display: http://127.0.0.1:8765")
    print(f"Processing OSC output: {OSC_HOST}:{OSC_PORT}/UDP")
    print("API endpoints:")
    print("  GET  /api/state           - 現在の姿勢状態")
    print("  WS   /ws                  - リアルタイム姿勢ストリーム")
    print("  POST /api/fishing/cast    - キャスト")
    print("  POST /api/fishing/hook    - アワセ")
    print("  POST /api/fishing/reel    - リール")
    print("  GET  /api/fishing/status  - 釣り状態")
    print("  POST /api/manga/generate  - 漫画生成")
    print("  POST /api/manga/panel     - 単一コマ生成")
    print("  GET  /api/manga/templates - テンプレート一覧")
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="info")