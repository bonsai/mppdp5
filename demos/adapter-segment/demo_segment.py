"""
Segment Adapter Demo - Extract segmentation masks from video using mppdp5 adapters.

Usage:
    python demo_segment.py --input video.mp4 --output ./work/mask.png
    python demo_segment.py --input video.mp4 --output ./work/mask.png --model mediapipe
    python demo_segment.py --input video.mp4 --output ./work/mask.png --model sam
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters import SegmentAdapter, AdapterConfig


async def run_segment_demo(args):
    """Run segmentation demo."""
    # Create adapter
    adapter = SegmentAdapter()
    
    # Configure
    config = AdapterConfig(
        mode="video",
        segmentation_model=args.model,
        mask_output_format=args.format,
        protocol="files" if args.format in ("png", "npy") else "jsonl",
        output_format="png",
        model_complexity=args.model_complexity,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
        device=args.device,
    )
    
    # SAM-specific config
    if args.model == "sam":
        config.extra["sam_model_type"] = args.sam_model
        config.extra["sam_checkpoint"] = args.sam_checkpoint
    
    adapter.prepare(config)
    
    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing: {args.input}")
    print(f"Output directory: {output_path.parent}")
    print(f"Model: {args.model}")
    if args.model == "sam":
        print(f"SAM model: {args.sam_model}")
        print(f"SAM checkpoint: {args.sam_checkpoint}")
    print("-" * 50)
    
    frame_count = 0
    async for output in adapter.process_video(args.input, str(output_path), config):
        frame_count += 1
        
        if not output.success:
            print(f"Frame {output.frame_index}: ERROR - {output.error}")
            continue
        
        if frame_count % 30 == 0:
            print(f"Frame {frame_count}: mask_shape={output.mask_shape} mask_path={output.mask_path}")
    
    adapter.cleanup()
    print(f"\nDone! Processed {frame_count} frames total.")
    print(f"Masks saved to: {output_path.parent}")


def main():
    parser = argparse.ArgumentParser(description="mppdp5 Segment Adapter Demo")
    parser.add_argument("--input", "-i", required=True, help="Input video file path")
    parser.add_argument("--output", "-o", required=True, help="Output mask file path (directory used for video)")
    parser.add_argument("--model", choices=["mediapipe", "sam"], default="mediapipe",
                        help="Segmentation model")
    parser.add_argument("--format", choices=["png", "npy"], default="png",
                        help="Mask output format")
    parser.add_argument("--model-complexity", type=int, choices=[0, 1], default=1,
                        help="MediaPipe model complexity (0 or 1 for selfie segmentation)")
    parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu",
                        help="Device for SAM (cuda/mps require PyTorch)")
    parser.add_argument("--sam-model", default="vit_b", help="SAM model type (vit_b, vit_l, vit_h)")
    parser.add_argument("--sam-checkpoint", help="Path to SAM checkpoint file")
    parser.add_argument("--max-frames", type=int, default=None, help="Maximum frames to process")
    parser.add_argument("--skip-frames", type=int, default=0, help="Skip N frames between processing")
    
    args = parser.parse_args()
    
    # Validate input
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    if args.model == "sam" and not args.sam_checkpoint:
        print("Warning: SAM checkpoint not specified. Will try default locations.")
    
    asyncio.run(run_segment_demo(args))


if __name__ == "__main__":
    main()