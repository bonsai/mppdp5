"""
Pose Adapter Demo - Extract pose keypoints and derived features from video using mppdp5 adapters.

Usage:
    python demo_pose.py --input video.mp4 --output ./work/pose.jsonl
    python demo_pose.py --input video.mp4 --output ./work/pose.jsonl --model-complexity 2
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters import PoseAdapter, AdapterConfig


async def run_pose_demo(args):
    """Run pose extraction demo."""
    # Create adapter
    adapter = PoseAdapter()
    
    # Configure
    config = AdapterConfig(
        mode="video",
        protocol="jsonl",
        output_format="jsonl",
        model_complexity=args.model_complexity,
        min_detection_confidence=args.min_detection_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
        smooth_landmarks=args.smooth,
        enable_segmentation=False,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
    )
    
    adapter.prepare(config)
    
    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing: {args.input}")
    print(f"Output: {args.output}")
    print(f"Model complexity: {args.model_complexity}")
    print(f"Smooth landmarks: {args.smooth}")
    print("-" * 50)
    
    frame_count = 0
    async for output in adapter.process_video(args.input, args.output, config):
        frame_count += 1
        
        if not output.success:
            print(f"Frame {output.frame_index}: No pose detected (confidence: {output.confidence:.3f})")
            # Still write the frame with empty landmarks
            pass
        
        # Write JSONL line
        with open(args.output, "a", encoding="utf-8") as f:
            data = {
                "stage_id": output.stage_id,
                "frame_index": output.frame_index,
                "timestamp": output.timestamp,
                "success": output.success,
                "landmarks": output.landmarks,
                "landmark_names": output.landmark_names,
                "lean": output.lean,
                "arms_spread": output.arms_spread,
                "crouch": output.crouch,
                "confidence": output.confidence,
                "image_path": output.image_path,
                "metadata": output.metadata,
            }
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        if frame_count % 30 == 0:
            status = "OK" if output.success else "NO POSE"
            print(f"Frame {frame_count}: {status} | confidence={output.confidence:.3f} lean={output.lean:.3f} arms_spread={output.arms_spread} crouch={output.crouch}")
    
    adapter.cleanup()
    print(f"\nDone! Processed {frame_count} frames total.")
    print(f"Output written to: {args.output}")


def main():
    parser = argparse.ArgumentParser(description="mppdp5 Pose Adapter Demo")
    parser.add_argument("--input", "-i", required=True, help="Input video file path")
    parser.add_argument("--output", "-o", required=True, help="Output JSONL file path")
    parser.add_argument("--model-complexity", type=int, choices=[0, 1, 2], default=1,
                        help="MediaPipe model complexity (0=lite, 1=full, 2=heavy)")
    parser.add_argument("--min-detection-confidence", type=float, default=0.5)
    parser.add_argument("--min-tracking-confidence", type=float, default=0.5)
    parser.add_argument("--smooth", action="store_true", default=True, help="Enable landmark smoothing")
    parser.add_argument("--no-smooth", action="store_false", dest="smooth", help="Disable landmark smoothing")
    parser.add_argument("--max-frames", type=int, default=None, help="Maximum frames to process")
    parser.add_argument("--skip-frames", type=int, default=0, help="Skip N frames between processing")
    
    args = parser.parse_args()
    
    # Validate input
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    asyncio.run(run_pose_demo(args))


if __name__ == "__main__":
    main()