"""CLI checks: one small invocation per adapter, then the pipeline."""

from __future__ import annotations

from .common import WORK, cli, ensure_video, fresh, read_jsonl, tail
from .registry import check

POSE_KEYS = {
    "stage_id", "frame_index", "timestamp", "success", "landmarks",
    "landmark_names", "lean", "arms_spread", "crouch", "confidence", "metadata",
}
CONTOUR_KEYS = {
    "stage_id", "frame_index", "timestamp", "success", "points",
    "connections", "image_width", "image_height",
}


def _ok(proc, label: str):
    assert proc.returncode == 0, f"{label} exited {proc.returncode}: {tail(proc)}"


@check("cli.help", desc="python -m cli.main --help lists 4 subcommands", level="slow")
def help_runs() -> None:
    proc = cli("--help")
    _ok(proc, "cli --help")
    for subcommand in ("contour", "pose", "segment", "pipeline"):
        assert subcommand in proc.stdout, f"{subcommand} missing from --help"


@check("cli.bad_input", desc="missing input exits non-zero with a clear message", level="slow")
def bad_input() -> None:
    proc = cli("pose", "-i", str(WORK / "nope.mp4"), "-o", str(WORK / "nope.jsonl"))
    assert proc.returncode != 0, "missing input should fail"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "not found" in combined.lower(), f"no 'not found' message: {tail(proc)}"


@check("cli.pose.run", desc="pose over 2 frames -> 2 JSONL lines", level="slow")
def pose_run() -> None:
    output = fresh(WORK / "check_cli_pose.jsonl")
    proc = cli("pose", "-i", str(ensure_video()), "-o", str(output), "--max-frames", "2")
    _ok(proc, "cli pose")
    rows = read_jsonl(output)
    assert len(rows) == 2, f"expected 2 rows, got {len(rows)}"
    missing = POSE_KEYS - rows[0].keys()
    assert not missing, f"pose JSONL missing keys: {sorted(missing)}"
    assert rows[0]["stage_id"] == "pose"


@check("cli.contour.run", desc="contour(landmarks) over 2 frames", level="slow")
def contour_run() -> None:
    output = fresh(WORK / "check_cli_contour.jsonl")
    proc = cli(
        "contour", "-i", str(ensure_video()), "-o", str(output),
        "--mode", "landmarks", "--max-frames", "2",
    )
    _ok(proc, "cli contour")
    rows = read_jsonl(output)
    assert len(rows) == 2, f"expected 2 rows, got {len(rows)}"
    missing = CONTOUR_KEYS - rows[0].keys()
    assert not missing, f"contour JSONL missing keys: {sorted(missing)}"


@check("cli.segment.run", desc="segment over 2 frames -> masks on disk", level="slow")
def segment_run() -> None:
    mask_dir = fresh(WORK / "check_cli_masks")
    mask_dir.mkdir(parents=True, exist_ok=True)
    proc = cli(
        "segment", "-i", str(ensure_video()), "-o", str(mask_dir / "mask.png"),
        "--max-frames", "2",
    )
    _ok(proc, "cli segment")
    masks = [p for p in mask_dir.rglob("*.png") if p.stat().st_size > 0]
    assert len(masks) >= 2, f"expected >= 2 masks, found {len(masks)}"


@check("cli.pipeline.run", desc="pipeline over 2 frames produces 3 outputs", level="slow")
def pipeline_run() -> None:
    out = fresh(WORK / "check_pipeline")
    out.mkdir(parents=True, exist_ok=True)
    proc = cli(
        "pipeline", "-i", str(ensure_video()), "-o", str(out), "--max-frames", "2",
    )
    _ok(proc, "cli pipeline")
    assert (out / "contour.jsonl").exists(), "contour.jsonl missing"
    assert (out / "pose.jsonl").exists(), "pose.jsonl missing"
    masks = list((out / "masks").glob("*.png")) if (out / "masks").exists() else []
    assert masks, "no masks produced"
