#!/usr/bin/env python3
"""Python-only manga/contour renderer using MediaPipe Tasks API.

Modes:
  contour - clean outline (convex hull of pose landmarks)
  manga   - contour + inner lines + screentone halftone
  pose    - standard skeleton + landmarks
  segment - selfie segmentation mask overlay

Keys: 1=contour, 2=manga, 3=pose, 4=segment, q=quit, m=mirror toggle
"""

import argparse
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from pathlib import Path

MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "pose_landmarker_lite.task"
SEGMENT_MODEL = Path(__file__).parent.parent.parent / "models" / "selfie_segmenter.tflite"


def download_models():
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MODEL_PATH.exists():
        import urllib.request
        url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
        print(f"Downloading pose model from {url}...")
        urllib.request.urlretrieve(url, MODEL_PATH)
        print(f"Saved to {MODEL_PATH}")
    
    # Selfie segmenter model - use correct URL
    if not SEGMENT_MODEL.exists():
        import urllib.request
        url = "https://storage.googleapis.com/mediapipe-models/selfie_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite"
        print(f"Downloading segmentation model from {url}...")
        try:
            urllib.request.urlretrieve(url, SEGMENT_MODEL)
            print(f"Saved to {SEGMENT_MODEL}")
        except Exception as e:
            print(f"Segmentation model download failed (optional): {e}")


def convex_hull(points):
    """Graham scan convex hull."""
    if len(points) < 3:
        return points
    pts = sorted(points, key=lambda p: (p[0], p[1]))
    
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    
    return lower[:-1] + upper[:-1]


def draw_contour(frame, landmarks, w, h, color=(0, 255, 0), thickness=2):
    """Draw body contour from landmarks."""
    # Key landmark indices for body outline
    indices = [0, 2, 5, 7, 8, 11, 13, 15, 23, 25, 27, 29, 31, 24, 26, 28, 30, 32, 12, 14, 16, 4, 3, 6]
    
    points = []
    for idx in indices:
        if idx < len(landmarks):
            lm = landmarks[idx]
            if lm.visibility > 0.4:
                points.append((int(lm.x * w), int(lm.y * h)))
    
    if len(points) < 3:
        return
    
    hull = convex_hull(points)
    hull = np.array(hull, dtype=np.int32)
    cv2.polylines(frame, [hull], True, color, thickness)


def draw_screentone(frame, landmarks, w, h, color=(0, 255, 0)):
    """Draw manga-style halftone shading."""
    indices = [0, 2, 5, 7, 8, 11, 13, 15, 23, 25, 27, 29, 31, 24, 26, 28, 30, 32, 12, 14, 16, 4, 3, 6]
    
    points = []
    for idx in indices:
        if idx < len(landmarks):
            lm = landmarks[idx]
            if lm.visibility > 0.4:
                points.append((lm.x * w, lm.y * h))
    
    if len(points) < 3:
        return
    
    hull = convex_hull(points)
    xs = [p[0] for p in hull]
    ys = [p[1] for p in hull]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    cx = (min_x + max_x) / 2
    cy = min_y
    hip_y = max_y
    shoulder_w = max_x - min_x
    
    for y in range(int(cy), int(hip_y), 4):
        ratio = (y - cy) / max(1, hip_y - cy)
        width = shoulder_w * (1 - ratio * 0.3)
        left = int(cx - width / 2)
        right = int(cx + width / 2)
        for x in range(left, right, 8):
            if (x + y) % 16 < 4:
                cv2.circle(frame, (x, y), 1, color, -1)


def draw_inner_contours(frame, landmarks, w, h, color=(128, 128, 128), thickness=1):
    """Draw inner body lines (torso, joints)."""
    connections = [
        (11, 12), (11, 23), (12, 24), (23, 24),  # torso
        (13, 14), (25, 26), (27, 28),  # knees/elbows
    ]
    for a, b in connections:
        if a < len(landmarks) and b < len(landmarks):
            lm1, lm2 = landmarks[a], landmarks[b]
            if lm1.visibility > 0.5 and lm2.visibility > 0.5:
                x1, y1 = int(lm1.x * w), int(lm1.y * h)
                x2, y2 = int(lm2.x * w), int(lm2.y * h)
                cv2.line(frame, (x1, y1), (x2, y2), color, thickness)


def draw_face_contour(frame, landmarks, w, h, color=(0, 255, 0), thickness=2):
    """Draw face contour."""
    face_indices = [0, 2, 5, 7, 8, 4, 3, 6]
    points = []
    for idx in face_indices:
        if idx < len(landmarks):
            lm = landmarks[idx]
            if lm.visibility > 0.5:
                points.append((int(lm.x * w), int(lm.y * h)))
    
    if len(points) >= 3:
        hull = convex_hull(points)
        hull = np.array(hull, dtype=np.int32)
        cv2.polylines(frame, [hull], True, color, thickness)


def draw_skeleton(frame, landmarks, w, h, color=(0, 180, 255), thickness=2):
    """Draw standard pose skeleton."""
    connections = [
        (0, 1), (1, 2), (2, 3), (3, 7),
        (0, 4), (4, 5), (5, 6), (6, 8),
        (9, 10),
        (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),
        (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),
        (11, 23), (12, 24), (23, 24),
        (23, 25), (25, 27), (27, 29), (27, 31),
        (24, 26), (26, 28), (28, 30), (28, 32),
    ]
    for a, b in connections:
        if a < len(landmarks) and b < len(landmarks):
            lm1, lm2 = landmarks[a], landmarks[b]
            if lm1.visibility > 0.5 and lm2.visibility > 0.5:
                x1, y1 = int(lm1.x * w), int(lm1.y * h)
                x2, y2 = int(lm2.x * w), int(lm2.y * h)
                cv2.line(frame, (x1, y1), (x2, y2), color, thickness)
    
    for lm in landmarks:
        if lm.visibility > 0.5:
            x, y = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)


def main():
    parser = argparse.ArgumentParser(description="Python manga/contour renderer")
    parser.add_argument("--input", default="0", help="0=webcam or video path")
    parser.add_argument("--mode", default="manga", choices=["contour", "manga", "pose", "segment"])
    parser.add_argument("--mirror", action="store_true", help="mirror webcam")
    parser.add_argument("--min-det", type=float, default=0.5)
    parser.add_argument("--min-track", type=float, default=0.5)
    args = parser.parse_args()

    download_models()

    src = int(args.input) if args.input.isdigit() else args.input
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"Failed to open: {args.input}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # Initialize MediaPipe
    base_options = BaseOptions(model_asset_path=str(MODEL_PATH))
    pose_options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        min_pose_detection_confidence=args.min_det,
        min_pose_presence_confidence=args.min_track,
        min_tracking_confidence=args.min_track,
        output_segmentation_masks=True,
    )
    landmarker = vision.PoseLandmarker.create_from_options(pose_options)

    segmenter = None
    if args.mode == "segment":
        if SEGMENT_MODEL.exists():
            seg_options = vision.ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_path=str(SEGMENT_MODEL)),
                running_mode=vision.RunningMode.VIDEO,
                output_category_mask=True,
            )
            segmenter = vision.ImageSegmenter.create_from_options(seg_options)
        else:
            print("Segmentation model not found, falling back to pose")
            args.mode = "pose"

    mode = args.mode
    mirror = args.mirror
    frame_idx = 0

    print("Keys: 1=contour  2=manga  3=pose  4=segment  q=quit  m=mirror")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1

            if mirror and isinstance(src, int):
                frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(frame_idx * 1000 / fps)

            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            # Create output frame
            if mode == "segment" and segmenter:
                seg_result = segmenter.segment_for_video(mp_image, timestamp_ms)
                mask = seg_result.category_mask.numpy_view()
                mask = (mask > 0).astype(np.uint8) * 255
                mask = cv2.resize(mask, (w, h))
                output = frame.copy()
                overlay = np.zeros_like(frame)
                overlay[mask > 0] = (0, 255, 100)
                output = cv2.addWeighted(output, 0.7, overlay, 0.3, 0)
            else:
                output = np.zeros_like(frame) if mode != "pose" else frame.copy()

            if result.pose_landmarks:
                lms = result.pose_landmarks[0]

                if mode in ("contour", "manga"):
                    # Dark background for manga
                    if mode == "manga":
                        output.fill(20)  # Dark gray
                    else:
                        output.fill(0)   # Black
                    
                    draw_contour(output, lms, w, h, (0, 255, 0), 3)
                    draw_inner_contours(output, lms, w, h, (100, 100, 100), 1)
                    draw_face_contour(output, lms, w, h, (0, 255, 0), 2)
                    
                    if mode == "manga":
                        draw_screentone(output, lms, w, h, (80, 80, 80))

                elif mode == "pose":
                    draw_skeleton(output, lms, w, h)

                elif mode == "segment" and not segmenter:
                    draw_skeleton(output, lms, w, h)

            cv2.putText(output, f"Mode: {mode.upper()}  (1/2/3/4 to switch)", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(output, f"Mirror: {'ON' if mirror else 'OFF'}  (m to toggle)", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow("Python Manga/Contour Renderer", output)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('1'):
                mode = "contour"
                print("Mode: CONTOUR")
            elif key == ord('2'):
                mode = "manga"
                print("Mode: MANGA")
            elif key == ord('3'):
                mode = "pose"
                print("Mode: POSE")
            elif key == ord('4'):
                if segmenter:
                    mode = "segment"
                    print("Mode: SEGMENT")
                else:
                    print("Segmentation model not available")
            elif key == ord('m'):
                mirror = not mirror
                print(f"Mirror: {'ON' if mirror else 'OFF'}")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
        if segmenter:
            segmenter.close()


if __name__ == "__main__":
    main()