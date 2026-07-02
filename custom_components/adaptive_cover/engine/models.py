"""Typed inputs and outputs for the pure engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Intent(StrEnum):
    """What the engine is trying to achieve with the chosen position."""

    CALCULATED = "calculated"  # track the sun geometrically
    DEFAULT = "default"  # sun not relevant: rest position
    SUNSET = "sunset"  # after sunset / before sunrise position
    CLIMATE_OPEN_HEAT = "climate_open_heat"  # winter: maximize gain
    CLIMATE_BLOCK_HEAT = "climate_block_heat"  # summer: minimize gain
    CLIMATE_DEFAULT = "climate_default"  # climate says nothing special
    CLIMATE_TILT_PRESET = "climate_tilt_preset"  # tilt-specific fixed angles


@dataclass(frozen=True)
class SunSnapshot:
    """Solar position at one instant."""

    azimuth: float
    elevation: float


@dataclass(frozen=True)
class TimeContext:
    """Time inputs the engine may not read from the wall clock.

    All naive-UTC to reproduce the current implementation's arithmetic
    (a naive UTC wall-clock read vs astral times with tzinfo stripped).
    """

    now_utc: datetime
    sunrise_utc: datetime
    sunset_utc: datetime


@dataclass(frozen=True)
class BlindSpot:
    """Azimuth/elevation region where an obstacle already blocks the sun."""

    left: float | None = None
    right: float | None = None
    elevation: float | None = None
    enabled: bool = False


@dataclass(frozen=True)
class PositionLimits:
    """Clamps applied after the raw position is computed."""

    min_position: float | None = None
    max_position: float | None = None
    min_only_when_sun: bool = False
    max_only_when_sun: bool = False


@dataclass(frozen=True)
class CoverConfig:
    """Full static configuration of one cover."""

    cover_type: str  # "vertical" | "awning" | "tilt"
    window_azimuth: float
    fov_left: float
    fov_right: float
    default_position: float
    sunset_position: float
    sunset_offset_min: float = 0
    sunrise_offset_min: float = 0
    min_elevation: float | None = None
    max_elevation: float | None = None
    blind_spot: BlindSpot = field(default_factory=BlindSpot)
    limits: PositionLimits = field(default_factory=PositionLimits)
    # vertical + awning
    distance_shaded_area: float | None = None
    window_height: float | None = None
    # awning
    awning_length: float | None = None
    awning_angle: float | None = None
    # tilt
    slat_distance: float | None = None
    slat_depth: float | None = None
    tilt_mode: str = "mode2"


@dataclass(frozen=True)
class ClimateInputs:
    """Resolved climate readings (entity access happens in the adapter)."""

    presence: bool = True
    is_summer: bool = False
    is_winter: bool = False
    # tri-state to reproduce current behavior: None = weather entity set but
    # no condition list configured (treated as "not sunny" downstream).
    is_sunny: bool | None = True
    lux_dim: bool = False
    irradiance_dim: bool = False
    transparent_blind: bool = False


@dataclass(frozen=True)
class Decision:
    """Engine output: what to do and why."""

    position: float
    intent: Intent
    trace: tuple[str, ...] = ()
