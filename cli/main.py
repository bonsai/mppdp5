#!/usr/bin/env python3
"""
mppdp5 CLI - Unified command line interface for mppdp5 adapters.

Usage:
    mppdp5 contour --input video.mp4 --output work/contour.jsonl
    mppdp5 pose --input video.mp4 --output work/pose.jsonl
    mppdp5 segment --input video.mp4 --output work/masks/
    mppdp5 pipeline --input video.mp4 --output-dir work/pipeline/
"""

from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters import ContourAdapter, PoseAdapter, SegmentAdapter, AdapterConfig


async def cmd_contour(args):
    """Contour extraction command."""
    adapter = ContourAdapter()
    config = AdapterConfig(
        mode="video",
        contour_mode=args.mode,
        edge_method=args.edge_method,
        canny_threshold1=args.canny_thresh1,
        canny_threshold2=args.canny_thresh2,
        protocol=args.protocol,
        output_format=args.format,
        model_complexity=args.model_complexity,
        min_detection_confidence=args.min_det,
        min_tracking_confidence=args.min_track,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
    )
    adapter.prepare(config)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"[contour] Input: {args.input}")
    print(f"[contour] Output: {args.output}")
    print(f"[contour] Mode: {args.mode}")
    
    frame_count = 0
    async for output in adapter.process_video(args.input, args.output, config):
        frame_count += 1
        
        if args.protocol == "jsonl":
            import json
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
            with open(args.output, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        if frame_count % 30 == 0:
            status = "OK" if output.success else "FAIL"
            print(f"  Frame {frame_count}: {status} points={len(output.points)}")
    
    adapter.cleanup()
    print(f"[contour] Done: {frame_count} frames")


async def cmd_pose(args):
    """Pose estimation command."""
    adapter = PoseAdapter()
    config = AdapterConfig(
        mode="video",
        protocol=args.protocol,
        output_format=args.format,
        model_complexity=args.model_complexity,
        min_detection_confidence=args.min_det,
        min_tracking_confidence=args.min_track,
        smooth_landmarks=args.smooth,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
    )
    adapter.prepare(config)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"[pose] Input: {args.input}")
    print(f"[pose] Output: {args.output}")
    print(f"[pose] Model: {args.model_complexity}")
    
    frame_count = 0
    async for output in adapter.process_video(args.input, args.output, config):
        frame_count += 1
        
        if args.protocol == "jsonl":
            import json
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
            with open(args.output, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        if frame_count % 30 == 0:
            status = "OK" if output.success else "NO POSE"
            print(f"  Frame {frame_count}: {status} conf={output.confidence:.3f}")
    
    adapter.cleanup()
    print(f"[pose] Done: {frame_count} frames")


async def cmd_segment(args):
    """Segmentation command."""
    adapter = SegmentAdapter()
    config = AdapterConfig(
        mode="video",
        segmentation_model=args.model,
        mask_output_format=args.mask_format,
        protocol=args.protocol,
        output_format=args.format,
        model_complexity=1,
        max_frames=args.max_frames,
        skip_frames=args.skip_frames,
        device=args.device,
    )
    if args.model == "sam":
        config.extra["sam_model_type"] = args.sam_model
        config.extra["sam_checkpoint"] = args.sam_checkpoint
    
    adapter.prepare(config)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"[segment] Input: {args.input}")
    print(f"[segment] Output: {args.output}")
    print(f"[segment] Model: {args.model}")
    
    frame_count = 0
    async for output in adapter.process_video(args.input, args.output, config):
        frame_count += 1
        
        if frame_count % 30 == 0:
            print(f"  Frame {frame_count}: mask={output.mask_path}")
    
    adapter.cleanup()
    print(f"[segment] Done: {frame_count} frames")


async def cmd_pipeline(args):
    """Full pipeline command."""
    work_dir = Path(args.output_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("MPPDP5 FULL PIPELINE")
    print("=" * 60)
    
    # Stage 1: Contour
    print("\n[1/3] Contour Extraction")
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
        import json
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
            print(f"  Frame {frame_count}: {len(output.points)} points")
    contour_adapter.cleanup()
    print(f"  -> {contour_output} ({frame_count} frames)")
    
    # Stage 2: Pose
    print("\n[2/3] Pose Estimation")
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
        import json
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
    print(f"  -> {pose_output} ({frame_count} frames)")
    
    # Stage 3: Segmentation
    print("\n[3/3] Segmentation")
    segment_adapter = SegmentAdapter()
    segment_config = AdapterConfig(
        mode="video",
        segmentation_model=args.segment_model,
        mask_output_format="png",
        protocol="files",
        output_format="png",
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
            print(f"  Frame {frame_count}: mask saved")
    segment_adapter.cleanup()
    print(f"  -> {mask_dir}/ ({frame_count} frames)")
    
    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Output directory: {work_dir}")
    print(f"  contour.jsonl: {contour_output}")
    print(f"  pose.jsonl:    {pose_output}")
    print(f"  masks/:        {mask_dir}/")


def main():
    parser = argparse.ArgumentParser(
        prog="mppdp5",
        description="mppdp5 - MediaPipe Pose Processing Pipeline Adapters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mppdp5 contour -i video.mp4 -o work/contour.jsonl --mode landmarks
  mppdp5 pose -i video.mp4 -o work/pose.jsonl --model-complexity 2
  mppdp5 segment -i video.mp4 -o work/masks/ --model mediapipe
  mppdp5 pipeline -i video.mp4 -o work/pipeline/
        """
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Common arguments
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input", "-i", required=True, help="Input video file")
    common.add_argument("--max-frames", type=int, default=None, help="Max frames to process")
    common.add_argument("--skip-frames", type=int, default=0, help="Skip N frames")
    common.add_argument("--model-complexity", type=int, choices=[0, 1, 2], default=1)
    
    # Contour subcommand
    contour_parser = subparsers.add_parser("contour", parents=[common], help="Extract contour lines")
    contour_parser.add_argument("--output", "-o", required=True, help="Output JSONL file")
    contour_parser.add_argument("--mode", choices=["landmarks", "edges", "both"], default="landmarks")
    contour_parser.add_argument("--edge-method", choices=["canny", "sobel", "laplacian"], default="canny")
    contour_parser.add_argument("--canny-thresh1", type=int, default=50)
    contour_parser.add_argument("--canny-thresh2", type=int, default=150)
    contour_parser.add_argument("--protocol", choices=["jsonl", "files"], default="jsonl")
    contour_parser.add_argument("--format", choices=["jsonl", "png", "jpg"], default="jsonl")
    contour_parser.add_argument("--min-det", type=float, default=0.5, dest="min_det")
    contour_parser.add_argument("--min-track", type=float, default=0.5, dest="min_track")
    contour_parser.set_defaults(func=cmd_contour)
    
    # Pose subcommand
    pose_parser = subparsers.add_parser("pose", parents=[common], help="Extract pose keypoints")
    pose_parser.add_argument("--output", "-o", required=True, help="Output JSONL file")
    pose_parser.add_argument("--protocol", choices=["jsonl", "files"], default="jsonl")
    pose_parser.add_argument("--format", choices=["jsonl", "png", "jpg"], default="jsonl")
    pose_parser.add_argument("--min-det", type=float, default=0.5, dest="min_det")
    pose_parser.add_argument("--min-track", type=float, default=0.5, dest="min_track")
    pose_parser.add_argument("--smooth", action="store_true", default=True)
    pose_parser.add_argument("--no-smooth", action="store_false", dest="smooth")
    pose_parser.set_defaults(func=cmd_pose)
    
    # Segment subcommand
    segment_parser = subparsers.add_parser("segment", parents=[common], help="Extract segmentation masks")
    segment_parser.add_argument("--output", "-o", required=True, help="Output directory for masks")
    segment_parser.add_argument("--model", choices=["mediapipe", "sam"], default="mediapipe")
    segment_parser.add_argument("--mask-format", choices=["png", "npy"], default="png")
    segment_parser.add_argument("--protocol", choices=["jsonl", "files"], default="files")
    segment_parser.add_argument("--format", choices=["png", "jpg"], default="png")
    segment_parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    segment_parser.add_argument("--sam-model", default="vit_b")
    segment_parser.add_argument("--sam-checkpoint", help="Path to SAM checkpoint")
    segment_parser.set_defaults(func=cmd_segment)
    
    # Pipeline subcommand
    pipeline_parser = subparsers.add_parser("pipeline", parents=[common], help="Run full pipeline")
    pipeline_parser.add_argument("--output-dir", "-o", required=True, help="Output directory for all stages")
    pipeline_parser.add_argument("--contour-mode", choices=["landmarks", "edges", "both"], default="landmarks")
    pipeline_parser.add_argument("--edge-method", choices=["canny", "sobel", "laplacian"], default="canny")
    pipeline_parser.add_argument("--segment-model", choices=["mediapipe", "sam"], default="mediapipe")
    pipeline_parser.add_argument("--sam-model", default="vit_b")
    pipeline_parser.add_argument("--sam-checkpoint", help="Path to SAM checkpoint")
    pipeline_parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    pipeline_parser.set_defaults(func=cmd_pipeline)
    
    args = parser.parse_args()
    
    # Validate input
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()