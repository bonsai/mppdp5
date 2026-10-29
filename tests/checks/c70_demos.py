"""Demo-level checks: each demo is exercised as its own small step."""

from __future__ import annotations

import sys

from .common import ROOT, read, run, tail
from .registry import check

DEMO_DIRS = (
    "adapter-contour", "adapter-pose", "adapter-segment", "full-pipeline",
    "java-renderer", "manga-cam", "mp-py-p5-java", "processing-renderer", "web-fishing",
    "web-manga",
)

PY_DEMOS = (
    "demos/adapter-contour/demo_contour.py",
    "demos/adapter-pose/demo_pose.py",
    "demos/adapter-segment/demo_segment.py",
    "demos/full-pipeline/demo_pipeline.py",
    "demos/manga-cam/manga_cam.py",
    "demos/mp-py-p5-java/mp_osc_sender.py",
)


@check("demo.dirs.present", desc="9 demo directories exist")
def demo_dirs() -> None:
    for name in DEMO_DIRS:
        assert (ROOT / "demos" / name).is_dir(), f"missing demos/{name}"


@check("demo.py.help", desc="every Python demo answers --help", level="slow")
def demo_help() -> None:
    failures = []
    for rel in PY_DEMOS:
        proc = run([sys.executable, str(ROOT / rel), "--help"], timeout=90)
        if proc.returncode != 0:
            failures.append(f"{rel} rc={proc.returncode}: {tail(proc, 3)}")
    assert not failures, " | ".join(failures)


@check("demo.mp_osc.tasks_api", desc="mp_osc_sender uses the Tasks PoseLandmarker")
def mp_osc_tasks() -> None:
    text = (ROOT / "demos" / "mp-py-p5-java" / "mp_osc_sender.py").read_text(encoding="utf-8")
    assert "vision.PoseLandmarker" in text, "mp_osc_sender is not on the Tasks API"
    assert "mp.solutions" not in text, "mp_osc_sender still uses legacy mp.solutions"


@check("demo.manga_cam.migrated", desc="manga_cam no longer imports mp.solutions")
def manga_cam_migrated() -> None:
    text = (ROOT / "demos" / "manga-cam" / "manga_cam.py").read_text(encoding="utf-8")
    assert "mp.solutions" not in text, (
        "manga_cam.py still uses mp.solutions; mediapipe 1.x removed it "
        "(see SKILL.md 'mediapipe 1.x 移行')"
    )


@check("demo.web_fishing.p5", desc="web-fishing loads p5.js and connects via WebSocket")
def web_fishing() -> None:
    index = ROOT / "demos" / "web-fishing" / "index.html"
    assert index.exists(), "demos/web-fishing/index.html missing"
    text = index.read_text(encoding="utf-8", errors="replace")
    assert "p5" in text.lower(), "index.html does not reference p5"
    sketch = ROOT / "web" / "sketch.js"
    assert sketch.exists(), "web/sketch.js missing (loaded by web-fishing/index.html)"
    sketch_text = sketch.read_text(encoding="utf-8", errors="replace")
    assert "WebSocket" in sketch_text, "web/sketch.js has no WebSocket connection"


@check("demo.web_manga.js", desc="web-manga loads MediaPipe Tasks + p5.js (browser-only manga)")
def web_manga_js() -> None:
    index = ROOT / "demos" / "web-manga" / "index.html"
    assert index.exists(), "demos/web-manga/index.html missing"
    text = index.read_text(encoding="utf-8", errors="replace")
    assert "p5" in text.lower(), "index.html does not reference p5"
    assert "@mediapipe/tasks-vision" in text, "index.html does not import MediaPipe Tasks"
    sketch = ROOT / "demos" / "web-manga" / "sketch.js"
    assert sketch.exists(), "demos/web-manga/sketch.js missing"
    sketch_text = sketch.read_text(encoding="utf-8", errors="replace")
    assert "PoseLandmarker" in sketch_text, "sketch.js does not use PoseLandmarker"
    assert "SelfieSegmenter" in sketch_text, "sketch.js does not use SelfieSegmenter"
    assert "getUserMedia" in sketch_text or "mediaDevices" in sketch_text, "no camera access"
    assert "convexHull" in sketch_text or "convex" in sketch_text, "no contour extraction (convex hull)"
    assert "screen" in sketch_text.lower() or "tone" in sketch_text.lower() or "manga" in sketch_text.lower(), "no manga/tone rendering"



