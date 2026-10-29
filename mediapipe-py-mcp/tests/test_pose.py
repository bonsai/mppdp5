"""Tests for the pure pose interpretation (no MediaPipe required)."""
from __future__ import annotations

import pytest

from mediapipe_py_mcp.pose import (
    LANDMARK_ORDER,
    MISSING,
    POINTS_PER_FRAME,
    PoseInterpreter,
    interpret_once,
    named_landmarks,
    neutral_frame,
)

INDEX = {name: index for name, index in LANDMARK_ORDER}


def lm(**overrides: tuple[float, float, float]) -> list[tuple[float, float, float]]:
    """Build 33 neutral landmarks with the named ones overridden."""
    points = [(0.5, 0.5, 1.0) for _ in range(33)]
    for name, value in overrides.items():
        points[INDEX[name]] = value
    return points


def test_points_length_is_always_28() -> None:
    assert len(interpret_once(lm(), 640, 480).points) == POINTS_PER_FRAME
    assert len(neutral_frame().points) == POINTS_PER_FRAME


def test_low_visibility_landmark_becomes_minus_one() -> None:
    frame = interpret_once(lm(nose=(0.5, 0.5, 0.1)), 640, 480)
    assert frame.points[0] == MISSING
    assert frame.points[1] == MISSING


def test_hip_centre_is_minus_one_when_either_hip_is_hidden() -> None:
    frame = interpret_once(lm(left_hip=(0.45, 0.6, 0.1)), 640, 480)
    assert frame.points[-2] == MISSING
    assert frame.points[-1] == MISSING


def test_lean_is_signed_and_clamped() -> None:
    right = interpret_once(
        lm(left_shoulder=(0.9, 0.3, 1.0), right_shoulder=(0.8, 0.3, 1.0)), 640, 480
    )
    left = interpret_once(
        lm(left_shoulder=(0.1, 0.3, 1.0), right_shoulder=(0.2, 0.3, 1.0)), 640, 480
    )
    assert right.lean > 0
    assert left.lean < 0
    assert abs(right.lean) <= 1.0


def test_arms_spread_requires_wide_wrists() -> None:
    narrow = lm(
        left_shoulder=(0.45, 0.3, 1.0),
        right_shoulder=(0.55, 0.3, 1.0),
        left_wrist=(0.45, 0.5, 1.0),
        right_wrist=(0.55, 0.5, 1.0),
    )
    wide = lm(
        left_shoulder=(0.45, 0.3, 1.0),
        right_shoulder=(0.55, 0.3, 1.0),
        left_wrist=(0.1, 0.5, 1.0),
        right_wrist=(0.9, 0.5, 1.0),
    )
    assert not interpret_once(narrow, 640, 480).arms_spread
    assert interpret_once(wide, 640, 480).arms_spread


def test_arms_spread_needs_visible_wrists() -> None:
    hidden = lm(
        left_shoulder=(0.45, 0.3, 1.0),
        right_shoulder=(0.55, 0.3, 1.0),
        left_wrist=(0.1, 0.5, 0.2),
        right_wrist=(0.9, 0.5, 1.0),
    )
    assert not interpret_once(hidden, 640, 480).arms_spread


def test_confidence_is_mean_of_required_visibilities() -> None:
    frame = interpret_once(
        lm(
            left_shoulder=(0.45, 0.3, 1.0),
            right_shoulder=(0.55, 0.3, 1.0),
            left_hip=(0.45, 0.6, 0.8),
            right_hip=(0.55, 0.6, 0.6),
        ),
        640,
        480,
    )
    assert frame.confidence == pytest.approx((1.0 + 1.0 + 0.8 + 0.6) / 4.0, abs=1e-3)
    assert frame.detected


def test_crouch_when_hips_drop_below_the_midpoint() -> None:
    crouched = lm(
        left_shoulder=(0.45, 0.2, 1.0),
        right_shoulder=(0.55, 0.2, 1.0),
        left_hip=(0.45, 0.7, 1.0),
        right_hip=(0.55, 0.7, 1.0),
        left_knee=(0.45, 0.8, 1.0),
        right_knee=(0.55, 0.8, 1.0),
    )
    assert interpret_once(crouched, 640, 480).crouch
    assert not interpret_once(lm(), 640, 480).crouch


def test_short_landmark_list_is_treated_as_no_detection() -> None:
    frame = interpret_once([(0.5, 0.5, 1.0)] * 10, 640, 480)
    assert frame.detected is False
    assert frame.points == [MISSING] * POINTS_PER_FRAME


def test_wrist_speed_is_zero_on_the_first_frame_then_positive() -> None:
    interpreter = PoseInterpreter()
    first = interpreter.update(lm(), 640, 480)
    assert first.left_speed == 0.0

    moved = interpreter.update(lm(left_wrist=(0.6, 0.5, 1.0)), 640, 480)
    assert moved.left_speed == pytest.approx(0.1 * 640, abs=1e-3)


def test_speed_state_resets_when_detection_drops() -> None:
    interpreter = PoseInterpreter()
    interpreter.update(lm(), 640, 480)
    interpreter.update(lm(left_wrist=(0.6, 0.5, 1.0)), 640, 480)
    interpreter.update([], 640, 480)
    after = interpreter.update(lm(left_wrist=(0.6, 0.5, 1.0)), 640, 480)
    assert after.left_speed == 0.0


def test_static_sequence_has_no_sway() -> None:
    interpreter = PoseInterpreter()
    frame = None
    for _ in range(10):
        frame = interpreter.update(lm(), 640, 480)
    assert frame is not None
    assert frame.hip_sway == 0.0


def test_sway_detects_moving_hips() -> None:
    interpreter = PoseInterpreter()
    frame = None
    for step in range(10):
        x = 0.5 + (0.1 if step % 2 else 0.0)
        frame = interpreter.update(
            lm(left_hip=(x - 0.05, 0.6, 1.0), right_hip=(x + 0.05, 0.6, 1.0)),
            640,
            480,
        )
    assert frame is not None
    assert frame.hip_sway > 0.0


def test_osc_messages_match_the_documented_contract() -> None:
    addresses = [address for address, _ in interpret_once(lm(), 640, 480).osc_messages()]
    assert addresses == ["/pose/points", "/left_speed", "/right_speed", "/hip_sway"]


def test_named_landmarks_returns_the_thirteen_filtered_points() -> None:
    records = named_landmarks(lm())
    assert len(records) == 13
    assert records[0]["name"] == "nose"
    assert records[-1]["name"] == "right_ankle"
