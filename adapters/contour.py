"""
Contour Adapter - Extracts outline/edge lines from video frames.

Supports two modes:
1. landmark-based: Uses MediaPipe pose landmarks to draw body contour lines
2. edge-based: Uses OpenCV Canny/Sobel/Laplacian edge detection

Output: JSONL stream of ContourOutput with normalized line coordinates.
"""

from __future__ import annotations
import asyncio
import base64
import cv2
import numpy as np
from pathlib import Path
from typing import AsyncIterator, Optional, List, Tuple
from dataclasses import dataclass

from .base import BaseAdapter, AdapterConfig, StageOutput, ContourOutput
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarkerOptions, RunningMode

from .base import (
    BaseAdapter, AdapterConfig, StageOutput, ContourOutput, 
)


# MediaPipe Pose landmark connections for body contour
BODY_CONTOUR_CONNECTIONS = [
    # Face outline
    (0, 1), (1, 2), (2, 3), (3, 7),  # nose to left eye to left ear
    (0, 4), (4, 5), (5, 6), (6, 8),  # nose to right eye to right ear
    # Torso
    (11, 12), (11, 23), (12, 24), (23, 24),  # shoulders to hips
    # Arms
    (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),  # left arm
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),  # right arm
    # Legs
    (23, 25), (25, 27), (27, 29), (27, 31),  # left leg
    (24, 26), (26, 28), (28, 30), (28, 32),  # right leg
]


class ContourAdapter(BaseAdapter):
    """Extracts contour lines from video using MediaPipe landmarks or edge detection."""
    
    @property
    def stage_id(self) -> str:
        return "contour"
    
    @property
    def provider_name(self) -> str:
        return "mppdp5-contour"
    
    def _initialize(self) -> None:
        cfg = self._config
        if not cfg:
            return
        
        if cfg.contour_mode in ("landmarks", "both"):
            self._pose = vision.PoseLandmarker.create_from_options(
                PoseLandmarkerOptions(
                    base_options=BaseOptions(
                        model_asset_path=str(Path(__file__).parent.parent / "models" / "pose_landmarker_lite.task"),
                        delegate=BaseOptions.Delegate.CPU,
                    ),
                    running_mode=RunningMode.IMAGE if cfg.mode == "image" else RunningMode.VIDEO,
                    min_pose_detection_confidence=cfg.min_detection_confidence,
                    min_pose_presence_confidence=cfg.min_tracking_confidence,
                    min_tracking_confidence=cfg.min_tracking_confidence,
                    output_segmentation_masks=False,
                )
            )
        else:
            self._pose = None
    
    def _extract_landmark_contours(
        self, 
        results: vision.PoseLandmarkerResult, 
        width: int, 
        height: int,
        visibility_threshold: float = 0.35
    ) -> Tuple[List[List[float]], List[List[int]]]:
        """Extract contour lines from MediaPipe pose landmarks."""
        lm = results.pose_landmarks[0]  # First detected person
        
        # Map landmark indices
        lm_to_idx = {}
        points = []
        point_idx = 0
        
        for i, point in enumerate(lm):
            if point.visibility >= visibility_threshold:
                # Normalize to 0-1
                points.append([point.x, point.y])
                lm_to_idx[i] = point_idx
                point_idx += 1
            else:
                lm_to_idx[i] = -1
        
        # Build connections using visible landmarks only
        connections = []
        for start, end in BODY_CONTOUR_CONNECTIONS:
            if start in lm_to_idx and end in lm_to_idx:
                si, ei = lm_to_idx[start], lm_to_idx[end]
                if si >= 0 and ei >= 0:
                    connections.append([si, ei])
        
        return points, connections
    
    def _extract_edges(
        self, 
        frame: np.ndarray, 
        method: str = "canny",
        threshold1: int = 50,
        threshold2: int = 150
    ) -> List[List[float]]:
        """Extract edge contours using OpenCV."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        
        if method == "canny":
            edges = cv2.Canny(gray, threshold1, threshold2)
        elif method == "sobel":
            sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            edges = cv2.magnitude(sobelx, sobely)
            edges = np.uint8(edges / edges.max() * 255) if edges.max() > 0 else edges.astype(np.uint8)
            _, edges = cv2.threshold(edges, 50, 255, cv2.THRESH_BINARY)
        elif method == "laplacian":
            edges = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
            edges = np.uint8(np.absolute(edges) / edges.max() * 255) if edges.max() > 0 else edges.astype(np.uint8)
            _, edges = cv2.threshold(edges, 30, 255, cv2.THRESH_BINARY)
        else:
            raise ValueError(f"Unknown edge method: {method}")
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Convert to normalized point lists
        h, w = frame.shape[:2]
        points = []
        for contour in contours:
            if len(contour) >= 3:  # Minimum for a line
                # Simplify contour
                epsilon = 0.005 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                for pt in approx:
                    x, y = pt[0]
                    points.append([x / w, y / h])
        
        return points
    
    def _render_contour_image(
        self, 
        frame: np.ndarray, 
        points: List[List[float]], 
        connections: Optional[List[List[int]]] = None
    ) -> np.ndarray:
        """Render contour lines on frame for visualization."""
        h, w = frame.shape[:2]
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        
        if connections and len(points) > 0:
            # Draw landmark-based lines
            for start_idx, end_idx in connections:
                if start_idx < len(points) and end_idx < len(points):
                    p1 = (int(points[start_idx][0] * w), int(points[start_idx][1] * h))
                    p2 = (int(points[end_idx][0] * w), int(points[end_idx][1] * h))
                    cv2.line(canvas, p1, p2, (255, 255, 255), 2)
        else:
            # Draw edge contours as connected lines
            if len(points) > 1:
                pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in points], dtype=np.int32)
                cv2.polylines(canvas, [pts], False, (255, 255, 255), 1)
        
        return canvas
    
    async def process_video(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> AsyncIterator[ContourOutput]:
        import cv2
        
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            yield ContourOutput(
                stage_id=self.stage_id, frame_index=-1, timestamp=0,
                success=False, error=f"Cannot open video: {input_path}",
                points=[], image_width=0, image_height=0
            )
            return
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Setup output writer if saving images
        writer = None
        if config.protocol == "files" and config.output_format in ("png", "jpg"):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
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
                
                all_points = []
                all_connections = []
                
                # Landmark-based contours
                if config.contour_mode in ("landmarks", "both") and self._pose:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = self._pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(frame_idx * 1000 / fps if fps > 0 else frame_idx * 1000 // 30))
                    
                    if results.pose_landmarks:
                        points, connections = self._extract_landmark_contours(
                            results.pose_landmarks[0], width, height
                        )
                        all_points.extend(points)
                        if connections:
                            all_connections = connections  # Use landmark connections
                
                # Edge-based contours
                if config.contour_mode in ("edges", "both"):
                    edge_points = self._extract_edges(
                        frame, config.edge_method, 
                        config.canny_threshold1, config.canny_threshold2
                    )
                    all_points.extend(edge_points)
                
                # Prepare output
                image_path = None
                if config.protocol == "files" and config.output_format in ("png", "jpg"):
                    image_path = str(Path(output_path).parent / f"contour_{frame_idx:06d}.{config.output_format}")
                    contour_img = self._render_contour_image(frame, all_points, all_connections)
                    cv2.imwrite(image_path, contour_img)
                
                yield ContourOutput(
                    stage_id=self.stage_id,
                    frame_index=frame_idx,
                    timestamp=timestamp,
                    success=len(all_points) > 0,
                    points=all_points,
                    connections=all_connections if all_connections else None,
                    image_width=width,
                    image_height=height,
                    image_path=image_path,
                    metadata={"fps": fps, "total_frames": total_frames}
                )
                
                frame_idx += 1
                await asyncio.sleep(0)  # Yield control
        
        finally:
            cap.release()
            if writer:
                writer.release()
    
    async def process_image(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> ContourOutput:
        import cv2
        
        frame = cv2.imread(input_path)
        if frame is None:
            return ContourOutput(
                stage_id=self.stage_id, frame_index=0, timestamp=0,
                success=False, error=f"Cannot read image: {input_path}",
                points=[], image_width=0, image_height=0
            )
        
        height, width = frame.shape[:2]
        all_points = []
        all_connections = []
        
        if config.contour_mode in ("landmarks", "both") and self._pose:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), 0)
            
            if results.pose_landmarks:
                points, connections = self._extract_landmark_contours(
                    results.pose_landmarks[0], width, height
                )
                all_points.extend(points)
                if connections:
                    all_connections = connections
        
        if config.contour_mode in ("edges", "both"):
            edge_points = self._extract_edges(
                frame, config.edge_method,
                config.canny_threshold1, config.canny_threshold2
            )
            all_points.extend(edge_points)
        
        image_path = None
        if config.protocol == "files":
            image_path = output_path
            contour_img = self._render_contour_image(frame, all_points, all_connections)
            cv2.imwrite(image_path, contour_img)
        
        return ContourOutput(
            stage_id=self.stage_id,
            frame_index=0,
            timestamp=0,
            success=len(all_points) > 0,
            points=all_points,
            connections=all_connections if all_connections else None,
            image_width=width,
            image_height=height,
            image_path=image_path
        )
    
    async def process_stream(
        self, 
        input_source: str | int, 
        output_sink: str, 
        config: AdapterConfig
    ) -> AsyncIterator[ContourOutput]:
        import cv2
        
        cap = cv2.VideoCapture(input_source)
        if not cap.isOpened():
            yield ContourOutput(
                stage_id=self.stage_id, frame_index=-1, timestamp=0,
                success=False, error=f"Cannot open stream: {input_source}",
                points=[], image_width=0, image_height=0
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
                
                timestamp = frame_idx * (1/30)  # Approximate
                
                all_points = []
                all_connections = []
                
                if config.contour_mode in ("landmarks", "both") and self._pose:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = self._pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), 0)
                    
                    if results.pose_landmarks:
                        points, connections = self._extract_landmark_contours(
                            results.pose_landmarks[0], width, height
                        )
                        all_points.extend(points)
                        if connections:
                            all_connections = connections
                
                if config.contour_mode in ("edges", "both"):
                    edge_points = self._extract_edges(
                        frame, config.edge_method,
                        config.canny_threshold1, config.canny_threshold2
                    )
                    all_points.extend(edge_points)
                
                # Stream output as JSONL to stdout or file
                if output_sink == "stdout":
                    import json, sys
                    out = ContourOutput(
                        stage_id=self.stage_id,
                        frame_index=frame_idx,
                        timestamp=timestamp,
                        success=len(all_points) > 0,
                        points=all_points,
                        connections=all_connections if all_connections else None,
                        image_width=width,
                        image_height=height
                    )
                    sys.stdout.write(json.dumps(self._dataclass_to_dict(out)) + "\n")
                    sys.stdout.flush()
                
                yield ContourOutput(
                    stage_id=self.stage_id,
                    frame_index=frame_idx,
                    timestamp=timestamp,
                    success=len(all_points) > 0,
                    points=all_points,
                    connections=all_connections if all_connections else None,
                    image_width=width,
                    image_height=height
                )
                
                frame_idx += 1
                await asyncio.sleep(0)
        
        finally:
            cap.release()
    
    def cleanup(self) -> None:
        if self._pose:
            self._pose.close()
            self._pose = None