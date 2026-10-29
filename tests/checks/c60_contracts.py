"""Cross-file contracts: OSC addresses, JSONL schema, duplicated assets."""

from __future__ import annotations

import re

from .common import ROOT, WORK, read, read_jsonl
from .registry import check

OSC_ADDRESSES = ("/pose/points", "/left_speed", "/right_speed", "/hip_sway")
PDE_FILES = (
    "demos/processing-renderer/PoseRendererP5/PoseRendererP5.pde",
    "demos/processing-renderer/ContourRenderer/ContourRenderer.pde",
    "demos/manga-cam/processing/PoseRendererP5/PoseRendererP5.pde",
    "demos/mp-py-p5-java/processing/MPPoseManga/MPPoseManga.pde",
)


@check("contract.osc.readme", desc="README documents all 4 OSC addresses")
def readme_osc() -> None:
    text = read("README.md")
    for address in OSC_ADDRESSES:
        assert address in text, f"README does not document {address}"


@check("contract.osc.sender_set", desc="server.py sends exactly the documented addresses")
def sender_osc_set() -> None:
    text = read("server.py")
    sent = set(re.findall(r'send_message\(\s*"([^"]+)"', text))
    missing = set(OSC_ADDRESSES) - sent
    assert not missing, f"server.py never sends {sorted(missing)}"
    extra = sent - set(OSC_ADDRESSES)
    assert not extra, f"server.py sends undocumented addresses {sorted(extra)}"


@check("contract.jsonl.pose", desc="CLI pose JSONL keeps the documented schema", depends_on=("cli.pose.run",))
def pose_jsonl_schema() -> None:
    rows = read_jsonl(WORK / "check_cli_pose.jsonl")
    for row in rows:
        assert len(row["landmark_names"]) == 33, "landmark_names must have 33 entries"
        assert len(row["landmarks"]) == 132, f"landmarks must be 33*4, got {len(row['landmarks'])}"
        assert isinstance(row["metadata"], dict), "metadata must be an object"
        assert 0.0 <= row["confidence"] <= 1.0, row["confidence"]


@check("contract.jsonl.contour", desc="CLI contour JSONL keeps points/connections", depends_on=("cli.contour.run",))
def contour_jsonl_schema() -> None:
    rows = read_jsonl(WORK / "check_cli_contour.jsonl")
    for row in rows:
        assert isinstance(row["points"], list), "points must be a list"
        assert row["image_width"] > 0 and row["image_height"] > 0, "image size not recorded"
        if row["connections"] is not None:
            for pair in row["connections"]:
                assert len(pair) == 2, f"connection must be an index pair: {pair}"


@check("contract.pde.files", desc="all Processing sketches are present")
def pde_files() -> None:
    for rel in PDE_FILES:
        assert (ROOT / rel).exists(), f"missing sketch: {rel}"


@check("contract.pde.oscp5", desc="OSC-based sketches import oscP5")
def pde_oscp5() -> None:
    for rel in (
        "demos/processing-renderer/spt/spt.pde",
        "demos/processing-renderer/SimplePoseTest/SimplePoseTest.pde",
        "demos/processing-renderer/TestOSCReceive/TestOSCReceive.pde",
        "demos/mp-py-p5-java/processing/MPPoseManga/MPPoseManga.pde",
    ):
        text = read(rel)
        assert "oscP5" in text, f"{rel} does not use oscP5"


@check("contract.java.copies", desc="java-renderer and manga-cam copies stay identical")
def java_copies() -> None:
    a = (ROOT / "demos" / "java-renderer" / "PoseRenderer.java").read_bytes()
    b = (ROOT / "demos" / "manga-cam" / "PoseRenderer.java").read_bytes()
    assert a == b, "PoseRenderer.java diverged between java-renderer and manga-cam"


@check("contract.osc.port_match", desc="server.py OSC port matches every Processing listener")
def osc_port_match() -> None:
    server_port = re.search(r"OSC_PORT\s*=\s*(\d+)", read("server.py"))
    assert server_port, "server.py has no OSC_PORT constant"
    expected = server_port.group(1)
    sketches = {
        "spt": "demos/processing-renderer/spt/spt.pde",
        "SimplePoseTest": "demos/processing-renderer/SimplePoseTest/SimplePoseTest.pde",
        "MPPoseManga": "demos/mp-py-p5-java/processing/MPPoseManga/MPPoseManga.pde",
    }
    mismatched = {}
    for name, rel in sketches.items():
        match = re.search(r"new OscP5\(this,\s*(\d+)\)", read(rel))
        assert match, f"{rel} does not construct OscP5"
        if match.group(1) != expected:
            mismatched[name] = match.group(1)
    assert not mismatched, (
        f"server.py sends OSC to {expected} but sketches listen elsewhere: {mismatched}; "
        "pick one port (README documents 12000, sketches and mp_osc_sender use 9000)"
    )


@check("contract.osc.mp_sender_port", desc="mp_osc_sender default port matches its sketches")
def mp_sender_port() -> None:
    text = read("demos/mp-py-p5-java/mp_osc_sender.py")
    match = re.search(r'"--port",\s*type=int,\s*default=(\d+)', text)
    assert match, "mp_osc_sender has no --port default"
    sender_port = match.group(1)
    for rel in (
        "demos/processing-renderer/spt/spt.pde",
        "demos/mp-py-p5-java/processing/MPPoseManga/MPPoseManga.pde",
    ):
        found = re.search(r"new OscP5\(this,\s*(\d+)\)", read(rel))
        assert found, f"{rel} does not construct OscP5"
        assert found.group(1) == sender_port, (
            f"{rel} listens on {found.group(1)}, mp_osc_sender sends to {sender_port}"
        )


@check("contract.web.entry", desc="web/ has an HTML entry point")
def web_entry() -> None:
    entries = list((ROOT / "web").glob("*.html"))
    assert entries, "web/ has no HTML entry point"
