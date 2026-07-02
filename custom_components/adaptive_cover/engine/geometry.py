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
    """Is the sun's elevation within the configured band?"""
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
    """Is the sun inside the configured blind-spot region?"""
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
    """Sun in front, not after sunset, not in the blind spot."""
    return (
        sun_in_fov(config, sun)
        & (not sunset_valid(config, ctx))
        & (not in_blind_spot(config, sun))
    )


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
    """Vertical blind position as % of window height."""
    position = vertical_blind_height(config, sun)
    return round(position / config.window_height * 100)


def awning_extension(config: CoverConfig, sun: SunSnapshot) -> float:
    """Required awning extension length (m). NOTE: historically unclipped."""
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
    """Profile angle beta (radians): elevation projected onto window normal."""
    g = gamma(config.window_azimuth, sun.azimuth)
    return np.arctan(tan(rad(sun.elevation)) / cos(rad(g)))


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
