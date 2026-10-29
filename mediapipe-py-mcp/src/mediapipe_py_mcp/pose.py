"""Pure pose interpretation for the mpp5 body-input pipeline.

This module has no MediaPipe dependency: it turns normalized landmark triples
``(x, y, visibility)`` into the numeric contract that the p5.js and Processing
renderers already consume, so the same numbers can come from a still image, a
single camera frame, or a live stream.

The formulas are ported one-to-one from ``mppdp5/server.py`` so the OSC contract
stays compatible with the existing renderers.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Sequence

#: A landmark is (x, y, visibility), all normalized to 0..1.
Landmark = Sequence[float]

# Visibility gates keep dropped landmarks from dragging a joint to (0, 0).
VISIBILITY_FLOOR = 0.35
WRIST_VISIBILITY_FLOOR = 0.45
DETECTION_CONFIDENCE = 0.35
#: Value emitted for a landmark that failed the visibility gate.
MISSING = -1.0
#: Normalized sway below this is reported as standing still.
SWAY_FLOOR = 0.03
SWAY_HISTORY = 20
#: MediaPipe's full pose topology; a shorter list means "no detection".
LANDMARK_COUNT = 33
#: 13 filtered landmarks plus the interpreted hip centre, x/y each.
POINTS_PER_FRAME = 28

#: Wire order of the 13 filtered landmarks on /pose/points.
LANDMARK_ORDER: tuple[tuple[str, int], ...] = (
    ("nose", 0),
    ("left_shoulder", 11),
    ("right_shoulder", 12),
    ("left_elbow", 13),
    ("right_elbow", 14),
    ("left_wrist", 15),
    ("right_wrist", 16),
    ("left_hip", 23),
    ("right_hip", 24),
    ("left_knee", 25),
    ("right_knee", 26),
    ("left_ankle", 27),
    ("right_ankle", 28),
)

_LANDMARK_INDEX = {name: index for name, index in LANDMARK_ORDER}


@dataclass(slots=True)
class PoseFrame:
    """One interpreted pose, ready for OSC and the web client."""

    detected: bool
    confidence: float
    lean: float
    arms_spread: bool
    crouch: bool
    points: list[float]
    left_speed: float
    right_speed: float
    hip_sway: float

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-friendly view used by the MCP tools."""
        return {
            "detected": self.detected,
            "confidence": self.confidence,
            "lean": self.lean,
            "arms_spread": self.arms_spread,
            "crouch": self.crouch,
            "left_speed": round(self.left_speed, 3),
            "right_speed": round(self.right_speed, 3),
            "hip_sway": round(self.hip_sway, 3),
            "points": self.points,
        }

    def osc_messages(self) -> list[tuple[str, Any]]:
        """Return the documented OSC contract as (address, payload) pairs."""
        return [
            ("/pose/points", self.points),
            ("/left_speed", float(self.left_speed)),
            ("/right_speed", float(self.right_speed)),
            ("/hip_sway", float(self.hip_sway)),
        ]


def neutral_frame() -> PoseFrame:
    """Return the ``-1`` filled frame the renderers already understand."""
    return PoseFrame(
        detected=False,
        confidence=0.0,
        lean=0.0,
        arms_spread=False,
        crouch=False,
        points=[MISSING] * POINTS_PER_FRAME,
        left_speed=0.0,
        right_speed=0.0,
        hip_sway=0.0,
    )


def named_landmarks(landmarks: Sequence[Landmark]) -> list[dict[str, Any]]:
    """Return the 13 filtered landmarks as named, rounded records."""
    records: list[dict[str, Any]] = []
    if not landmarks:
        return records
    for name, index in LANDMARK_ORDER:
        x, y, visibility = landmarks[index][0], landmarks[index][1], landmarks[index][2]
        records.append(
            {
                "name": name,
                "x": round(float(x), 5),
                "y": round(float(y), 5),
                "visibility": round(float(visibility), 4),
            }
        )
    return records


class PoseInterpreter:
    """Stateful interpreter: wrist speed and hip sway need the previous frame."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Drop the temporal history (wrist speed and hip sway)."""
        self._prev_left: tuple[float, float] | None = None
        self._prev_right: tuple[float, float] | None = None
        self._hip_x_history: deque[float] = deque(maxlen=SWAY_HISTORY)

    def update(
        self,
        landmarks: Sequence[Landmark] | None,
        width: int,
        height: int,
    ) -> PoseFrame:
        """Interpret one frame of normalized landmarks and return a PoseFrame."""
        if not landmarks or len(landmarks) < LANDMARK_COUNT:
            # Mirror server.py: a dropped detection resets speed and sway state.
            self.reset()
            return neutral_frame()

        def lm(name: str) -> Landmark:
            return landmarks[_LANDMARK_INDEX[name]]

        left_sh, right_sh = lm("left_shoulder"), lm("right_shoulder")
        left_hip, right_hip = lm("left_hip"), lm("right_hip")
        left_knee, right_knee = lm("left_knee"), lm("right_knee")
        left_wrist, right_wrist = lm("left_wrist"), lm("right_wrist")

        confidence = sum(p[2] for p in (left_sh, right_sh, left_hip, right_hip)) / 4.0
        shoulder_center_x = (left_sh[0] + right_sh[0]) / 2.0
        shoulder_center_y = (left_sh[1] + right_sh[1]) / 2.0
        hip_center_y = (left_hip[1] + right_hip[1]) / 2.0
        knee_center_y = (left_knee[1] + right_knee[1]) / 2.0
        shoulder_width = max(abs(left_sh[0] - right_sh[0]), 0.05)
        wrist_span = abs(left_wrist[0] - right_wrist[0])
        lean = max(-1.0, min(1.0, (shoulder_center_x - 0.5) * 2.4))
        arms_spread = (
            left_wrist[2] > WRIST_VISIBILITY_FLOOR
            and right_wrist[2] > WRIST_VISIBILITY_FLOOR
            and wrist_span / shoulder_width > 2.0
        )
        crouch = hip_center_y > (shoulder_center_y + knee_center_y) / 2.0 + 0.015

        # OSC contract: 13 filtered landmarks plus the interpreted hip center.
        points: list[float] = []
        for _, index in LANDMARK_ORDER:
            landmark = landmarks[index]
            if landmark[2] >= VISIBILITY_FLOOR:
                points.extend([float(landmark[0]), float(landmark[1])])
            else:
                points.extend([MISSING, MISSING])

        hip_sway = 0.0
        if min(left_hip[2], right_hip[2]) >= VISIBILITY_FLOOR:
            hip_x = (left_hip[0] + right_hip[0]) / 2.0
            hip_y = (left_hip[1] + right_hip[1]) / 2.0
            points.extend([float(hip_x), float(hip_y)])
            self._hip_x_history.append(hip_x)
            if len(self._hip_x_history) >= 5:
                mean_x = sum(self._hip_x_history) / len(self._hip_x_history)
                variance = sum(
                    (x - mean_x) ** 2 for x in self._hip_x_history
                ) / len(self._hip_x_history)
                hip_sway = min(math.sqrt(variance) * width / 25.0, 1.5)
                if hip_sway < SWAY_FLOOR:
                    hip_sway = 0.0
        else:
            points.extend([MISSING, MISSING])

        left_pos = (left_wrist[0] * width, left_wrist[1] * height)
        right_pos = (right_wrist[0] * width, right_wrist[1] * height)
        left_speed = (
            math.hypot(left_pos[0] - self._prev_left[0], left_pos[1] - self._prev_left[1])
            if self._prev_left
            else 0.0
        )
        right_speed = (
            math.hypot(right_pos[0] - self._prev_right[0], right_pos[1] - self._prev_right[1])
            if self._prev_right
            else 0.0
        )
        self._prev_left, self._prev_right = left_pos, right_pos

        return PoseFrame(
            detected=confidence >= DETECTION_CONFIDENCE,
            confidence=round(float(confidence), 3),
            lean=round(lean, 3),
            arms_spread=bool(arms_spread),
            crouch=bool(crouch),
            points=points,
            left_speed=float(left_speed),
            right_speed=float(right_speed),
            hip_sway=float(hip_sway),
        )


def interpret_once(
    landmarks: Sequence[Landmark] | None,
    width: int,
    height: int,
) -> PoseFrame:
    """Interpret a single frame with no temporal history (speed and sway are 0)."""
    return PoseInterpreter().update(landmarks, width, height)
