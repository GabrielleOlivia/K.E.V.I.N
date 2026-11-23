"""Relative head/chest tilt from TWO independent raw accelerometer streams.

TRAINING ONLY. Gravity-derived tilt is not absolute anatomical airway angle.
Both modules must be rigidly fixed and independently aligned/calibrated.
No stale/missing data are silently substituted with zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, isfinite, sqrt


def wrap_deg(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def accelerometer_tilt(xyz: tuple[float, float, float], axis: str) -> float | None:
    """Pitch or roll from static gravity vector, in sensor mounting coordinates.

    Rapid acceleration and axis misalignment contaminate gravity tilt.
    """
    x, y, z = xyz
    if not all(isfinite(v) for v in xyz):
        return None
    norm = sqrt(x*x + y*y + z*z)
    if norm < 100 or norm > 100000:
        return None
    if axis == "pitch":
        return degrees(atan2(-x, sqrt(y*y + z*z)))
    if axis == "roll":
        return degrees(atan2(y, z))
    raise ValueError(f"Unknown IMU axis {axis!r}")


@dataclass
class Sample:
    xyz: tuple[float, float, float]
    received_at: float


class TiltPair:
    """Requires a neutral reference for both devices and fresh samples.

    Independent axis/sign adjustments compensate only simple mounting differences;
    real 3D head-to-chest pose requires known rigid sensor-to-anatomical transforms.
    """
    FRESH_SECONDS = 2.0

    def __init__(self):
        self.samples: dict[str, Sample] = {}
        self.zeroed = False
        self.reference: dict[str, float] = {}
        self.configuration: tuple[str, str, bool, bool] | None = None

    def update(self, role: str, xyz: tuple[float, float, float], now: float):
        if role not in ("head", "chest"):
            return
        if accelerometer_tilt(xyz, "pitch") is None:
            self.samples.pop(role, None)
            self.zeroed = False
            return
        self.samples[role] = Sample(xyz, now)

    def discard(self, role: str):
        self.samples.pop(role, None)
        self.zeroed = False

    def fresh(self, role: str, now: float) -> bool:
        sample = self.samples.get(role)
        return (sample is not None and 0 <= now - sample.received_at < self.FRESH_SECONDS)

    def measure(self, role: str, axis: str, sign_inverted: bool, now: float) -> float | None:
        if not self.fresh(role, now):
            return None
        angle = accelerometer_tilt(self.samples[role].xyz, axis)
        return (-angle if sign_inverted else angle) if angle is not None else None

    def zero(self, now: float, head_axis: str = "pitch", chest_axis: str = "pitch",
             invert_head: bool = False, invert_chest: bool = False) -> bool:
        config = (head_axis, chest_axis, invert_head, invert_chest)
        h = self.measure("head", head_axis, invert_head, now)
        c = self.measure("chest", chest_axis, invert_chest, now)
        if h is None or c is None:
            self.zeroed = False
            return False
        self.reference = {"head": h, "chest": c}
        self.configuration = config
        self.zeroed = True
        return True

    def relative(self, now: float, head_axis: str = "pitch", chest_axis: str = "pitch",
                 invert_head: bool = False, invert_chest: bool = False) -> float | None:
        config = (head_axis, chest_axis, invert_head, invert_chest)
        if not self.zeroed or self.configuration != config:
            return None
        h = self.measure("head", head_axis, invert_head, now)
        c = self.measure("chest", chest_axis, invert_chest, now)
        if h is None or c is None:
            return None
        return wrap_deg(wrap_deg(h - self.reference["head"]) -
                        wrap_deg(c - self.reference["chest"]))
