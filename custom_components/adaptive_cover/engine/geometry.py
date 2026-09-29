"""Pure solar/cover geometry.

Formulas are kept operation-for-operation identical to the historical
implementation in calculation.py so positions reproduce bit-for-bit. The
math is scalar ``math`` (numpy until P2); ``numeric.clip`` is ``np.clip``.
"""

from __future__ import annotations

from datetime import timedelta
from math import atan, cos, degrees, sin, sqrt, tan
from math import radians as rad

from .models import BlindSpot, CoverConfig, SunSnapshot, TimeContext
from .numeric import clip

# When the sun leaves a window less than this before the sunset position
# begins, the sunset position starts right away. Without it such a window
# opens to the default and closes again minutes later (dusk open-then-close).
DUSK_LEAD = timedelta(minutes=30)


def gamma(window_azimuth: float, solar_azimuth: float) -> float:
    """Relative angle between window normal and sun (surface solar azimuth)."""
    return (window_azimuth - solar_azimuth + 180) % 360 - 180


def _missing(name: str) -> TypeError:
    """Build the error for a missing (None) geometry parameter.

    TypeError is what the arithmetic on None raised before the engine was
    typed, so callers see the same exception type as before.
    """
    return TypeError(f"cover geometry is missing {name}")


def _required(value: float | None, name: str) -> float:
    """Return a geometry parameter the formula needs.

    Raises
    ------
    TypeError
        If it is missing (see ``_missing``).

    """
    if value is None:
        raise _missing(name)
    return value


def valid_elevation(
    elevation: float, min_elevation: float | None, max_elevation: float | None
) -> bool:
    """Check whether the sun's elevation is within the configured band.

    The horizon floor is unconditional: with no min_elevation configured the
    sun must still be above 0 deg. (Historically a max-only band dropped the
    floor entirely, so "sun in FOV" stayed true all night and winter climate
    branches held covers open in the dark.)
    """
    floor = 0 if min_elevation is None else min_elevation
    if elevation < floor:
        return False
    if max_elevation is not None and elevation > max_elevation:
        return False
    return True


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
    """Dark outside: from sunset + privacy offset until sunrise + sunrise offset."""
    if config.privacy is None or not config.privacy.enabled:
        return False
    after_dusk = ctx.now_utc > (
        ctx.sunset_utc + timedelta(minutes=config.privacy.offset_min)
    )
    # Dawn release honors the same sunrise offset as sunset_valid; a bare
    # ctx.sunrise_utc held privacy covers closed 20 min past their
    # siblings' morning open (regression 2026-07-02..09).
    before_dawn = ctx.now_utc < (
        ctx.sunrise_utc + timedelta(minutes=config.sunrise_offset_min)
    )
    return after_dusk or before_dawn


# --- overhang & glare band ---


def profile_angle(config: CoverConfig, sun: SunSnapshot) -> float:
    """Return the profile angle in radians.

    Solar elevation projected onto the plane perpendicular to the window.
    Governs how deep sun reaches past horizontal edges (overhangs) and how
    fast rays descend into the room.
    """
    g = gamma(config.window_azimuth, sun.azimuth)
    return atan(tan(rad(sun.elevation)) / cos(rad(g)))


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
    return float(clip(shadow_line, 0, config.window_height))


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
    height = _required(config.window_height, "window_height")
    return round(float(clip(safe, 0, height)) / height * 100)


def dusk_lead_active(config: CoverConfig, sun: SunSnapshot, ctx: TimeContext) -> bool:
    """Check whether the sun left the window within DUSK_LEAD of dusk.

    True while the sun is out of the window, the sunset position begins
    within DUSK_LEAD, and the sun was still in the window when that lead
    began (``ctx.sun_at_dusk_lead``). A sun that left earlier has had the
    cover resting at the default for a while: the configured sunset time
    stands. Unknown (None) never engages.
    """
    if ctx.sun_at_dusk_lead is None or sun_in_fov(config, sun):
        return False
    starts = ctx.sunset_utc + timedelta(minutes=config.sunset_offset_min)
    if not starts - DUSK_LEAD <= ctx.now_utc <= starts:
        return False
    return sun_in_fov(config, ctx.sun_at_dusk_lead)


def default_position(config: CoverConfig, sun: SunSnapshot, ctx: TimeContext) -> float:
    """Rest position: sunset position after dark or at dusk, default otherwise.

    Dusk: when the sun leaves the window less than DUSK_LEAD before the
    sunset position begins, the sunset position starts right away. Resting
    at the default first opened the cover for a few minutes, then closed it.
    """
    if sunset_valid(config, ctx) or dusk_lead_active(config, sun, ctx):
        return config.sunset_position
    return config.default_position


# --- per-cover-type geometry ---


def vertical_blind_height(config: CoverConfig, sun: SunSnapshot) -> float:
    """Height (m) below the blind edge that direct sun may reach."""
    g = gamma(config.window_azimuth, sun.azimuth)
    if config.distance_shaded_area is None:
        raise _missing("distance_shaded_area")
    # np.clip semantics: no window_height means no upper bound.
    return clip(
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
    return round(position / _required(config.window_height, "window_height") * 100)


def awning_extension(config: CoverConfig, sun: SunSnapshot) -> float:
    """Return the required awning extension length (m), clipped to the awning."""
    awn_angle = 90 - _required(config.awning_angle, "awning_angle")
    a_angle = 90 - sun.elevation
    c_angle = 180 - awn_angle - a_angle
    vertical_position = vertical_blind_height(config, sun)
    denominator = sin(rad(c_angle))
    # Degenerate geometry (awning_angle + elevation ~ 0, e.g. flat awning at
    # sunrise) makes the sine-rule denominator 0: division yields inf and
    # round(inf) raised OverflowError in the update loop. Full extension is
    # the physical answer: rays are parallel to the awning plane.
    if abs(denominator) < 1e-9:
        return float(_required(config.awning_length, "awning_length"))
    extension = (
        (_required(config.window_height, "window_height") - vertical_position)
        * sin(rad(a_angle))
    ) / denominator
    # np.clip semantics: no awning_length means no upper bound.
    return float(clip(extension, 0, config.awning_length))


def awning_percentage(config: CoverConfig, sun: SunSnapshot) -> float:
    """Awning position as % of awning length (0-100 after extension clip)."""
    return round(
        awning_extension(config, sun)
        / _required(config.awning_length, "awning_length")
        * 100
    )


def tilt_beta(config: CoverConfig, sun: SunSnapshot) -> float:
    """Historical alias: the tilt formula's beta IS the profile angle."""
    return profile_angle(config, sun)


def tilt_slat_angle(config: CoverConfig, sun: SunSnapshot) -> float:
    """Venetian slat angle (degrees), per MDPI 1996-1073/13/7/1731."""
    beta = tilt_beta(config, sun)
    ratio = _required(config.slat_distance, "slat_distance") / _required(
        config.slat_depth, "slat_depth"
    )
    # With slat_distance > slat_depth (the UI allows it) the discriminant
    # can go negative at low profile angles; sqrt would produce NaN and
    # round(NaN) kills the update loop. Clamp to 0: max-blocking angle.
    discriminant = clip((tan(beta) ** 2) - (ratio**2) + 1, 0, None)
    slat = 2 * atan((tan(beta) + sqrt(discriminant)) / (1 + ratio))
    return degrees(slat)


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
