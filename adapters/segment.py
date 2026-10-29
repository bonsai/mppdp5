"""
Segment Adapter - Extracts segmentation masks from video frames.

Supports:
- MediaPipe Tasks ImageSegmenter (Selfie Segmentation)
- SAM (Segment Anything Model) - high quality, slower
- Future: Robust Video Matting (RVM) for video matting

Output: Mask images (PNG) or encoded arrays (JSONL with base64/RLE).
"""

from __future__ import annotations
import asyncio
import base64
import cv2
import mediapipe as mp
import numpy as np
from pathlib import Path
from typing import AsyncIterator, List, Optional
from dataclasses import dataclass

from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import ImageSegmenterOptions, RunningMode

from .base import BaseAdapter, AdapterConfig, StageOutput, SegmentOutput


class SegmentAdapter(BaseAdapter):
    """Extracts segmentation masks from video."""
    
    @property
    def stage_id(self) -> str:
        return "segment"
    
    @property
    def provider_name(self) -> str:
        return "mppdp5-segment"
    
    def _initialize(self) -> None:
        cfg = self._config
        if not cfg:
            return
        
        self._segmentation_model = cfg.segmentation_model
        
        if self._segmentation_model == "mediapipe":
            seg_model_path = str(Path(__file__).parent.parent / "models" / "selfie_segmenter.tflite")
            self._seg = vision.ImageSegmenter.create_from_options(
                ImageSegmenterOptions(
                    base_options=BaseOptions(
                        model_asset_path=seg_model_path,
                        delegate=BaseOptions.Delegate.CPU,
                    ),
                    running_mode=RunningMode.VIDEO,
                    output_category_mask=True,
                )
            )
        elif self._segmentation_model == "sam":
            # Lazy import SAM only when needed
            self._sam_predictor = None
            self._sam_initialized = False
        else:
            raise ValueError(f"Unknown segmentation model: {self._segmentation_model}")
    
    def _init_sam(self) -> None:
        """Initialize SAM predictor lazily."""
        if self._sam_initialized:
            return
        
        try:
            from segment_anything import sam_model_registry, SamPredictor
            import torch
            
            # Default to vit_b for speed, can be configured
            model_type = getattr(self._config, "sam_model_type", "vit_b")
            checkpoint = getattr(self._config, "sam_checkpoint", None)
            
            if checkpoint is None:
                # Try to find in common locations
                import os
                for path in [
                    "sam_vit_b_01ec64.pth",
                    "./sam_vit_b_01ec64.pth",
                    "../sam_vit_b_01ec64.pth",
                    os.path.expanduser("~/.cache/sam_vit_b_01ec64.pth"),
                ]:
                    if os.path.exists(path):
                        checkpoint = path
                        break
            
            if checkpoint is None:
                raise FileNotFoundError(
                    "SAM checkpoint not found. Set sam_checkpoint in config or download "
                    "from https://github.com/facebookresearch/segment-anything"
                )
            
            device = self._config.device if self._config.device != "cpu" else "cpu"
            if device == "mps" and not torch.backends.mps.is_available():
                device = "cpu"
            
            sam = sam_model_registry[model_type](checkpoint=checkpoint)
            sam.to(device=device)
            self._sam_predictor = SamPredictor(sam)
            self._sam_initialized = True
            
        except ImportError:
            raise RuntimeError("segment-anything not installed. Run: pip install segment-anything")
    
    def _get_mediapipe_mask(self, frame: np.ndarray, width: int, height: int, timestamp_ms: int = 0) -> np.ndarray:
        """Get binary mask from MediaPipe Tasks ImageSegmenter."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = self._seg.segment_for_video(mp_image, timestamp_ms)
        mask = results.category_mask.numpy_view()
        # Threshold to binary (1 = person)
        binary_mask = (mask > 0).astype(np.uint8) * 255
        return binary_mask
    
    def _get_sam_mask(self, frame: np.ndarray, prompts: Optional[dict] = None) -> np.ndarray:
        """Get mask from SAM using automatic or prompted segmentation."""
        self._init_sam()
        
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._sam_predictor.set_image(rgb)
        
        if prompts and "points" in prompts:
            # Point prompts
            point_coords = np.array(prompts["points"])
            point_labels = np.array(prompts.get("labels", [1] * len(point_coords)))
            masks, scores, _ = self._sam_predictor.predict(
                point_coords=point_coords,
                point_labels=point_labels,
                multimask_output=True
            )
            # Return best mask
            best_idx = np.argmax(scores)
            return (masks[best_idx] * 255).astype(np.uint8)
        
        elif prompts and "box" in prompts:
            # Box prompt
            box = np.array(prompts["box"])
            masks, scores, _ = self._sam_predictor.predict(
                box=box,
                multimask_output=True
            )
            best_idx = np.argmax(scores)
            return (masks[best_idx] * 255).astype(np.uint8)
        
        else:
            # Automatic mask generation (slow, use for single images)
            from segment_anything import SamAutomaticMaskGenerator
            mask_generator = SamAutomaticMaskGenerator(self._sam_predictor.model)
            masks = mask_generator.generate(rgb)
            if masks:
                # Return largest mask
                largest = max(masks, key=lambda m: m["area"])
                return (largest["segmentation"] * 255).astype(np.uint8)
            return np.zeros(frame.shape[:2], dtype=np.uint8)
    
    def _encode_mask(self, mask: np.ndarray, format: str) -> any:
        """Encode mask for JSONL output."""
        if format == "base64":
            _, buffer = cv2.imencode(".png", mask)
            return base64.b64encode(buffer).decode("utf-8")
        elif format == "rle":
            # Run-length encoding
            from pycocotools import mask as mask_utils
            rle = mask_utils.encode(np.asfortranarray(mask))
            rle["counts"] = rle["counts"].decode("utf-8")
            return rle
        elif format == "npy":
            return mask.tolist()
        return None
    
    def _render_overlay(self, frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Render mask overlay on frame."""
        overlay = frame.copy()
        # Green tint for person
        green = np.zeros_like(frame)
        green[:, :] = (0, 255, 0)
        alpha = 0.4
        mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) / 255.0
        overlay = (overlay * (1 - mask_3ch * alpha) + green * mask_3ch * alpha).astype(np.uint8)
        return overlay
    
    async def process_video(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> AsyncIterator[SegmentOutput]:
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            yield SegmentOutput(
                stage_id=self.stage_id, frame_index=-1, timestamp=0,
                success=False, error=f"Cannot open video: {input_path}",
                mask_path=None, mask_shape=(0, 0)
            )
            return
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
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
                
                # Get mask
                if self._segmentation_model == "mediapipe":
                    mask = self._get_mediapipe_mask(frame, width, height, int(frame_idx * 1000 / fps if fps > 0 else int(frame_idx * 1000 / 30)))
                elif self._segmentation_model == "sam":
                    mask = self._get_sam_mask(frame)
                else:
                    mask = np.zeros((height, width), dtype=np.uint8)
                
                # Save mask PNGs when output_path ends with .png or protocol is files
                mask_path = None
                overlay_path = None
                mask_data = None
                save_mask_png = output_path.endswith(".png") or config.protocol == "files"
                if save_mask_png:
                    output_dir = Path(output_path).parent
                    output_dir.mkdir(parents=True, exist_ok=True)
                    mask_path = str(output_dir / f"mask_{frame_idx:06d}.{config.mask_output_format}")
                    if config.mask_output_format == "png":
                        cv2.imwrite(mask_path, mask)
                    elif config.mask_output_format == "npy":
                        np.save(mask_path.replace(".npy", ""), mask)

                    # Also save overlay
                    if config.output_format in ("png", "jpg"):
                        overlay_path = str(output_dir / f"overlay_{frame_idx:06d}.{config.output_format}")
                        overlay = self._render_overlay(frame, mask)
                        cv2.imwrite(overlay_path, overlay)

                elif config.protocol in ("jsonl", "memory"):
                    mask_data = self._encode_mask(mask, "base64")
                
                yield SegmentOutput(
                    stage_id=self.stage_id,
                    frame_index=frame_idx,
                    timestamp=timestamp,
                    success=True,
                    mask_path=mask_path,
                    mask_data=mask_data,
                    mask_shape=(height, width),
                    classes=["person"],
                    overlay_path=overlay_path,
                    metadata={"fps": fps, "model": self._segmentation_model}
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
    ) -> SegmentOutput:
        frame = cv2.imread(input_path)
        if frame is None:
            return SegmentOutput(
                stage_id=self.stage_id, frame_index=0, timestamp=0,
                success=False, error=f"Cannot read image: {input_path}",
                mask_path=None, mask_shape=(0, 0)
            )
        
        height, width = frame.shape[:2]
        
        if self._segmentation_model == "mediapipe":
            mask = self._get_mediapipe_mask(frame, width, height, int(frame_idx * 1000 / fps if fps > 0 else int(frame_idx * 1000 / 30)))
        elif self._segmentation_model == "sam":
            mask = self._get_sam_mask(frame)
        else:
            mask = np.zeros((height, width), dtype=np.uint8)
        
        mask_path = None
        overlay_path = None
        mask_data = None
        
        if config.protocol == "files":
            mask_path = output_path
            if config.mask_output_format == "png":
                cv2.imwrite(mask_path, mask)
            elif config.mask_output_format == "npy":
                np.save(mask_path.replace(".npy", ""), mask)
            
            if config.output_format in ("png", "jpg"):
                overlay_path = output_path.replace("mask", "overlay")
                overlay = self._render_overlay(frame, mask)
                cv2.imwrite(overlay_path, overlay)
        
        elif config.protocol in ("jsonl", "memory"):
            mask_data = self._encode_mask(mask, "base64")
        
        return SegmentOutput(
            stage_id=self.stage_id,
            frame_index=0,
            timestamp=0,
            success=True,
            mask_path=mask_path,
            mask_data=mask_data,
            mask_shape=(height, width),
            classes=["person"],
            overlay_path=overlay_path
        )
    
    async def process_stream(
        self, 
        input_source: str | int, 
        output_sink: str, 
        config: AdapterConfig
    ) -> AsyncIterator[SegmentOutput]:
        cap = cv2.VideoCapture(input_source)
        if not cap.isOpened():
            yield SegmentOutput(
                stage_id=self.stage_id, frame_index=-1, timestamp=0,
                success=False, error=f"Cannot open stream: {input_source}",
                mask_path=None, mask_shape=(0, 0)
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
                
                if self._segmentation_model == "mediapipe":
                    mask = self._get_mediapipe_mask(frame, width, height, int(frame_idx * 1000 / fps if fps > 0 else int(frame_idx * 1000 / 30)))
                elif self._segmentation_model == "sam":
                    mask = self._get_sam_mask(frame)
                else:
                    mask = np.zeros((height, width), dtype=np.uint8)
                
                mask_data = None
                if output_sink == "stdout":
                    mask_data = self._encode_mask(mask, "base64")
                    import json, sys
                    out = SegmentOutput(
                        stage_id=self.stage_id,
                        frame_index=frame_idx,
                        timestamp=timestamp,
                        success=True,
                        mask_data=mask_data,
                        mask_shape=(height, width),
                        classes=["person"]
                    )
                    sys.stdout.write(json.dumps(self._dataclass_to_dict(out)) + "\n")
                    sys.stdout.flush()
                
                yield SegmentOutput(
                    stage_id=self.stage_id,
                    frame_index=frame_idx,
                    timestamp=timestamp,
                    success=True,
                    mask_data=mask_data,
                    mask_shape=(height, width),
                    classes=["person"]
                )
                
                frame_idx += 1
                await asyncio.sleep(0)
        
        finally:
            cap.release()
    
    def cleanup(self) -> None:
        if hasattr(self, "_seg") and self._seg:
            self._seg.close()
            self._seg = None
        if hasattr(self, "_sam_predictor"):
            self._sam_predictor = None
