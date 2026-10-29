"""MediaPipe API surface + adapter import + OSC address inventory."""

from __future__ import annotations

import re

from .common import ROOT, read
from .registry import check


@check(
    "api.mediapipe.legacy",
    desc="mp.solutions legacy is removed in mediapipe 1.x",
)
def legacy_api() -> None:
    import mediapipe as mp

    assert not hasattr(mp, "solutions"), (
        "mediapipe should not expose legacy mp.solutions; "
        "all adapters must use Tasks API (vision.PoseLandmarker / vision.ImageSegmenter)"
    )


@check("api.mediapipe.tasks", desc="mp.tasks.python.vision.PoseLandmarker exists")
def tasks_api() -> None:
    from mediapipe.tasks.python import vision

    for name in ("PoseLandmarker", "PoseLandmarkerOptions", "RunningMode"):
        assert hasattr(vision, name), f"vision lacks {name}"


@check("api.mediapipe.image", desc="mp.Image + ImageFormat.SRGB")
def tasks_image() -> None:
    import mediapipe as mp

    assert hasattr(mp, "Image"), "mp.Image missing"
    assert hasattr(mp.ImageFormat, "SRGB"), "mp.ImageFormat.SRGB missing"


@check("api.pose.landmark_names", desc="33 landmark names, stable order")
def landmark_names() -> None:
    from adapters.pose import LANDMARK_NAMES

    assert len(LANDMARK_NAMES) == 33, f"expected 33 names, got {len(LANDMARK_NAMES)}"
    assert LANDMARK_NAMES[0] == "nose", LANDMARK_NAMES[0]
    assert LANDMARK_NAMES[-1] == "right_foot_index", LANDMARK_NAMES[-1]


@check("api.adapters.import", desc="adapters package exposes the three adapters")
def adapters_import() -> None:
    import adapters

    for name in ("ContourAdapter", "PoseAdapter", "SegmentAdapter", "AdapterConfig"):
        assert hasattr(adapters, name), f"adapters lacks {name}"


@check("api.server.osc_addresses", desc="server.py sends the 4 contracted OSC addresses")
def osc_addresses() -> None:
    text = read("server.py")
    for address in ("/pose/points", "/left_speed", "/right_speed", "/hip_sway"):
        assert address in text, f"server.py never sends {address}"


@check("api.renderer.mppose_contract", desc="OSC sketches read the /mppose/* addresses")
def renderer_contract() -> None:
    text = read("demos/processing-renderer/spt/spt.pde")
    assert "/mppose/landmark" in text, "spt.pde does not handle /mppose/landmark"
    manga = read("demos/mp-py-p5-java/processing/MPPoseManga/MPPoseManga.pde")
    for address in ("/mppose/start", "/mppose/frame", "/mppose/landmark"):
        assert address in manga, f"MPPoseManga.pde does not handle {address}"


@check("api.no_duplicate_pose_tables", desc="landmark indices defined once per package")
def duplicate_tables() -> None:
    pose = read("adapters/pose.py")
    hits = len(re.findall(r"class PoseLandmark:", pose))
    assert hits == 1, f"expected one PoseLandmark class in adapters/pose.py, found {hits}"
    assert (ROOT / "adapters" / "pose.py").exists()
