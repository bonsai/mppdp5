#!/usr/bin/env python3
"""
MCP Server for web-manga demo - Browser-only MediaPipe + p5.js manga renderer.

Provides tools for manga generation from pose data (server-side).
The HTTP server (port 8082) should be started separately:
    python -m http.server 8082 -d demos/web-manga
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("web-manga")

# Configuration
ROOT_DIR = Path(os.environ.get("MPPDP5_ROOT", Path(__file__).parent.parent.parent))
DEMO_DIR = ROOT_DIR / "demos" / "web-manga"
SERVER_PORT = 8082
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"


@mcp.tool()
def get_demo_status() -> str:
    """Get current demo server status (checks if HTTP server is running on 8082)."""
    import urllib.request
    
    try:
        with urllib.request.urlopen(SERVER_URL, timeout=2) as resp:
            return json.dumps({
                "status": "running",
                "url": SERVER_URL,
                "http_status": resp.status,
                "note": "Start HTTP server with: python -m http.server 8082 -d demos/web-manga",
            }, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "not_running",
            "url": SERVER_URL,
            "error": str(e),
            "note": "Start HTTP server with: python -m http.server 8082 -d demos/web-manga",
        }, indent=2)


@mcp.tool()
def list_modes() -> str:
    """List available rendering modes."""
    modes = {
        "manga": "漫画 (Contour + Tone) - Convex hull outline + inner contours + screentone halftone",
        "contour": "輪郭のみ - Clean outline only",
        "pose": "Pose Landmarks - Skeleton + joint positions",
        "segment": "Selfie Segmentation - MediaPipe SelfieSegmenter mask",
    }
    return json.dumps({"modes": modes, "default": "manga"}, indent=2, ensure_ascii=False)


@mcp.tool()
def generate_manga_from_pose(
    landmarks: list[dict],
    mode: str = "manga",
    width: int = 640,
    height: int = 480
) -> str:
    """
    Generate manga-style contour from MediaPipe pose landmarks.
    Replicates the client-side convexHull + screentone logic server-side.
    """
    if not landmarks or len(landmarks) < 11:
        return json.dumps({"error": "Insufficient landmarks (need at least 11)"}, indent=2)
    
    # Key landmark indices for body contour (matching sketch.js)
    indices = [0, 2, 5, 7, 8, 11, 13, 15, 23, 25, 27, 29, 31, 24, 26, 28, 30, 32, 12, 14, 16, 4, 3, 6]
    
    # Filter valid landmarks
    points = []
    for idx in indices:
        if idx < len(landmarks):
            lm = landmarks[idx]
            if lm.get("visibility", 0) > 0.4:
                points.append({"x": lm["x"] * width, "y": lm["y"] * height})
    
    if len(points) < 3:
        return json.dumps({"error": "Not enough visible landmarks for contour"}, indent=2)
    
    # Convex hull (Graham scan)
    def cross(o, a, b):
        return (a["x"] - o["x"]) * (b["y"] - o["y"]) - (a["y"] - o["y"]) * (b["x"] - o["x"])
    
    sorted_pts = sorted(points, key=lambda p: (p["x"], p["y"]))
    
    lower = []
    for p in sorted_pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    
    upper = []
    for p in reversed(sorted_pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    
    hull = lower[:-1] + upper[:-1]
    
    # Screentone pattern (manga mode)
    screentone_dots = []
    if mode == "manga" and len(hull) >= 3:
        min_x = min(p["x"] for p in hull)
        max_x = max(p["x"] for p in hull)
        min_y = min(p["y"] for p in hull)
        max_y = max(p["y"] for p in hull)
        
        cx = (min_x + max_x) / 2
        cy = min_y
        hip_y = max_y
        shoulder_w = max_x - min_x
        
        for y in range(int(cy), int(hip_y), 4):
            ratio = (y - cy) / max(1, hip_y - cy)
            w = shoulder_w * (1 - ratio * 0.3)
            left = cx - w / 2
            right = cx + w / 2
            for x in range(int(left), int(right), 8):
                if (x + y) % 16 < 4:
                    screentone_dots.append({"x": x, "y": y})
    
    return json.dumps({
        "mode": mode,
        "contour": hull,
        "screentone": screentone_dots if mode == "manga" else [],
        "landmark_count": len(landmarks),
        "visible_count": len(points),
    }, indent=2)


@mcp.tool()
def create_manga_panels(
    pose_sequence: list[dict],
    num_panels: int = 4,
    template: str = "action"
) -> str:
    """
    Generate manga panel sequence from pose history.
    Templates: action, drama, comedy, horror, romance
    """
    templates = {
        "action": ["構え", "溜め", "放出", "決着"],
        "drama": ["日常", "異変", "決意", "行動"],
        "comedy": ["平和", "ハプニング", "大慌て", "オチ"],
        "horror": ["静寂", "予兆", "恐怖", "絶望"],
        "romance": ["出会い", "ときめき", "すれ違い", "結ばれ"],
    }
    
    panel_titles = templates.get(template, templates["action"])
    panels = []
    
    for i in range(min(num_panels, len(panel_titles))):
        pose_idx = min(i * len(pose_sequence) // num_panels, len(pose_sequence) - 1) if pose_sequence else 0
        pose = pose_sequence[pose_idx] if pose_sequence else {}
        
        panels.append({
            "index": i + 1,
            "title": panel_titles[i],
            "template": template,
            "pose_snapshot": {
                "lean": pose.get("lean", 0),
                "arms_spread": pose.get("arms_spread", False),
                "crouch": pose.get("crouch", False),
            },
            "suggested_dialogue": f"[{template}] コマ{i+1}: {panel_titles[i]}",
        })
    
    return json.dumps({
        "template": template,
        "panels": panels,
        "total_panels": len(panels),
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def get_demo_info() -> str:
    """Get demo information and file structure."""
    files = {}
    for f in DEMO_DIR.rglob("*"):
        if f.is_file():
            rel = f.relative_to(DEMO_DIR)
            files[str(rel)] = f.stat().st_size
    
    return json.dumps({
        "demo_dir": str(DEMO_DIR),
        "server_url": SERVER_URL,
        "files": files,
        "dependencies": {
            "p5": "https://cdn.jsdelivr.net/npm/p5@1.11.3/lib/p5.min.js",
            "@mediapipe/tasks-vision": "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22",
            "models": [
                "pose_landmarker_lite.task (5.6 MB, float16)",
                "selfie_segmenter.tflite",
            ],
        },
        "start_http_server": "python -m http.server 8082 -d demos/web-manga",
    }, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()