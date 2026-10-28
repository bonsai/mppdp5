#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mppose-manga-sender")

SENDER_DIR = os.environ.get("MPPOSE_SENDER_DIR", str(Path(__file__).parent.parent))
PYTHON = os.environ.get("MPPOSE_PYTHON", sys.executable)
SENDER_SCRIPT = os.path.join(SENDER_DIR, "mp_osc_sender.py")

_state = {
    "process": None,
    "pid": None,
    "args": [],
    "started_at": None,
    "logs": []
}

@mcp.tool()
def list_cameras(max_cameras: int = 10) -> str:
    try:
        import cv2
        available = []
        for i in range(max_cameras):
            cap = cv2.VideoCapture(i)
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
def start_sender(input_source: str = "0", ip: str = "127.0.0.1", port: int = 9000, mirror: bool = True, model_complexity: int = 1, min_detection_confidence: float = 0.5, min_tracking_confidence: float = 0.5) -> str:
    if _state["process"] is not None and _state["process"].poll() is None:
        return json.dumps({"status": "already_running", "pid": _state["pid"]}, indent=2)
    
    args = [PYTHON, SENDER_SCRIPT, "--input", input_source, "--ip", ip, "--port", str(port), "--model", str(model_complexity), "--min-det", str(min_detection_confidence), "--min-track", str(min_tracking_confidence)]
    if mirror and input_source.isdigit():
        args.append("--mirror")
    
    try:
        proc = subprocess.Popen(args, cwd=SENDER_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        _state["process"] = proc
        _state["pid"] = proc.pid
        _state["args"] = args
        _state["started_at"] = time.time()
        _state["logs"] = []
        return json.dumps({"status": "started", "pid": proc.pid, "args": args}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)

@mcp.tool()
def stop_sender() -> str:
    if _state["process"] is None or _state["process"].poll() is not None:
        return json.dumps({"status": "not_running"}, indent=2)
    try:
        proc = _state["process"]
        if os.name == 'nt':
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            time.sleep(0.5)
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        _state["process"] = None
        _state["pid"] = None
        return json.dumps({"status": "stopped"}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)

@mcp.tool()
def get_status() -> str:
    running = _state["process"] is not None and _state["process"].poll() is None
    return json.dumps({
        "running": running,
        "pid": _state["pid"] if running else None,
        "args": _state["args"] if running else None,
        "started_at": _state["started_at"] if running else None,
        "uptime_seconds": time.time() - _state["started_at"] if running and _state["started_at"] else None
    }, indent=2)

@mcp.tool()
def get_logs(lines: int = 50) -> str:
    return json.dumps({"logs": _state["logs"][-lines:]}, indent=2)

if __name__ == "__main__":
    mcp.run()
