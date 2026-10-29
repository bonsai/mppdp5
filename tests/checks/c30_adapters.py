"""Adapter checks, split so one broken stage does not hide the others."""

from __future__ import annotations

import asyncio

from .common import WORK, ensure_video, fresh
from .registry import check

STATE: dict[str, object] = {}


def _collect(adapter, video, output, config) -> list:
    async def run():
        return [item async for item in adapter.process_video(str(video), str(output), config)]

    try:
        return asyncio.run(run())
    finally:
        adapter.cleanup()


# ── pose ──────────────────────────────────────────────────────────────
@check("adapters.pose.prepare", desc="PoseAdapter.prepare() opens MediaPipe Pose")
def pose_prepare() -> None:
    from adapters import AdapterConfig, PoseAdapter

    adapter = PoseAdapter()
    config = AdapterConfig(mode="video", protocol="jsonl", max_frames=2)
    adapter.prepare(config)
    STATE["pose"] = (adapter, config)


@check(
    "adapters.pose.frames",
    desc="PoseAdapter yields 2 frames",
    depends_on=("media.video.fixture", "adapters.pose.prepare"),
)
def pose_frames() -> None:
    adapter, config = STATE["pose"]
    outputs = _collect(adapter, ensure_video(), WORK / "check_pose.jsonl", config)
    assert len(outputs) == 2, f"expected 2 outputs, got {len(outputs)}"
    STATE["pose.outputs"] = outputs


@check("adapters.pose.schema", desc="pose outputs carry landmarks/features", depends_on=("adapters.pose.frames",))
def pose_schema() -> None:
    outputs = STATE["pose.outputs"]
    for output in outputs:
        assert output.stage_id == "pose", output.stage_id
        assert isinstance(output.success, bool)
        assert len(output.landmarks) == 132, f"landmarks has {len(output.landmarks)} values"
        assert 0.0 <= output.confidence <= 1.0, output.confidence
        for name in ("lean", "arms_spread", "crouch"):
            assert hasattr(output, name), f"PoseOutput lacks {name}"


# ── contour: edges path is MediaPipe-free on purpose ───────────────────
@check("adapters.contour.edges.prepare", desc="ContourAdapter(edges) needs no pose model")
def contour_edges_prepare() -> None:
    from adapters import AdapterConfig, ContourAdapter

    adapter = ContourAdapter()
    config = AdapterConfig(mode="video", contour_mode="edges", edge_method="canny", max_frames=2)
    adapter.prepare(config)
    STATE["contour.edges"] = (adapter, config)


@check(
    "adapters.contour.edges.frames",
    desc="contour(edges) yields 2 frames with normalized points",
    depends_on=("media.video.fixture", "adapters.contour.edges.prepare"),
)
def contour_edges_frames() -> None:
    adapter, config = STATE["contour.edges"]
    outputs = _collect(adapter, ensure_video(), WORK / "check_contour_edges.jsonl", config)
    assert len(outputs) == 2, f"expected 2 outputs, got {len(outputs)}"
    for output in outputs:
        assert output.stage_id == "contour"
        for x, y in output.points:
            assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0, f"point outside 0..1: {(x, y)}"


@check("adapters.contour.landmarks.prepare", desc="ContourAdapter(landmarks) opens MediaPipe Pose")
def contour_landmarks_prepare() -> None:
    from adapters import AdapterConfig, ContourAdapter

    adapter = ContourAdapter()
    config = AdapterConfig(mode="video", contour_mode="landmarks", max_frames=1)
    adapter.prepare(config)
    STATE["contour.landmarks"] = (adapter, config)


# ── segment ───────────────────────────────────────────────────────────
@check("adapters.segment.prepare", desc="SegmentAdapter.prepare() opens SelfieSegmentation")
def segment_prepare() -> None:
    from adapters import AdapterConfig, SegmentAdapter

    adapter = SegmentAdapter()
    config = AdapterConfig(mode="video", segmentation_model="mediapipe", max_frames=2)
    adapter.prepare(config)
    STATE["segment"] = (adapter, config)


@check(
    "adapters.segment.frames",
    desc="segment writes 2 mask files",
    depends_on=("media.video.fixture", "adapters.segment.prepare"),
)
def segment_frames() -> None:
    adapter, config = STATE["segment"]
    mask_dir = WORK / "check_masks"
    fresh(mask_dir)
    mask_dir.mkdir(parents=True, exist_ok=True)
    outputs = _collect(adapter, ensure_video(), mask_dir / "mask.png", config)
    assert len(outputs) == 2, f"expected 2 outputs, got {len(outputs)}"
    written = [p for p in mask_dir.rglob("*.png") if p.stat().st_size > 0]
    assert written, "no non-empty mask PNG was written"


# ── config contract ───────────────────────────────────────────────────
@check("adapters.config.defaults", desc="AdapterConfig defaults match the CLI contract")
def config_defaults() -> None:
    from adapters import AdapterConfig

    config = AdapterConfig()
    assert config.protocol == "jsonl"
    assert config.output_format == "jsonl"
    assert config.mode == "video"
    assert config.model_complexity == 1
    assert config.skip_frames == 0
