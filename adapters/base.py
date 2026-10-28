"""
Base adapter protocol and data models for mppdp5 adapters.

Defines the unified interface that video2storyboard expects from all providers.
"""

from __future__ import annotations
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional, Union, Literal
from typing_extensions import Protocol


@dataclass
class AdapterConfig:
    """Common configuration for all adapters."""
    # Input/Output
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    
    # Processing options
    mode: Literal["video", "image", "stream"] = "video"
    device: str = "cpu"  # "cpu", "cuda", "mps"
    
    # Output format
    protocol: Literal["jsonl", "files", "memory"] = "jsonl"
    output_format: Literal["jsonl", "png", "jpg", "npy"] = "jsonl"
    
    # MediaPipe specific
    model_complexity: int = 1
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    smooth_landmarks: bool = True
    enable_segmentation: bool = False
    
    # Contour specific
    contour_mode: Literal["landmarks", "edges", "both"] = "landmarks"
    edge_method: Literal["canny", "sobel", "laplacian"] = "canny"
    canny_threshold1: int = 50
    canny_threshold2: int = 150
    
    # Segmentation specific
    segmentation_model: Literal["mediapipe", "sam"] = "mediapipe"
    mask_output_format: Literal["png", "npy", "rle"] = "png"
    
    # Performance
    batch_size: int = 1
    max_frames: Optional[int] = None
    skip_frames: int = 0
    
    # Extra provider-specific options
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageOutput:
    """Base output from a processing stage."""
    stage_id: str
    frame_index: int
    timestamp: float
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContourOutput(StageOutput):
    """Contour/outline extraction output."""
    # For protocol=jsonl: list of [x, y] points normalized 0-1
    # For contour_mode=landmarks: MediaPipe landmark connections as lines
    # For contour_mode=edges: Canny/Sobel edge pixel coordinates
    points: list[list[float]] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    connections: Optional[list[list[int]]] = None
    image_path: Optional[str] = None


@dataclass
class PoseOutput(StageOutput):
    """Pose/keypoint detection output."""
    # MediaPipe 33 landmarks + optional interpreted hip center
    # Each landmark: [x, y, z, visibility] normalized 0-1
    landmarks: list[list[float]] = field(default_factory=list)
    landmark_names: list[str] = field(default_factory=list)
    
    # Derived pose features
    lean: float = 0.0
    arms_spread: bool = False
    crouch: bool = False
    confidence: float = 0.0
    
    # For protocol=files: path to rendered pose image
    image_path: Optional[str] = None


@dataclass
class SegmentOutput(StageOutput):
    """Segmentation mask output."""
    # For protocol=files: path to mask image
    mask_path: Optional[str] = None
    
    # For protocol=jsonl/memory: encoded mask data
    mask_data: Optional[Any] = None  # base64 PNG, RLE, or numpy array
    mask_shape: tuple[int, int] = (0, 0)  # height, width
    classes: list[str] = field(default_factory=list)  # class names for multi-class
    
    # For protocol=files: path to visualized overlay
    overlay_path: Optional[str] = None


class StageAdapter(Protocol):
    """Protocol for all stage adapters."""
    
    @property
    def stage_id(self) -> str:
        """Unique stage identifier (e.g., 'contour', 'pose', 'segment')."""
        ...
    
    @property
    def provider_name(self) -> str:
        """Provider name for registry (e.g., 'mppdp5-contour')."""
        ...
    
    def prepare(self, config: AdapterConfig) -> None:
        """Initialize adapter with configuration."""
        ...
    
    async def process_video(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> AsyncIterator[StageOutput]:
        """Process video file, yield output per frame."""
        ...
    
    async def process_image(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> StageOutput:
        """Process single image."""
        ...
    
    async def process_stream(
        self, 
        input_source: Union[str, int],  # file path, camera index, or RTSP URL
        output_sink: str,  # output path or "stdout" for JSONL streaming
        config: AdapterConfig
    ) -> AsyncIterator[StageOutput]:
        """Process live stream (camera/RTSP)."""
        ...
    
    def cleanup(self) -> None:
        """Release resources."""
        ...


class BaseAdapter(ABC):
    """Abstract base class with common functionality."""
    
    def __init__(self):
        self._config: Optional[AdapterConfig] = None
        self._initialized = False
    
    @property
    @abstractmethod
    def stage_id(self) -> str:
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass
    
    def prepare(self, config: AdapterConfig) -> None:
        self._config = config
        self._initialize()
        self._initialized = True
    
    @abstractmethod
    def _initialize(self) -> None:
        """Provider-specific initialization."""
        pass
    
    @abstractmethod
    async def process_video(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> AsyncIterator[StageOutput]:
        pass
    
    @abstractmethod
    async def process_image(
        self, 
        input_path: str, 
        output_path: str, 
        config: AdapterConfig
    ) -> StageOutput:
        pass
    
    @abstractmethod
    async def process_stream(
        self, 
        input_source: Union[str, int],
        output_sink: str,
        config: AdapterConfig
    ) -> AsyncIterator[StageOutput]:
        pass
    
    def cleanup(self) -> None:
        pass
    
    def _write_jsonl(self, output_path: str, outputs: list[StageOutput]) -> None:
        """Write outputs as JSONL file."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for out in outputs:
                # Convert dataclass to dict, handling nested dataclasses
                data = self._dataclass_to_dict(out)
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
    
    def _dataclass_to_dict(self, obj: Any) -> Any:
        """Recursively convert dataclass to dict."""
        if hasattr(obj, "__dataclass_fields__"):
            return {k: self._dataclass_to_dict(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._dataclass_to_dict(v) for v in obj]
        elif isinstance(obj, dict):
            return {k: self._dataclass_to_dict(v) for k, v in obj.items()}
        else:
            return obj
    
    def _get_video_info(self, path: str) -> tuple[int, int, float, int]:
        """Get video info: (width, height, fps, frame_count)."""
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {path}")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return width, height, fps, frame_count