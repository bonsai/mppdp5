import pytest

from puredata_mcp.server import validate_song


def test_valid_song_is_normalized_and_sorted():
    song = validate_song({
        "version": 1,
        "title": "test",
        "bpm": 120,
        "preset": "sine",
        "notes": [
            {"beat": 2, "midi": 64},
            {"beat": 0, "midi": 60, "velocity": 100, "duration": 0.25},
        ],
    })
    assert song["notes"][0]["midi"] == 60
    assert song["notes"][0]["velocity"] == 100
    assert song["notes"][1]["velocity"] == 90


@pytest.mark.parametrize("song", [
    {"version": 2, "bpm": 120, "notes": [{"beat": 0, "midi": 60}]},
    {"version": 1, "bpm": 500, "notes": [{"beat": 0, "midi": 60}]},
    {"version": 1, "bpm": 120, "notes": [{"beat": 0, "midi": 200}]},
    {"version": 1, "bpm": 120, "notes": [{"beat": 0, "midi": 60, "unknown": 1}]},
    {"version": 1, "bpm": 120, "preset": "not-real", "notes": [{"beat": 0, "midi": 60}]},
])
def test_invalid_song_is_rejected(song):
    with pytest.raises(ValueError):
        validate_song(song)


def test_unknown_top_level_field_is_rejected():
    with pytest.raises(ValueError, match="Unknown song fields"):
        validate_song({
            "version": 1,
            "bpm": 120,
            "notes": [{"beat": 0, "midi": 60}],
            "execute": "no",
        })
