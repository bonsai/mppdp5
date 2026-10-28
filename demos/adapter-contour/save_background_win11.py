"""
Save Background Frame - Windows 11 optimized version.

Handles Windows 11 camera privacy, DSHOW backend, auto-exposure warmup.
"""
from __future__ import annotations
import argparse
import cv2
import sys
from pathlib import Path


def find_working_camera(max_index: int = 5) -> tuple[cv2.VideoCapture, int] | tuple[None, None]:
    """Find first working camera index."""
    for i in range(max_index):
        # Try DSHOW first (Windows 10/11)
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"[OK] Camera {i} (DSHOW)")
                return cap, i
            cap.release()
        
        # Try default backend
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"[OK] Camera {i} (default)")
                return cap, i
            cap.release()
    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Save background frame from camera (Windows 11 optimized)"
    )
    parser.add_argument("--camera", "-c", type=int, default=None,
                        help="Camera index (default: auto-detect)")
    parser.add_argument("--output", "-o", default="background.png",
                        help="Output image path")
    parser.add_argument("--width", "-W", type=int, default=1920,
                        help="Capture width")
    parser.add_argument("--height", "-H", type=int, default=1080,
                        help="Capture height")
    parser.add_argument("--warmup", "-w", type=int, default=30,
                        help="Warmup frames for auto-exposure")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List available cameras and exit")
    
    args = parser.parse_args()
    
    if args.list:
        print("Scanning cameras...")
        for i in range(5):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                print(f"  Camera {i}: {int(w)}x{int(h)} (DSHOW)")
                cap.release()
            else:
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                    print(f"  Camera {i}: {int(w)}x{int(h)} (default)")
                    cap.release()
        return
    
    # Open camera
    if args.camera is not None:
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(args.camera)
        if not cap.isOpened():
            print(f"Error: Cannot open camera {args.camera}")
            print("\nTroubleshooting:")
            print("1. Windows Settings > Privacy & security > Camera")
            print("2. Enable 'Camera access' and 'Let apps access your camera'")
            print("3. Enable 'Desktop apps' at bottom")
            print("4. Restart terminal after changes")
            sys.exit(1)
    else:
        print("Auto-detecting camera...")
        cap, cam_idx = find_working_camera()
        if cap is None:
            print("Error: No working camera found")
            sys.exit(1)
        print(f"Using camera {cam_idx}")
    
    # Configure
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce latency
    
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Resolution: {actual_w}x{actual_h}")
    
    # Warmup: let auto-exposure and white-balance settle
    print(f"Warming up ({args.warmup} frames)...")
    for i in range(args.warmup):
        ret, frame = cap.read()
        if not ret:
            continue
        # Show progress every 10 frames
        if i % 10 == 0:
            print(f"  {i}/{args.warmup}", end="\r")
    print()
    
    # Capture background frame
    print("Capturing background frame...")
    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        print("Error: Failed to capture frame")
        sys.exit(1)
    
    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save as PNG (lossless)
    cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    
    print(f"✓ Saved: {output_path.absolute()}")
    print(f"  Size: {frame.shape[1]}x{frame.shape[0]}")
    print(f"  Channels: {frame.shape[2]} (BGR)")
    
    # Also show file size
    size_kb = output_path.stat().st_size / 1024
    print(f"  File: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()