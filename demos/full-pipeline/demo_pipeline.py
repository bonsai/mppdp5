"""
Full Pipeline Demo - Run contour + pose + segment adapters in sequence.

This demonstrates the video2storyboard pipeline concept using mppdp5 adapters.

Usage:
    python demo_pipeline.py --input video.mp4 --output-dir ./work/pipeline
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters import ContourAdapter, PoseAdapter, SegmentAdapter, AdapterConfig


async def run_pipeline_demo(args):
    """Run full pipeline demo."""
    work_dir = Path(args.output_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # Stage 1: Contour
    print("=" * 60)
    print("STAGE 1: Contour Extraction")
    print("=" * 60)
    
    contour_adapter = ContourAdapter()
    contour_config = AdapterConfig(
        mode="video",
        contour_mode=args.contour_mode,
        edge_method=args.edge_method,
        protocol="jsonl",
        output_format="jsonl",
        model_complexity=args.model_complexity,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
    )
    contour_adapter.prepare(contour_config)
    
    contour_output = work_dir / "contour.jsonl"
    frame_count = 0
    
    async for output in contour_adapter.process_video(args.input, str(contour_output), contour_config):
        frame_count += 1
        with open(contour_output, "a", encoding="utf-8") as f:
            data = {
                "stage_id": output.stage_id,
                "frame_index": output.frame_index,
                "timestamp": output.timestamp,
                "success": output.success,
                "points": output.points,
                "connections": output.connections,
                "image_width": output.image_width,
                "image_height": output.image_height,
            }
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        if frame_count % 30 == 0:
            print(f"  Frame {frame_count}: {len(output.points)} contour points")
    
    contour_adapter.cleanup()
    print(f"Contour done: {frame_count} frames -> {contour_output}")
    
    # Stage 2: Pose
    print("\n" + "=" * 60)
    print("STAGE 2: Pose Estimation")
    print("=" * 60)
    
    pose_adapter = PoseAdapter()
    pose_config = AdapterConfig(
        mode="video",
        protocol="jsonl",
        output_format="jsonl",
        model_complexity=args.model_complexity,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
    )
    pose_adapter.prepare(pose_config)
    
    pose_output = work_dir / "pose.jsonl"
    frame_count = 0
    
    async for output in pose_adapter.process_video(args.input, str(pose_output), pose_config):
        frame_count += 1
        with open(pose_output, "a", encoding="utf-8") as f:
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
                "metadata": output.metadata,
            }
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        if frame_count % 30 == 0:
            status = "OK" if output.success else "NO POSE"
            print(f"  Frame {frame_count}: {status} conf={output.confidence:.3f}")
    
    pose_adapter.cleanup()
    print(f"Pose done: {frame_count} frames -> {pose_output}")
    
    # Stage 3: Segmentation
    print("\n" + "=" * 60)
    print("STAGE 3: Segmentation")
    print("=" * 60)
    
    segment_adapter = SegmentAdapter()
    segment_config = AdapterConfig(
        mode="video",
        segmentation_model=args.segment_model,
        mask_output_format="png",
        protocol="files",
        output_format="png",
        model_complexity=1,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
        device=args.device,
    )
    if args.segment_model == "sam":
        segment_config.extra["sam_model_type"] = args.sam_model
        segment_config.extra["sam_checkpoint"] = args.sam_checkpoint
    
    segment_adapter.prepare(segment_config)
    
    mask_dir = work_dir / "masks"
    mask_dir.mkdir(parents=True, exist_ok=True)
    frame_count = 0
    
    async for output in segment_adapter.process_video(args.input, str(mask_dir / "mask.png"), segment_config):
        frame_count += 1
        if frame_count % 30 == 0:
            print(f"  Frame {frame_count}: mask saved to {output.mask_path}")
    
    segment_adapter.cleanup()
    print(f"Segmentation done: {frame_count} frames -> {mask_dir}/")
    
    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Output directory: {work_dir}")
    print(f"  - contour.jsonl: {contour_output}")
    print(f"  - pose.jsonl:    {pose_output}")
    print(f"  - masks/:        {mask_dir}/")
    print("\nNext steps:")
    print(f"  - Feed contour.jsonl to Processing renderer")
    print(f"  - Use pose.jsonl for action recognition")
    print(f"  - Combine contour + masks for manga rendering")


def main():
    parser = argparse.ArgumentParser(description="mppdp5 Full Pipeline Demo")
    parser.add_argument("--input", "-i", required=True, help="Input video file path")
    parser.add_argument("--output-dir", "-o", required=True, help="Output directory for all stages")
    
    # Contour options
    parser.add_argument("--contour-mode", choices=["landmarks", "edges", "both"], default="landmarks")
    parser.add_argument("--edge-method", choices=["canny", "sobel", "laplacian"], default="canny")
    
    # Common options
    parser.add_argument("--model-complexity", type=int, choices=[0, 1, 2], default=1)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--skip-frames", type=int, default=0)
    
    # Segmentation options
    parser.add_argument("--segment-model", choices=["mediapipe", "sam"], default="mediapipe")
    parser.add_argument("--sam-model", default="vit_b")
    parser.add_argument("--sam-checkpoint", help="Path to SAM checkpoint")
    parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    
    args = parser.parse_args()
    
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    asyncio.run(run_pipeline_demo(args))


if __name__ == "__main__":
    main()