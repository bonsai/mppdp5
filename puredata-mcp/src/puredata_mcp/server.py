"""MCP tools for a running Pure Data patch, controlled over OSC.

The server never executes shell commands or writes arbitrary Pd patch code.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pythonosc.udp_client import SimpleUDPClient

mcp = FastMCP("puredata-mcp")

HOST = os.getenv("PD_OSC_HOST", "127.0.0.1")
PORT = int(os.getenv("PD_OSC_PORT", "9000"))
SONG_ROOT = Path(os.getenv("PD_SONG_ROOT", str(Path.cwd() / "songs"))).resolve()
PRESET_ROOT = Path(os.getenv("PD_PRESET_ROOT", str(Path.cwd() / "presets"))).resolve()

PARAM_RANGES: dict[str, tuple[float, float]] = {
    "master_volume": (0.0, 1.0),
    "cutoff": (20.0, 20000.0),
    "reverb": (0.0, 1.0),
    "attack": (0.001, 5.0),
    "release": (0.01, 10.0),
}
PRESETS = {
    "sine": "Basic sine lead",
    "arcade": "Bright arcade synth",
    "bass": "Low-frequency bass",
    "pluck": "Short plucked tone",
}
_EFFECTS = {"hit", "dodge", "collision", "game_over", "level_up"}


def _client() -> SimpleUDPClient:
    return SimpleUDPClient(HOST, PORT)


def _int_range(name: str, value: int, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def _number_range(name: str, value: float, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number in [{low}, {high}]")
    result = float(value)
    if not low <= result <= high:
        raise ValueError(f"{name} must be in [{low}, {high}]")
    return result


def _song_path(filename: str) -> Path:
    candidate = (SONG_ROOT / filename).resolve()
    if candidate != SONG_ROOT and SONG_ROOT not in candidate.parents:
        raise ValueError("Song path must stay inside PD_SONG_ROOT")
    if candidate.suffix.lower() != ".json":
        raise ValueError("Song file must have a .json extension")
    return candidate


def validate_song(data: Any) -> dict[str, Any]:
    """Validate the small, versioned song interchange format."""
    if not isinstance(data, dict):
        raise ValueError("Song must be a JSON object")
    allowed = {"version", "title", "bpm", "preset", "notes"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown song fields: {', '.join(sorted(unknown))}")
    if data.get("version") != 1:
        raise ValueError("Song version must be 1")
    bpm = _number_range("bpm", data.get("bpm"), 30, 300)
    preset = data.get("preset", "sine")
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Available: {', '.join(PRESETS)}")
    notes = data.get("notes")
    if not isinstance(notes, list) or not notes:
        raise ValueError("notes must be a non-empty array")
    clean_notes: list[dict[str, Any]] = []
    allowed_note_fields = {"beat", "midi", "velocity", "duration"}
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise ValueError(f"notes[{index}] must be an object")
        extra = set(note) - allowed_note_fields
        if extra:
            raise ValueError(f"Unknown fields in notes[{index}]: {', '.join(sorted(extra))}")
        beat = _number_range(f"notes[{index}].beat", note.get("beat"), 0, 1000000)
        midi = _int_range(f"notes[{index}].midi", note.get("midi"), 0, 127)
        velocity = _int_range(f"notes[{index}].velocity", note.get("velocity", 90), 0, 127)
        duration = _number_range(f"notes[{index}].duration", note.get("duration", 1), 0.01, 64)
        clean_notes.append({"beat": beat, "midi": midi, "velocity": velocity, "duration": duration})
    clean_notes.sort(key=lambda item: item["beat"])
    return {
        "version": 1,
        "title": str(data.get("title", "Untitled"))[:120],
        "bpm": bpm,
        "preset": preset,
        "notes": clean_notes,
    }


@mcp.tool()
def pd_status() -> dict[str, Any]:
    """Report the configured OSC endpoint and whether its UDP port is locally bindable.

    UDP has no connection handshake; this is a configuration/port check, not proof
    that Pure Data is running or that audio is audible.
    """
    bindable = True
    error = None
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", 0))
    except OSError as exc:
        bindable = False
        error = str(exc)
    finally:
        probe.close()
    return {
        "server": "puredata-mcp",
        "osc_host": HOST,
        "osc_port": PORT,
        "udp_available": bindable,
        "note": "UDP is connectionless; start pd/main.pd and verify audio manually.",
        "error": error,
    }


@mcp.tool()
def pd_note_on(note: int, velocity: int = 90, channel: int = 1) -> dict[str, Any]:
    """Send a MIDI-style note-on event to the configured Pure Data OSC receiver."""
    note = _int_range("note", note, 0, 127)
    velocity = _int_range("velocity", velocity, 0, 127)
    channel = _int_range("channel", channel, 1, 16)
    _client().send_message("/pd/note/on", [note, velocity, channel])
    return {"sent": True, "address": "/pd/note/on", "note": note, "velocity": velocity, "channel": channel}


@mcp.tool()
def pd_note_off(note: int, channel: int = 1) -> dict[str, Any]:
    """Send a note-off event to Pure Data."""
    note = _int_range("note", note, 0, 127)
    channel = _int_range("channel", channel, 1, 16)
    _client().send_message("/pd/note/off", [note, channel])
    return {"sent": True, "address": "/pd/note/off", "note": note, "channel": channel}


@mcp.tool()
def pd_set_parameter(name: str, value: float) -> dict[str, Any]:
    """Set an allowlisted synth parameter; arbitrary parameter names are rejected."""
    if name not in PARAM_RANGES:
        raise ValueError(f"Unsupported parameter '{name}'. Allowed: {', '.join(sorted(PARAM_RANGES))}")
    low, high = PARAM_RANGES[name]
    value = _number_range(name, value, low, high)
    _client().send_message("/pd/param", [name, value])
    return {"sent": True, "name": name, "value": value}


@mcp.tool()
def pd_play_effect(name: str) -> dict[str, Any]:
    """Trigger a preconfigured game effect by name."""
    if name not in _EFFECTS:
        raise ValueError(f"Unknown effect '{name}'. Allowed: {', '.join(sorted(_EFFECTS))}")
    _client().send_message("/pd/effect", name)
    return {"sent": True, "effect": name}


@mcp.tool()
def pd_panic() -> dict[str, Any]:
    """Send the all-notes-off panic event."""
    _client().send_message("/pd/panic", 1)
    return {"sent": True, "address": "/pd/panic"}


@mcp.tool()
def pd_list_presets() -> list[dict[str, str]]:
    """List named sound presets configured by the starter patch."""
    return [{"id": key, "description": value} for key, value in PRESETS.items()]


@mcp.tool()
def pd_load_song(filename: str) -> dict[str, Any]:
    """Validate a song JSON file under PD_SONG_ROOT and return normalized song data.

    This tool intentionally does not schedule a whole song; the game/runtime owns
    timing and sends note-on/off events to avoid blocking an MCP request.
    """
    path = _song_path(filename)
    if not path.is_file():
        raise FileNotFoundError(f"Song file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    song = validate_song(data)
    return {
        "valid": True,
        "path": str(path),
        "title": song["title"],
        "bpm": song["bpm"],
        "preset": song["preset"],
        "note_count": len(song["notes"]),
        "song": song,
    }


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
