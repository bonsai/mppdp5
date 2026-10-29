"""Synthetic media fixture checks (no camera needed)."""

from __future__ import annotations

from .common import WORK, ensure_video, rel
from .registry import check


@check("media.video.fixture", desc="work/test_input.mp4 exists and is playable")
def fixture_exists() -> None:
    path = ensure_video()
    assert path.exists(), f"{rel(path)} was not created"
    assert path.stat().st_size > 0, "fixture is empty"


@check("media.video.readable", desc="fixture decodes >= 10 frames at 320x240")
def fixture_readable() -> None:
    import cv2

    path = ensure_video()
    cap = cv2.VideoCapture(str(path))
    try:
        assert cap.isOpened(), f"cannot open {rel(path)}"
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames = 0
        while frames < 20:
            ok, _ = cap.read()
            if not ok:
                break
            frames += 1
    finally:
        cap.release()
    assert (width, height) == (320, 240), f"unexpected size {width}x{height}"
    assert frames >= 10, f"only {frames} frames decoded"


@check("media.work.dir", desc="work/ is writable")
def work_writable() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    probe = WORK / ".write_probe"
    probe.write_text("ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok"
    probe.unlink()
