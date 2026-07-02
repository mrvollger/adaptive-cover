"""Pure solar/cover geometry.

Formulas are kept operation-for-operation identical to the historical
implementation in calculation.py so positions reproduce bit-for-bit.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
from numpy import cos, sin, tan
from numpy import radians as rad

from .models import BlindSpot, CoverConfig, SunSnapshot, TimeContext


def gamma(window_azimuth: float, solar_azimuth: float) -> float:
    """Relative angle between window normal and sun (surface solar azimuth)."""
    return (window_azimuth - solar_azimuth + 180) % 360 - 180


def valid_elevation(
    elevation: float, min_elevation: float | None, max_elevation: float | None
) -> bool:
    """Check whether the sun's elevation is within the configured band."""
    if min_elevation is None and max_elevation is None:
        return elevation >= 0
    if min_elevation is None:
        return elevation <= max_elevation
    if max_elevation is None:
        return elevation >= min_elevation
    return min_elevation <= elevation <= max_elevation


def sun_in_fov(config: CoverConfig, sun: SunSnapshot) -> bool:
    """Sun in front of the window (FOV clipped to +/-90) and elevation valid."""
    g = gamma(config.window_azimuth, sun.azimuth)
    azi_min = min(config.fov_left, 90)
    azi_max = min(config.fov_right, 90)
    return bool(
        (g < azi_min)
        & (g > -azi_max)
        & valid_elevation(sun.elevation, config.min_elevation, config.max_elevation)
    )


def in_blind_spot(config: CoverConfig, sun: SunSnapshot) -> bool:
    """Check whether the sun is inside the configured blind-spot region."""
    spot: BlindSpot = config.blind_spot
    if spot.left is None or spot.right is None or not spot.enabled:
        return False
    g = gamma(config.window_azimuth, sun.azimuth)
    left_edge = config.fov_left - spot.left
    right_edge = config.fov_left - spot.right
    inside = (g <= left_edge) & (g >= right_edge)
    if spot.elevation is not None:
        inside = inside & (sun.elevation <= spot.elevation)
    return bool(inside)


def sunset_valid(config: CoverConfig, ctx: TimeContext) -> bool:
    """After sunset+offset or before sunrise+offset (naive-UTC arithmetic)."""
    after_sunset = ctx.now_utc > (
        ctx.sunset_utc + timedelta(minutes=config.sunset_offset_min)
    )
    before_sunrise = ctx.now_utc < (
        ctx.sunrise_utc + timedelta(minutes=config.sunrise_offset_min)
    )
    return after_sunset or before_sunrise


def direct_sun_valid(config: CoverConfig, sun: SunSnapshot, ctx: TimeContext) -> bool:
    """Check for actionable direct sun.

    Sun in front, not after sunset, not in the blind spot, and the glass
    not already fully shaded by an overhang.
    """
    return (
        sun_in_fov(config, sun)
        & (not sunset_valid(config, ctx))
        & (not in_blind_spot(config, sun))
        & (not window_fully_shaded(config, sun))
    )


def privacy_active(config: CoverConfig, ctx: TimeContext) -> bool:
    """Dark outside: from sunset + privacy offset until sunrise."""
    if config.privacy is None or not config.privacy.enabled:
        return False
    after_dusk = ctx.now_utc > (
        ctx.sunset_utc + timedelta(minutes=config.privacy.offset_min)
    )
    before_dawn = ctx.now_utc < ctx.sunrise_utc
    return after_dusk or before_dawn


# --- overhang & glare band ---


def profile_angle(config: CoverConfig, sun: SunSnapshot) -> float:
    """Return the profile angle in radians.

    Solar elevation projected onto the plane perpendicular to the window.
    Governs how deep sun reaches past horizontal edges (overhangs) and how
    fast rays descend into the room.
    """
    g = gamma(config.window_azimuth, sun.azimuth)
    return np.arctan(tan(rad(sun.elevation)) / cos(rad(g)))


def sunlit_top(config: CoverConfig, sun: SunSnapshot) -> float:
    """Height (m above sill) of the top of the sunlit band on the glass.

    Without an overhang the whole window can be sunlit. With one, glass
    above the shadow line never sees direct sun.
    """
    if config.window_height is None:
        raise ValueError("sunlit_top requires window_height")
    if config.overhang is None:
        return config.window_height
    shadow_line = config.overhang.height_above_sill - config.overhang.depth * tan(
        profile_angle(config, sun)
    )
    return float(np.clip(shadow_line, 0, config.window_height))


def window_fully_shaded(config: CoverConfig, sun: SunSnapshot) -> bool:
    """Check whether the overhang shades the entire window right now."""
    if config.overhang is None or config.window_height is None:
        return False
    if sun.elevation <= 0:
        return False
    return sunlit_top(config, sun) <= 0


def glare_safe_height(config: CoverConfig, sun: SunSnapshot) -> float:
    """Return the highest glare-safe entry height (m above sill).

    Rays entering at or below this height stay below eye level at the
    nearest occupied distance.
    """
    if config.glare is None:
        raise ValueError("glare_safe_height requires a GlareModel")
    return config.glare.eye_height + config.glare.occupied_distance * float(
        tan(profile_angle(config, sun))
    )


def admit_no_glare_percentage(config: CoverConfig, sun: SunSnapshot) -> float:
    """Position (% open) that admits maximum sun without eye-level glare.

    The cover edge may sit at the glare-safe height; if the overhang's
    shadow line is already at or below it, no coverage is needed at all.
    """
    top = sunlit_top(config, sun)
    safe = glare_safe_height(config, sun)
    if top <= safe:
        return 100
    return round(float(np.clip(safe, 0, config.window_height))
                 / config.window_height * 100)


def default_position(config: CoverConfig, ctx: TimeContext) -> float:
    """Rest position: sunset position after dark, default otherwise."""
    if sunset_valid(config, ctx):
        return config.sunset_position
    return config.default_position


# --- per-cover-type geometry ---


def vertical_blind_height(config: CoverConfig, sun: SunSnapshot) -> float:
    """Height (m) below the blind edge that direct sun may reach."""
    g = gamma(config.window_azimuth, sun.azimuth)
    return np.clip(
        (config.distance_shaded_area / cos(rad(g))) * tan(rad(sun.elevation)),
        0,
        config.window_height,
    )


def vertical_percentage(config: CoverConfig, sun: SunSnapshot) -> float:
    """Vertical blind position as % of window height.

    With an overhang: if the shadow line is at or below the edge height the
    penetration model requires, the blind can open fully - glass above the
    shadow line admits no direct sun anyway.
    """
    position = vertical_blind_height(config, sun)
    if config.overhang is not None and sunlit_top(config, sun) <= position:
        return 100
    return round(position / config.window_height * 100)


def awning_extension(config: CoverConfig, sun: SunSnapshot) -> float:
    """Return the required awning extension length (m); historically unclipped."""
    awn_angle = 90 - config.awning_angle
    a_angle = 90 - sun.elevation
    c_angle = 180 - awn_angle - a_angle
    vertical_position = vertical_blind_height(config, sun)
    return ((config.window_height - vertical_position) * sin(rad(a_angle))) / sin(
        rad(c_angle)
    )


def awning_percentage(config: CoverConfig, sun: SunSnapshot) -> float:
    """Awning position as % of awning length (may exceed 0-100 pre-clip)."""
    return round(awning_extension(config, sun) / config.awning_length * 100)


def tilt_beta(config: CoverConfig, sun: SunSnapshot) -> float:
    """Historical alias: the tilt formula's beta IS the profile angle."""
    return profile_angle(config, sun)


def tilt_slat_angle(config: CoverConfig, sun: SunSnapshot) -> float:
    """Venetian slat angle (degrees), per MDPI 1996-1073/13/7/1731."""
    beta = tilt_beta(config, sun)
    ratio = config.slat_distance / config.slat_depth
    slat = 2 * np.arctan(
        (tan(beta) + np.sqrt((tan(beta) ** 2) - (ratio**2) + 1)) / (1 + ratio)
    )
    return np.rad2deg(slat)


def tilt_percentage(config: CoverConfig, sun: SunSnapshot) -> float:
    """Tilt position as % (mode1: 0-90 deg range; mode2: 0-180 deg)."""
    angle = tilt_slat_angle(config, sun)
    if config.tilt_mode == "mode1":
        return round(angle / 90 * 100)
    return round(angle / 180 * 100)


def calculated_percentage(config: CoverConfig, sun: SunSnapshot) -> float:
    """Dispatch to the cover-type-specific percentage."""
    if config.cover_type == "vertical":
        return vertical_percentage(config, sun)
    if config.cover_type == "awning":
        return awning_percentage(config, sun)
    if config.cover_type == "tilt":
        return tilt_percentage(config, sun)
    raise ValueError(f"Unknown cover type: {config.cover_type}")
