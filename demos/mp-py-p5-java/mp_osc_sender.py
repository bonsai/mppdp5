#!/usr/bin/env python3
"""mp_osc_sender.py
MediaPipe Pose Landmarker (Tasks API v1.2+) で骨格を検出し、OSC で Processing に送信する

必要なモデルファイル: models/pose_landmarker_lite.task (自動ダウンロード済み)

送信先: 127.0.0.1:9000
アドレス:
  /mppose/start
  /mppose/landmark  [idx, x, y, z, visibility]  (正規化座標 0-1)
  /mppose/frame     [frame_idx, width, height, fps]
  /mppose/end
"""

import argparse
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from pythonosc import udp_client

# モデルファイルのパス
MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "pose_landmarker_lite.task"


def download_model_if_needed():
    """モデルファイルがなければダウンロード"""
    if MODEL_PATH.exists():
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    import urllib.request
    url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    print(f"Downloading model from {url}...")
    urllib.request.urlretrieve(url, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")


def main():
    download_model_if_needed()

    ap = argparse.ArgumentParser(description="MediaPipe Pose Landmarker -> OSC sender")
    ap.add_argument("--input", default="0", help="0=webcam or path to video")
    ap.add_argument("--ip", default="127.0.0.1", help="OSC target IP")
    ap.add_argument("--port", type=int, default=9000, help="OSC target port")
    ap.add_argument("--model", type=int, default=0, choices=[0, 1], help="0=lite, 1=full (uses same model file)")
    ap.add_argument("--min-det", type=float, default=0.5)
    ap.add_argument("--min-track", type=float, default=0.5)
    ap.add_argument("--mirror", action="store_true", help="mirror for webcam preview")
    args = ap.parse_args()

    src = int(args.input) if args.input.isdigit() else args.input
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"Failed to open input: {args.input}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    client = udp_client.SimpleUDPClient(args.ip, args.port)
    client.send_message("/mppose/start", [time.time(), w, h, fps])
    print(f"[OSC] sending to {args.ip}:{args.port}  (w={w} h={h} fps={fps:.1f})")
    print("Press 'q' to quit preview")

    # MediaPipe Tasks API v1.2+ 初期化
    base_options = BaseOptions(model_asset_path=str(MODEL_PATH))
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        min_pose_detection_confidence=args.min_det,
        min_pose_presence_confidence=args.min_track,
        min_tracking_confidence=args.min_track,
        output_segmentation_masks=False,
    )
    landmarker = vision.PoseLandmarker.create_from_options(options)

    frame_idx = 0
    t_prev = time.time()
    fps_disp = fps
    timestamp_ms = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1

            if args.mirror and isinstance(src, int):
                frame = cv2.flip(frame, 1)

            # MediaPipe 用に RGB 変換
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # タイムスタンプ (ミリ秒)
            timestamp_ms = int(frame_idx * 1000 / fps)

            # 推論実行
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            now = time.time()
            dt = now - t_prev
            t_prev = now
            if dt > 0:
                fps_disp = 0.9 * fps_disp + 0.1 * (1.0 / dt)

            client.send_message("/mppose/frame", [frame_idx, w, h, fps_disp])

            if result.pose_landmarks:
                for i, lm in enumerate(result.pose_landmarks[0]):
                    client.send_message("/mppose/landmark", [i, lm.x, lm.y, lm.z, lm.visibility])

            # プレビュー表示
            vis = frame.copy()
            if result.pose_landmarks:
                # ランドマーク描画
                for lm in result.pose_landmarks[0]:
                    x, y = int(lm.x * w), int(lm.y * h)
                    cv2.circle(vis, (x, y), 3, (0, 255, 0), -1)
                # 接続線描画（主要なもののみ）
                connections = [
                    (0, 1), (1, 2), (2, 3), (3, 7),  # 左顔
                    (0, 4), (4, 5), (5, 6), (6, 8),  # 右顔
                    (9, 10),  # 口
                    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),  # 左腕
                    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),  # 右腕
                    (11, 23), (12, 24), (23, 24),  # 胴体
                    (23, 25), (25, 27), (27, 29), (27, 31),  # 左脚
                    (24, 26), (26, 28), (28, 30), (28, 32),  # 右脚
                ]
                for start, end in connections:
                    if start < len(result.pose_landmarks[0]) and end < len(result.pose_landmarks[0]):
                        lm1 = result.pose_landmarks[0][start]
                        lm2 = result.pose_landmarks[0][end]
                        if lm1.visibility > 0.5 and lm2.visibility > 0.5:
                            x1, y1 = int(lm1.x * w), int(lm1.y * h)
                            x2, y2 = int(lm2.x * w), int(lm2.y * h)
                            cv2.line(vis, (x1, y1), (x2, y2), (0, 180, 255), 2)

            cv2.putText(vis, f"OSC -> {args.ip}:{args.port} | {fps_disp:.0f} fps", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("mp_osc_sender (q: quit)", vis)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        client.send_message("/mppose/end", [frame_idx, time.time()])
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
        print("[OSC] sent /mppose/end")


if __name__ == "__main__":
    main()