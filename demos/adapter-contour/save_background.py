"""
Save Background Frame - Capture and save a background frame from camera or video.

Usage:
    python save_background.py --source 0 --output background.png
    python save_background.py --source video.mp4 --output background.png --frame 100
"""

from __future__ import annotations
import argparse
import cv2
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Save background frame from camera or video")
    parser.add_argument("--source", "-s", default="0", help="Camera index (0,1,...) or video file path")
    parser.add_argument("--output", "-o", required=True, help="Output image path")
    parser.add_argument("--frame", "-f", type=int, default=0, help="Frame number to capture (for video)")
    parser.add_argument("--width", type=int, default=640, help="Camera width")
    parser.add_argument("--height", type=int, default=480, help="Camera height")
    parser.add_argument("--warmup", type=int, default=30, help="Warmup frames to discard (camera)")
    
    args = parser.parse_args()
    
    # Open source
    if args.source.isdigit():
        cap = cv2.VideoCapture(int(args.source), cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        is_camera = True
    else:
        cap = cv2.VideoCapture(args.source)
        is_camera = False
    
    if not cap.isOpened():
        print(f"Error: Could not open source: {args.source}")
        sys.exit(1)
    
    try:
        if is_camera:
            # Warmup: discard first frames for auto-exposure/white-balance
            print(f"Warming up camera (discarding {args.warmup} frames)...")
            for _ in range(args.warmup):
                cap.read()
            
            print("Capturing background frame...")
            ret, frame = cap.read()
        else:
            # Seek to frame
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_idx = min(args.frame, total - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            print(f"Reading frame {frame_idx}/{total}...")
            ret, frame = cap.read()
        
        if not ret or frame is None:
            print("Error: Failed to capture frame")
            sys.exit(1)
        
        # Save
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), frame)
        print(f"Saved: {output_path} ({frame.shape[1]}x{frame.shape[0]})")
        
    finally:
        cap.release()


if __name__ == "__main__":
    main()