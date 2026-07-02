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
    ADMIT_NO_GLARE = "admit_no_glare"  # let warmth in, keep sun out of eyes
    SHADED_BY_OVERHANG = "shaded_by_overhang"  # architecture already shades
    PRIVACY = "privacy"  # dark outside, lit inside: close
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
class Overhang:
    """Fixed horizontal shade (balcony, eave) above the window.

    Casts a shadow line onto the glass at
    ``height_above_sill - depth * tan(profile_angle)``; glass above that
    line never sees direct sun, so the cover need not protect it.
    """

    depth: float  # m, horizontal projection out from the facade
    height_above_sill: float  # m, underside height above the window sill


@dataclass(frozen=True)
class GlareModel:
    """Where eyes are, for the admit-warmth-but-no-glare objective.

    A ray entering the glass at height h descends at the profile angle and
    reaches ``eye_height`` at horizontal distance
    ``(h - eye_height) / tan(profile)``. The cover only needs to block
    entry above ``eye_height + occupied_distance * tan(profile)``.
    """

    eye_height: float  # m above the sill (seated eyes ~1.2 m)
    occupied_distance: float  # m from window to nearest occupied spot


@dataclass(frozen=True)
class PrivacyConfig:
    """Close after dusk regardless of solar/climate logic.

    Active from ``sunset + offset_min`` until sunrise. Runs before every
    other rule: a lit room with a dark sky is visible from outside no
    matter what the thermometer says.
    """

    enabled: bool = False
    offset_min: float = 30
    position: float = 0


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
    overhang: Overhang | None = None  # vertical covers only
    glare: GlareModel | None = None  # vertical covers only
    privacy: PrivacyConfig | None = None
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
