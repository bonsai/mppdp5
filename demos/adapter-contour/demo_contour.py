"""
Contour Adapter Demo - Extract body contour lines from video using mppdp5 adapters.

Usage:
    python demo_contour.py --input video.mp4 --output ./work/contour.jsonl
    python demo_contour.py --input video.mp4 --output ./work/contour.jsonl --mode landmarks
    python demo_contour.py --input video.mp4 --output ./work/contour.jsonl --mode edges
    python demo_contour.py --input video.mp4 --output ./work/contour.jsonl --mode both
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters import ContourAdapter, AdapterConfig


async def run_contour_demo(args):
    """Run contour extraction demo."""
    # Create adapter
    adapter = ContourAdapter()
    
    # Configure
    config = AdapterConfig(
        mode="video",
        contour_mode=args.mode,
        edge_method=args.edge_method,
        canny_threshold1=args.canny_thresh1,
        canny_threshold2=args.canny_thresh2,
        protocol="jsonl",
        output_format="jsonl",
        model_complexity=args.model_complexity,
        min_detection_confidence=args.min_detection_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
    )
    
    adapter.prepare(config)
    
    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing: {args.input}")
    print(f"Output: {args.output}")
    print(f"Mode: {args.mode}")
    print(f"Model complexity: {args.model_complexity}")
    print("-" * 50)
    
    frame_count = 0
    async for output in adapter.process_video(args.input, args.output, config):
        frame_count += 1
        
        if not output.success:
            print(f"Frame {output.frame_index}: ERROR - {output.error}")
            continue
        
        # Write JSONL line
        with open(args.output, "a", encoding="utf-8") as f:
            # Convert to dict for JSON serialization
            data = {
                "stage_id": output.stage_id,
                "frame_index": output.frame_index,
                "timestamp": output.timestamp,
                "success": output.success,
                "points": output.points,
                "connections": output.connections,
                "image_width": output.image_width,
                "image_height": output.image_height,
                "image_path": output.image_path,
                "metadata": output.metadata,
            }
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        if frame_count % 30 == 0:
            print(f"Processed {frame_count} frames... (latest: {len(output.points)} points)")
    
    adapter.cleanup()
    print(f"\nDone! Processed {frame_count} frames total.")
    print(f"Output written to: {args.output}")


def main():
    parser = argparse.ArgumentParser(description="mppdp5 Contour Adapter Demo")
    parser.add_argument("--input", "-i", required=True, help="Input video file path")
    parser.add_argument("--output", "-o", required=True, help="Output JSONL file path")
    parser.add_argument("--mode", choices=["landmarks", "edges", "both"], default="landmarks",
                        help="Contour extraction mode")
    parser.add_argument("--edge-method", choices=["canny", "sobel", "laplacian"], default="canny",
                        help="Edge detection method (for edges mode)")
    parser.add_argument("--canny-thresh1", type=int, default=50, help="Canny threshold 1")
    parser.add_argument("--canny-thresh2", type=int, default=150, help="Canny threshold 2")
    parser.add_argument("--model-complexity", type=int, choices=[0, 1, 2], default=1,
                        help="MediaPipe model complexity")
    parser.add_argument("--min-detection-confidence", type=float, default=0.5)
    parser.add_argument("--min-tracking-confidence", type=float, default=0.5)
    parser.add_argument("--max-frames", type=int, default=None, help="Maximum frames to process")
    parser.add_argument("--skip-frames", type=int, default=0, help="Skip N frames between processing")
    
    args = parser.parse_args()
    
    # Validate input
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    asyncio.run(run_contour_demo(args))


if __name__ == "__main__":
    main()