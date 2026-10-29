#!/usr/bin/env python3
"""manga_cam.py — リアルタイム漫画線画カメラ (MediaPipe Tasks API 版)

組み合わせパイプライン（全部コードのみ・古典処理が核）:
  1. 線画: bilateral + Canny の輪郭
  2. 強調: エッジ強さ×輪郭長で「重要な線は濃く、他は薄く」
  3. 手書き調: 輪郭の点列を震わせて薄く重ね描き（ラインボイル制御つき）
  4. 人物: MediaPipe Tasks PoseLandmarker の骨格を常に濃い別レイヤーで
  5. 建物: セグメンテーション（任意・重いので数フレームに1回だけ計算して再利用）
           建物マスクに触れる線は重要度ブースト
  6. トーン: 階調を量子化して紙の下にうっすら敷く

使い方:
  python manga_cam.py                 # Webカメラ
  python manga_cam.py --input in.mp4  # 動画ファイル
  python manga_cam.py --buildings     # 建物セグメンテーションON（初回DLあり）
  python manga_cam.py --save out.mp4  # 書き出し

キー: q=終了 / p=骨格ON-OFF / b=建物ON-OFF / t=トーンON-OFF / s=フレーム保存
"""
import argparse
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarkerOptions, RunningMode
import numpy as np


# ---------- 手書き調: 輪郭を震わせる ----------
def jitter(points, amp, smooth, rng):
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    n = len(pts)
    k = cv2.getGaussianKernel(smooth, 0).flatten()
    dx = np.convolve(rng.normal(0, amp, n), k, mode="same")[:n]
    dy = np.convolve(rng.normal(0, amp, n), k, mode="same")[:n]
    pts[:, 0] += dx
    pts[:, 1] += dy
    return pts.astype(np.int32)


# ---------- 建物セグメンテーション（任意・遅延読み込み・結果を再利用） ----------
class BuildingMask:
    def __init__(self):
        self.seg = None
        self.mask = None
        self.failed = False

    def _load(self):
        from transformers import pipeline
        # ADE20K 学習済み（building クラスあり）
        self.seg = pipeline(
            "image-segmentation",
            model="facebook/mask2former-swin-small-ade-semantic",
        )

    def update(self, frame_bgr):
        if self.failed:
            return
        try:
            if self.seg is None:
                self._load()
            from PIL import Image
            pil = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
            result = self.seg(pil)
            mask = None
            for r in result:
                if r["label"] == "building":
                    m = np.array(r["mask"]) > 0
                    mask = m if mask is None else (mask | m)
            if mask is not None:
                self.mask = mask.astype(np.uint8)
        except Exception as e:  # モデルが無い環境では静かに無効化
            print(f"[buildings disabled] {e}")
            self.failed = True


# ---------- メイン描画 ----------
def render(frame, wobble=2.0, frame_idx=0, boil=3,
           pose_layer=None, building_mask=None, tone=True):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    smooth_gray = cv2.bilateralFilter(gray, 9, 75, 75)
    edges = cv2.Canny(smooth_gray, 50, 150)

    # エッジ強さマップ
    gx = cv2.Sobel(smooth_gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(smooth_gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    mag /= (mag.max() + 1e-6)

    h, w = gray.shape
    paper = np.full((h, w, 3), (250, 248, 242), np.uint8)

    # トーン: 階調を4段に量子化して薄く敷く
    if tone:
        levels = (smooth_gray.astype(np.float32) / 255.0 * 3).round() / 3.0
        tone_img = (250 - (1.0 - levels) * 70).astype(np.uint8)
        tone_img = cv2.cvtColor(tone_img, cv2.COLOR_GRAY2BGR)
        paper = cv2.addWeighted(paper, 0.55, tone_img, 0.45, 0)

    noise = np.random.default_rng(0).normal(0, 3, (h, w, 1)).repeat(3, axis=2)
    canvas = np.clip(paper.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    # 震えのパターンは boil フレームごとに更新（コマ落とし感）
    rng = np.random.default_rng(1000 + frame_idx // boil)

    for cnt in contours:
        pts = cnt.reshape(-1, 2)
        if len(pts) < 5:
            continue
        xs = np.clip(pts[:, 0], 0, w - 1)
        ys = np.clip(pts[:, 1], 0, h - 1)
        strength = float(mag[ys, xs].mean())
        importance = strength * 0.7 + min(len(pts) / 200.0, 1.0) * 0.3

        # 建物マスクに触れる線はブースト
        if building_mask is not None:
            if building_mask[ys, xs].mean() > 0.5:
                importance = min(importance + 0.45, 1.0)

        shade = int(205 - importance * 175)          # 30（濃）..205（薄）
        thickness = 2 if importance > 0.55 else 1
        passes = 3 if importance > 0.4 else 1
        for _ in range(passes):
            shaken = jitter(pts, amp=wobble, smooth=15, rng=rng)
            cv2.polylines(canvas, [shaken.reshape(-1, 1, 2)], False,
                          (shade, shade, shade), thickness, cv2.LINE_AA)

    # 人物の骨格は常に濃く（別レイヤー）
    if pose_layer is not None:
        mask = np.any(pose_layer > 0, axis=2)
        canvas[mask] = (30, 30, 30)
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="0", help="0=カメラ / 動画パス")
    ap.add_argument("--save", default="", help="書き出し先 mp4")
    ap.add_argument("--wobble", type=float, default=2.0)
    ap.add_argument("--buildings", action="store_true")
    ap.add_argument("--seg-every", type=int, default=10, help="建物マスクの更新間隔フレーム")
    args = ap.parse_args()

    src = int(args.input) if args.input.isdigit() else args.input
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit("入力を開けませんでした")

    # MediaPipe Tasks PoseLandmarker（あれば使う）
    pose = None
    try:
        model_path = Path(__file__).parent.parent / "models" / "pose_landmarker_lite.task"
        base_options = BaseOptions(
            model_asset_path=str(model_path),
            delegate=BaseOptions.Delegate.CPU,
        )
        pose_options = PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.VIDEO,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_segmentation_masks=False,
        )
        pose = vision.PoseLandmarker.create_from_options(pose_options)
    except Exception as e:
        print(f"[pose disabled] {e}")

    buildings = BuildingMask() if args.buildings else None
    show_pose, show_tone = True, True

    writer = None
    if args.save:
        fps0 = cap.get(cv2.CAP_PROP_FPS) or 30
        w0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h0 = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(args.save,
                                 cv2.VideoWriter_fourcc(*"mp4v"), fps0, (w0, h0))

    idx, t_prev, fps_disp = 0, time.time(), 0.0
    frame_timestamp = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1

        # 建物マスクは重いので間引いて更新
        if buildings is not None and idx % args.seg_every == 1:
            buildings.update(frame)

        # 骨格レイヤー（真っ黒キャンバスに白で描いてマスク化）
        pose_layer = None
        if pose is not None and show_pose:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            frame_timestamp = int(frame_timestamp + 1000 / 30)  # ~30fps timestamps
            results = pose.detect_for_video(mp_image, frame_timestamp)
            if results.pose_landmarks:
                h_frame, w_frame = frame.shape[:2]
                pose_layer = np.zeros_like(frame)
                lms = results.pose_landmarks[0]
                # Draw connections
                connections = [
                    (11, 12), (11, 13), (13, 15), (15, 17),
                    (12, 14), (14, 16), (16, 18),
                    (11, 23), (12, 24), (23, 24),
                    (23, 25), (25, 27), (24, 26), (26, 28),
                    (0, 11), (0, 12),
                ]
                for start_idx, end_idx in connections:
                    if start_idx < len(lms) and end_idx < len(lms):
                        p1 = lms[start_idx]
                        p2 = lms[end_idx]
                        if p1.visibility > 0.35 and p2.visibility > 0.35:
                            x1, y1 = int(p1.x * w_frame), int(p1.y * h_frame)
                            x2, y2 = int(p2.x * w_frame), int(p2.y * h_frame)
                            cv2.line(pose_layer, (x1, y1), (x2, y2), (255, 255, 255), 2)
                            cv2.circle(pose_layer, (x1, y1), 2, (255, 255, 255), -1)
                            cv2.circle(pose_layer, (x2, y2), 2, (255, 255, 255), -1)

        out = render(frame, wobble=args.wobble, frame_idx=idx,
                     pose_layer=pose_layer,
                     building_mask=(buildings.mask if buildings else None),
                     tone=show_tone)

        now = time.time()
        fps_disp = 0.9 * fps_disp + 0.1 * (1.0 / max(now - t_prev, 1e-6))
        t_prev = now
        cv2.putText(out, f"{fps_disp:.0f} fps", (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 120, 120), 2, cv2.LINE_AA)

        if writer is not None:
            writer.write(out)
        cv2.imshow("manga_cam (q:quit p:pose b:buildings t:tone s:save)", out)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("p"):
            show_pose = not show_pose
        elif key == ord("t"):
            show_tone = not show_tone
        elif key == ord("b"):
            if buildings is None:
                buildings = BuildingMask()
            else:
                buildings = None
        elif key == ord("s"):
            cv2.imwrite(f"manga_{idx:06d}.png", out)

    cap.release()
    if writer is not None:
        writer.release()
    cv2.destroyAllWindows()
    if pose:
        pose.close()


if __name__ == "__main__":
    main()
