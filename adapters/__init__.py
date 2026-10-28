"""
mppdp5 Adapters - Unified interface for video2storyboard pipeline integration.

Provides standardized adapters for:
- contour: Outline/edge extraction (JSONL stream of line coordinates)
- pose: Keypoint/landmark detection (JSONL stream of landmarks)
- segment: Segmentation masks (image files or encoded arrays)

All adapters follow the same protocol:
- process_video(input_path, output_path, config) -> AsyncIterator[StageOutput]
- process_image(input_path, output_path, config) -> StageOutput
- process_stream(input_source, output_sink, config) -> AsyncIterator[StageOutput]
"""

from .base import StageAdapter, StageOutput, ContourOutput, PoseOutput, SegmentOutput, AdapterConfig
from .contour import ContourAdapter
from .pose import PoseAdapter
from .segment import SegmentAdapter

__all__ = [
    "StageAdapter",
    "StageOutput",
    "ContourOutput",
    "PoseOutput",
    "SegmentOutput",
    "AdapterConfig",
    "ContourAdapter",
    "PoseAdapter",
    "SegmentAdapter",
]

# Provider registry for video2storyboard router
PROVIDER_REGISTRY = {
    "mppdp5-contour": ContourAdapter,
    "mppdp5-pose": PoseAdapter,
    "mppdp5-segment": SegmentAdapter,
}