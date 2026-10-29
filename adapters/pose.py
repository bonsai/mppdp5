"""
Pose Adapter - Extracts MediaPipe pose keypoints and derived features.

Output: JSONL stream of PoseOutput with 33 landmarks + interpreted features.
Compatible with existing mppdp5 OSC output format.
"""

from __future__ import annotations
import asyncio
import cv2
import numpy as np
from pathlib import Path
from typing import AsyncIterator, List, Optional, Any
import math

import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarkerOptions, RunningMode

from .base import BaseAdapter, AdapterConfig, StageOutput, PoseOutput


# MediaPipe Pose Landmark indices
class PoseLandmark:
    NOSE = 0
    LEFT_EYE_INNER = 1
    LEFT_EYE = 2
    LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4
    RIGHT_EYE = 5
    RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7
    RIGHT_EAR = 8
    MOUTH_LEFT = 9
    MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_PINKY = 17
    RIGHT_PINKY = 18
    LEFT_INDEX = 19
    RIGHT_INDEX = 20
    LEFT_THUMB = 21
    RIGHT_THUMB = 22
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28
    LEFT_HEEL = 29
    RIGHT_HEEL = 30
    LEFT_FOOT_INDEX = 31
    RIGHT_FOOT_INDEX = 32


LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]


class PoseAdapter(BaseAdapter):
    """Extracts pose keypoints and derived features from video."""
    
    @property
    def stage_id(self) -> str:
        return "pose"
    
    @property
    def provider_name(self) -> str:
        return "mppdp5-pose"
    
    def _initialize(self) -> None:
        cfg = self._config
        if not cfg:
            return
        
        base_options = BaseOptions(
            model_asset_path=str(Path(__file__).parent.parent / "models" / "pose_landmarker_lite.task"),
            delegate=BaseOptions.Delegate.CPU,
        )
        self._pose = vision.PoseLandmarker.create_from_options(
            PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=RunningMode.VIDEO,
                min_pose_detection_confidence=cfg.min_detection_confidence,
                min_pose_presence_confidence=cfg.min_tracking_confidence,
                min_tracking_confidence=cfg.min_tracking_confidence,
                output_segmentation_masks=False,
            )
        )
        
        # For speed calculation
        self._prev_left_wrist: Optional[tuple] = None
        self._prev_right_wrist: Optional[tuple] = None
        self._hip_x_history: List[float] = []
    
    def _extract_landmarks(
        self, 
        landmarks: vision.PoseLandmarkerResult, 
        width: int, 
        height: int,
        visibility_threshold: float = 0.35
    ) -> tuple[List[List[float]], float, bool, bool, float]:
        """Extract landmarks and compute derived features.
        
        Returns: (landmarks_list, lean, arms_spread, crouch, confidence)
        landmarks_list: 33 * 4 floats [x, y, z, visibility] or [-1, -1, -1, -1]
        """
        lm = landmarks.pose_landmarks[0]  # First detected person
        
        # Build flat landmark array (compatible with OSC format)
        landmarks_flat = []
        for i in range(33):
            point = lm[i]
            if point.visibility >= visibility_threshold:
                landmarks_flat.extend([point.x, point.y, point.z, point.visibility])
            else:
                landmarks_flat.extend([-1.0, -1.0, -1.0, -1.0])
        
        # Key landmarks for derived features
        left_sh = lm[PoseLandmark.LEFT_SHOULDER]
        right_sh = lm[PoseLandmark.RIGHT_SHOULDER]
        left_wrist = lm[PoseLandmark.LEFT_WRIST]
        right_wrist = lm[PoseLandmark.RIGHT_WRIST]
        left_hip = lm[PoseLandmark.LEFT_HIP]
        right_hip = lm[PoseLandmark.RIGHT_HIP]
        left_knee = lm[PoseLandmark.LEFT_KNEE]
        right_knee = lm[PoseLandmark.RIGHT_KNEE]
        
        # Confidence from key landmarks
        required = [left_sh, right_sh, left_hip, right_hip]
        confidence = sum(p.visibility for p in required) / len(required)
        
        # Lean (shoulder center x deviation from center)
        shoulder_center_x = (left_sh.x + right_sh.x) / 2.0
        lean = max(-1.0, min(1.0, (shoulder_center_x - 0.5) * 2.4))
        
        # Arms spread (wrist span vs shoulder width)
        wrist_span = abs(left_wrist.x - right_wrist.x)
        shoulder_width = max(abs(left_sh.x - right_sh.x), 0.05)
        arms_spread = (
            left_wrist.visibility > 0.45
            and right_wrist.visibility > 0.45
            and wrist_span / shoulder_width > 2.0
        )
        
        # Crouch (hip below midpoint of shoulder-knee)
        hip_center_y = (left_hip.y + right_hip.y) / 2.0
        knee_center_y = (left_knee.y + right_knee.y) / 2.0
        shoulder_center_y = (left_sh.y + right_sh.y) / 2.0
        crouch = hip_center_y > (shoulder_center_y + knee_center_y) / 2.0 + 0.015
        
        return landmarks_flat, lean, arms_spread, crouch, confidence
    
    def _calculate_speeds(
        self, 
        left_wrist: Any, 
        right_wrist: Any,
        width: int, height: int
    ) -> tuple[float, float]:
        """Calculate wrist speeds."""
        left_pos = (left_wrist.x * width, left_wrist.y * height) if left_wrist.visibility > 0.35 else None
        right_pos = (right_wrist.x * width, right_wrist.y * height) if right_wrist.visibility > 0.35 else None
        
        left_speed = 0.0
        right_speed = 0.0
        
        if left_pos and self._prev_left_wrist:
            left_speed = math.hypot(left_pos[0] - self._prev_left_wrist[0], left_pos[1] - self._prev_left_wrist[1])
        if right_pos and self._prev_right_wrist:
            right_speed = math.hypot(right_pos[0] - self._prev_right_wrist[0], right_pos[1] - self._prev_right_wrist[1])
        
        self._prev_left_wrist = left_pos
        self._prev_right_wrist = right_pos
        
        return left_speed, right_speed
    
    def _calculate_hip_sway(self, left_hip, right_hip, width: int) -> float:
        """Calculate hip sway from hip center movement history."""
        if left_hip.visibility >= 0.35 and right_hip.visibility >= 0.35:
            hip_x = (left_hip.x + right_hip.x) / 2.0
            self._hip_x_history.append(hip_x)
            if len(self._hip_x_history) > 20:
                self._hip_x_history.pop(0)
            
            if len(self._hip_x_history) >= 5:
                mean_x = sum(self._hip_x_history) / len(self._hip_x_history)
                variance = sum((x - mean_x) ** 2 for x in self._hip_x_history) / len(self._hip_x_history)
                hip_sway = min(math.sqrt(variance) * width / 25.0, 1.5)
                return hip_sway if hip_sway >= 0.03 else 0.0
        return 0.0
    
    def _render_pose_image(self, frame: np.ndarray, landmarks) -> np.ndarray:
        """Render pose landmarks on frame using OpenCV."""
        annotated = frame.copy()
        # Draw landmarks as circles
        for lm in landmarks:
            if lm.visibility > 0.5:
                x, y = int(lm.x * frame.shape[1]), int(lm.y * frame.shape[0])
                cv2.circle(annotated, (x, y), 3, (0, 255, 0), -1)
        # Draw connections
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
        for start_idx, end_idx in connections:
            if start_idx < len(landmarks) and end_idx < len(landmarks):
                lm1 = landmarks[start_idx]
                lm2 = landmarks[end_idx]
                if lm1.visibility > 0.5 and lm2.visibility > 0.5:
                    x1, y1 = int(lm1.x * frame.shape[1]), int(lm1.y * frame.shape[0])
                    x2, y2 = int(lm2.x * frame.shape[1]), int(lm2.y * frame.shape[0])
                    cv2.line(annotated, (x1, y1), (x2, y2), (0, 180, 255), 2)
        return annotated
    
    async def process_video(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> AsyncIterator[PoseOutput]:
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            yield PoseOutput(
                stage_id=self.stage_id, frame_index=-1, timestamp=0,
                success=False, error=f"Cannot open video: {input_path}",
                landmarks=[], landmark_names=LANDMARK_NAMES
            )
            return
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        frame_idx = 0
        skip = config.skip_frames
        max_frames = config.max_frames or total_frames
        
        try:
            while frame_idx < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                
                if skip > 0 and frame_idx % (skip + 1) != 0:
                    frame_idx += 1
                    continue
                
                timestamp = frame_idx / fps if fps > 0 else frame_idx * (1/30)
                
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int(frame_idx * 1000 / fps) if fps > 0 else 0
                results = self._pose.detect_for_video(mp_image, timestamp_ms)
                
                if not results.pose_landmarks:
                    yield PoseOutput(
                        stage_id=self.stage_id,
                        frame_index=frame_idx,
                        timestamp=timestamp,
                        success=False,
                        landmarks=[-1.0] * 132,  # 33 * 4
                        landmark_names=LANDMARK_NAMES,
                        confidence=0.0
                    )
                    frame_idx += 1
                    await asyncio.sleep(0)
                    continue
                
                landmarks_flat, lean, arms_spread, crouch, confidence = self._extract_landmarks(
                    results, width, height
                )
                
                # Speeds
                lms = results.pose_landmarks[0]
                left_speed, right_speed = self._calculate_speeds(
                    lms[PoseLandmark.LEFT_WRIST],
                    lms[PoseLandmark.RIGHT_WRIST],
                    width, height
                )
                
                # Hip sway
                hip_sway = self._calculate_hip_sway(
                    lms[PoseLandmark.LEFT_HIP],
                    lms[PoseLandmark.RIGHT_HIP],
                    width
                )
                
                # Render image if needed
                image_path = None
                if config.protocol == "files" and config.output_format in ("png", "jpg"):
                    image_path = str(Path(output_path).parent / f"pose_{frame_idx:06d}.{config.output_format}")
                    annotated = self._render_pose_image(frame, results.pose_landmarks)
                    cv2.imwrite(image_path, annotated)
                
                yield PoseOutput(
                    stage_id=self.stage_id,
                    frame_index=frame_idx,
                    timestamp=timestamp,
                    success=True,
                    landmarks=landmarks_flat,
                    landmark_names=LANDMARK_NAMES,
                    lean=lean,
                    arms_spread=arms_spread,
                    crouch=crouch,
                    confidence=confidence,
                    image_path=image_path,
                    metadata={
                        "fps": fps,
                        "total_frames": total_frames,
                        "left_speed": left_speed,
                        "right_speed": right_speed,
                        "hip_sway": hip_sway,
                    }
                )
                
                frame_idx += 1
                await asyncio.sleep(0)
        
        finally:
            cap.release()
    
    async def process_image(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> PoseOutput:
        frame = cv2.imread(input_path)
        if frame is None:
            return PoseOutput(
                stage_id=self.stage_id, frame_index=0, timestamp=0,
                success=False, error=f"Cannot read image: {input_path}",
                landmarks=[], landmark_names=LANDMARK_NAMES
            )
        
        height, width = frame.shape[:2]
        
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = self._pose.detect_for_video(mp_image, 0)
        
        if not results.pose_landmarks:
            return PoseOutput(
                stage_id=self.stage_id, frame_index=0, timestamp=0,
                success=False, landmarks=[-1.0] * 132, landmark_names=LANDMARK_NAMES,
                confidence=0.0
            )
        
        landmarks_flat, lean, arms_spread, crouch, confidence = self._extract_landmarks(
            results.pose_landmarks, width, height
        )
        
        image_path = None
        if config.protocol == "files":
            image_path = output_path
            annotated = self._render_pose_image(frame, results.pose_landmarks)
            cv2.imwrite(image_path, annotated)
        
        return PoseOutput(
            stage_id=self.stage_id,
            frame_index=0,
            timestamp=0,
            success=True,
            landmarks=landmarks_flat,
            landmark_names=LANDMARK_NAMES,
            lean=lean,
            arms_spread=arms_spread,
            crouch=crouch,
            confidence=confidence,
            image_path=image_path
        )
    
    async def process_stream(
        self, 
        input_source: str | int, 
        output_sink: str, 
        config: AdapterConfig
    ) -> AsyncIterator[PoseOutput]:
        cap = cv2.VideoCapture(input_source)
        if not cap.isOpened():
            yield PoseOutput(
                stage_id=self.stage_id, frame_index=-1, timestamp=0,
                success=False, error=f"Cannot open stream: {input_source}",
                landmarks=[], landmark_names=LANDMARK_NAMES
            )
            return
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        frame_idx = 0
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    await asyncio.sleep(0.01)
                    continue
                
                timestamp = frame_idx * (1/30)
                
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                results = self._pose.detect_for_video(mp_image, int(frame_idx * 1000 / 30))
                
                if not results.pose_landmarks:
                    yield PoseOutput(
                        stage_id=self.stage_id,
                        frame_index=frame_idx,
                        timestamp=timestamp,
                        success=False,
                        landmarks=[-1.0] * 132,
                        landmark_names=LANDMARK_NAMES,
                        confidence=0.0
                    )
                    frame_idx += 1
                    await asyncio.sleep(0)
                    continue
                
                landmarks_flat, lean, arms_spread, crouch, confidence = self._extract_landmarks(
                    results.pose_landmarks, width, height
                )
                
                left_speed, right_speed = self._calculate_speeds(
                    lms[PoseLandmark.LEFT_WRIST],
                    lms[PoseLandmark.RIGHT_WRIST],
                    width, height
                )
                
                hip_sway = self._calculate_hip_sway(
                    lms[PoseLandmark.LEFT_HIP],
                    lms[PoseLandmark.RIGHT_HIP],
                    width
                )
                
                # Stream to stdout as JSONL (compatible with existing OSC format)
                if output_sink == "stdout":
                    import json, sys
                    out = PoseOutput(
                        stage_id=self.stage_id,
                        frame_index=frame_idx,
                        timestamp=timestamp,
                        success=True,
                        landmarks=landmarks_flat,
                        landmark_names=LANDMARK_NAMES,
                        lean=lean,
                        arms_spread=arms_spread,
                        crouch=crouch,
                        confidence=confidence,
                        metadata={
                            "left_speed": left_speed,
                            "right_speed": right_speed,
                            "hip_sway": hip_sway,
                        }
                    )
                    sys.stdout.write(json.dumps(self._dataclass_to_dict(out)) + "\n")
                    sys.stdout.flush()
                
                yield PoseOutput(
                    stage_id=self.stage_id,
                    frame_index=frame_idx,
                    timestamp=timestamp,
                    success=True,
                    landmarks=landmarks_flat,
                    landmark_names=LANDMARK_NAMES,
                    lean=lean,
                    arms_spread=arms_spread,
                    crouch=crouch,
                    confidence=confidence,
                    metadata={
                        "left_speed": left_speed,
                        "right_speed": right_speed,
                        "hip_sway": hip_sway,
                    }
                )
                
                frame_idx += 1
                await asyncio.sleep(0)
        
        finally:
            cap.release()
    
    def cleanup(self) -> None:
        if self._pose:
            self._pose.close()
            self._pose = None