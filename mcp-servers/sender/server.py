#!/usr/bin/env python3
"""
MCP Server for mppdp5 - Controls pose/sender processes via MCP tools.

Provides tools to:
- List available cameras
- Start/stop contour, pose, segment extraction
- Get process status and logs
"""

from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mppdp5-sender")

# Configuration
ROOT_DIR = Path(os.environ.get("MPPDP5_ROOT", Path(__file__).parent.parent.parent))
PYTHON = os.environ.get("MPPDP5_PYTHON", sys.executable)
CLI_ENTRY = ROOT_DIR / "cli" / "main.py"

# Process state per stage
_state: dict[str, dict] = {
    "contour": {"process": None, "pid": None, "args": [], "started_at": None, "logs": []},
    "pose": {"process": None, "pid": None, "args": [], "started_at": None, "logs": []},
    "segment": {"process": None, "pid": None, "args": [], "started_at": None, "logs": []},
}


def _run_cli(stage: str, args: list[str]) -> subprocess.Popen:
    """Run mpose CLI as subprocess."""
    cmd = [PYTHON, "-m", "cli.main", stage] + args
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    return proc


@mcp.tool()
def list_cameras(max_cameras: int = 10) -> str:
    """List available camera devices."""
    try:
        import cv2
        available = []
        for i in range(max_cameras):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    available.append({"index": i, "available": True})
                cap.release()
            else:
                break
        return json.dumps({"cameras": available}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def start_contour(
    input_source: str = "0",
    output: str = "work/contour.jsonl",
    mode: str = "landmarks",
    edge_method: str = "canny",
    model_complexity: int = 1,
    min_detection_confidence: float = 0.5,
    min_tracking_confidence: float = 0.5,
    max_frames: int | None = None,
    skip_frames: int = 0,
) -> str:
    """Start contour extraction process."""
    st = _state["contour"]
    if st["process"] is not None and st["process"].poll() is None:
        return json.dumps({"status": "already_running", "pid": st["pid"]}, indent=2)

    args = [
        "--input", input_source,
        "--output", output,
        "--mode", mode,
        "--edge-method", edge_method,
        "--model-complexity", str(model_complexity),
        "--min-det", str(min_detection_confidence),
        "--min-track", str(min_tracking_confidence),
    ]
    if max_frames:
        args.extend(["--max-frames", str(max_frames)])
    if skip_frames:
        args.extend(["--skip-frames", str(skip_frames)])

    try:
        proc = _run_cli("contour", args)
        st["process"] = proc
        st["pid"] = proc.pid
        st["args"] = args
        st["started_at"] = time.time()
        st["logs"] = []
        return json.dumps({"status": "started", "pid": proc.pid, "args": args}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def start_pose(
    input_source: str = "0",
    output: str = "work/pose.jsonl",
    model_complexity: int = 1,
    min_detection_confidence: float = 0.5,
    min_tracking_confidence: float = 0.5,
    smooth: bool = True,
    max_frames: int | None = None,
    skip_frames: int = 0,
) -> str:
    """Start pose estimation process."""
    st = _state["pose"]
    if st["process"] is not None and st["process"].poll() is None:
        return json.dumps({"status": "already_running", "pid": st["pid"]}, indent=2)

    args = [
        "--input", input_source,
        "--output", output,
        "--model-complexity", str(model_complexity),
        "--min-det", str(min_detection_confidence),
        "--min-track", str(min_tracking_confidence),
        "--smooth" if smooth else "--no-smooth",
    ]
    if max_frames:
        args.extend(["--max-frames", str(max_frames)])
    if skip_frames:
        args.extend(["--skip-frames", str(skip_frames)])

    try:
        proc = _run_cli("pose", args)
        st["process"] = proc
        st["pid"] = proc.pid
        st["args"] = args
        st["started_at"] = time.time()
        st["logs"] = []
        return json.dumps({"status": "started", "pid": proc.pid, "args": args}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def start_segment(
    input_source: str = "0",
    output: str = "work/masks/",
    model: str = "mediapipe",
    mask_format: str = "png",
    max_frames: int | None = None,
    skip_frames: int = 0,
    device: str = "cpu",
) -> str:
    """Start segmentation process."""
    st = _state["segment"]
    if st["process"] is not None and st["process"].poll() is None:
        return json.dumps({"status": "already_running", "pid": st["pid"]}, indent=2)

    args = [
        "--input", input_source,
        "--output", output,
        "--model", model,
        "--mask-format", mask_format,
        "--device", device,
    ]
    if max_frames:
        args.extend(["--max-frames", str(max_frames)])
    if skip_frames:
        args.extend(["--skip-frames", str(skip_frames)])

    try:
        proc = _run_cli("segment", args)
        st["process"] = proc
        st["pid"] = proc.pid
        st["args"] = args
        st["started_at"] = time.time()
        st["logs"] = []
        return json.dumps({"status": "started", "pid": proc.pid, "args": args}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def start_pipeline(
    input_source: str = "0",
    output_dir: str = "work/pipeline/",
    contour_mode: str = "landmarks",
    segment_model: str = "mediapipe",
    model_complexity: int = 1,
    max_frames: int | None = None,
    skip_frames: int = 0,
) -> str:
    """Start full pipeline (contour + pose + segment)."""
    # Check if any stage is already running
    for stage_name, st in _state.items():
        if st["process"] is not None and st["process"].poll() is None:
            return json.dumps({"status": "already_running", "stage": stage_name, "pid": st["pid"]}, indent=2)

    args = [
        "--input", input_source,
        "--output-dir", output_dir,
        "--contour-mode", contour_mode,
        "--segment-model", segment_model,
        "--model-complexity", str(model_complexity),
    ]
    if max_frames:
        args.extend(["--max-frames", str(max_frames)])
    if skip_frames:
        args.extend(["--skip-frames", str(skip_frames)])

    try:
        proc = _run_cli("pipeline", args)
        # Mark all stages as running with same PID
        for st in _state.values():
            st["process"] = proc
            st["pid"] = proc.pid
            st["args"] = args
            st["started_at"] = time.time()
            st["logs"] = []
        return json.dumps({"status": "started", "pid": proc.pid, "args": args}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def stop_process(stage: str = "all") -> str:
    """Stop running process(es). stage: 'contour', 'pose', 'segment', 'pipeline', or 'all'."""
    results = {}
    
    stages_to_stop = list(_state.keys()) if stage == "all" else [stage]
    
    for stage_name in stages_to_stop:
        st = _state.get(stage_name)
        if not st:
            results[stage_name] = {"status": "unknown_stage"}
            continue
            
        if st["process"] is None or st["process"].poll() is not None:
            results[stage_name] = {"status": "not_running"}
            continue
            
        try:
            proc = st["process"]
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                time.sleep(0.5)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            st["process"] = None
            st["pid"] = None
            results[stage_name] = {"status": "stopped"}
        except Exception as e:
            results[stage_name] = {"status": "error", "error": str(e)}
    
    return json.dumps(results, indent=2)


@mcp.tool()
def get_status(stage: str = "all") -> str:
    """Get status of running process(es)."""
    stages_to_check = list(_state.keys()) if stage == "all" else [stage]
    results = {}
    
    for stage_name in stages_to_check:
        st = _state.get(stage_name)
        if not st:
            results[stage_name] = {"status": "unknown_stage"}
            continue
            
        running = st["process"] is not None and st["process"].poll() is None
        results[stage_name] = {
            "running": running,
            "pid": st["pid"] if running else None,
            "args": st["args"] if running else None,
            "started_at": st["started_at"] if running else None,
            "uptime_seconds": time.time() - st["started_at"] if running and st["started_at"] else None,
        }
    
    return json.dumps(results, indent=2)


@mcp.tool()
def get_logs(stage: str = "contour", lines: int = 50) -> str:
    """Get recent logs from a process."""
    st = _state.get(stage)
    if not st:
        return json.dumps({"error": f"Unknown stage: {stage}"}, indent=2)
    
    logs = st["logs"][-lines:] if st["logs"] else []
    return json.dumps({"stage": stage, "logs": logs}, indent=2)


if __name__ == "__main__":
    mcp.run()