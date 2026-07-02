"""Decision evaluation: reproduce the historical strategy classes, traced.

evaluate() is the single entry point. With climate=None it reproduces
NormalCoverState.get_state(); with ClimateInputs it reproduces
ClimateCoverState.get_state() branch-for-branch, including quirks:

- climate branch outputs (0/100/tilt presets) are NOT clipped to 0-100,
  only min/max-limited, exactly like the current code
- min/max limits apply to the basic path after clipping
- the "not sunny" bundle is (lux_dim or irradiance_dim or not is_sunny)
"""

from __future__ import annotations

import numpy as np

from . import geometry
from .models import (
    ClimateInputs,
    CoverConfig,
    Decision,
    Intent,
    SunSnapshot,
    TimeContext,
)


def _apply_limits(
    result: float, dsv: bool, config: CoverConfig, trace: list[str]
) -> float:
    limits = config.limits
    apply_max = limits.max_position is not None and limits.max_position != 100
    if apply_max and limits.max_only_when_sun:
        apply_max = dsv
    if apply_max and result > limits.max_position:
        trace.append(f"max limit {limits.max_position} applied (was {result})")
        return limits.max_position

    apply_min = limits.min_position is not None and limits.min_position != 0
    if apply_min and limits.min_only_when_sun:
        apply_min = dsv
    if apply_min and result < limits.min_position:
        trace.append(f"min limit {limits.min_position} applied (was {result})")
        return limits.min_position
    return result


def _evaluate_basic(
    config: CoverConfig, sun: SunSnapshot, ctx: TimeContext, trace: list[str]
) -> tuple[float, Intent]:
    dsv = geometry.direct_sun_valid(config, sun, ctx)
    if dsv:
        raw = geometry.calculated_percentage(config, sun)
        intent = Intent.CALCULATED
        trace.append(f"sun in window: calculated {raw}")
    else:
        raw = geometry.default_position(config, ctx)
        if geometry.sunset_valid(config, ctx):
            intent = Intent.SUNSET
            trace.append(f"after sunset/before sunrise: sunset position {raw}")
        elif geometry.window_fully_shaded(config, sun) and geometry.sun_in_fov(
            config, sun
        ):
            intent = Intent.SHADED_BY_OVERHANG
            trace.append(f"overhang shades whole window: default {raw}")
        else:
            intent = Intent.DEFAULT
            trace.append(f"sun not in window: default {raw}")
    result = np.clip(raw, 0, 100)
    result = _apply_limits(result, dsv, config, trace)
    return result, intent


def _admits_glare_position(config: CoverConfig) -> bool:
    """Glare-limited admission applies only where eyes and beams meet:
    vertical covers with a configured glare model."""
    return config.glare is not None and config.cover_type == "vertical"


def _not_sunny(climate: ClimateInputs) -> bool:
    return climate.lux_dim or climate.irradiance_dim or not climate.is_sunny


def _evaluate_climate_normal(
    config: CoverConfig,
    sun: SunSnapshot,
    ctx: TimeContext,
    climate: ClimateInputs,
    trace: list[str],
) -> tuple[float, Intent]:
    """Vertical/awning covers under climate control."""
    valid = geometry.sun_in_fov(config, sun)

    if not climate.presence:
        trace.append("no presence")
        if valid:
            if climate.is_summer:
                trace.append("summer, away: close fully")
                return 0, Intent.CLIMATE_BLOCK_HEAT
            if climate.is_winter:
                trace.append("winter, away: open fully (nobody to glare)")
                return 100, Intent.CLIMATE_OPEN_HEAT
        raw = geometry.default_position(config, ctx)
        trace.append(f"away, sun not relevant: default {raw}")
        return raw, Intent.CLIMATE_DEFAULT

    if not climate.is_summer and _not_sunny(climate):
        if climate.is_winter and valid:
            trace.append("winter, dim/cloudy: open fully (no beam, no glare)")
            return 100, Intent.CLIMATE_OPEN_HEAT
        raw = geometry.default_position(config, ctx)
        trace.append(f"not summer, dim/cloudy: default {raw}")
        return raw, Intent.CLIMATE_DEFAULT

    if climate.is_summer and climate.transparent_blind:
        trace.append("summer, transparent blind: close fully")
        return 0, Intent.CLIMATE_BLOCK_HEAT

    # Presence + direct sun + heating wanted: the historical tree fell
    # through to full glare-blocking here, giving 'sunny winter day = cave'.
    # With a glare model, admit warmth up to the eye band instead.
    if (
        climate.is_winter
        and _admits_glare_position(config)
        and geometry.direct_sun_valid(config, sun, ctx)
    ):
        raw = geometry.admit_no_glare_percentage(config, sun)
        trace.append(f"winter, sunny, someone home: admit warmth to eye band ({raw})")
        return raw, Intent.ADMIT_NO_GLARE

    trace.append("climate neutral: basic strategy")
    return _evaluate_basic(config, sun, ctx, trace)


def _evaluate_climate_tilt(
    config: CoverConfig,
    sun: SunSnapshot,
    ctx: TimeContext,
    climate: ClimateInputs,
    trace: list[str],
) -> tuple[float, Intent]:
    """Tilt covers under climate control."""
    degrees = 180 if config.tilt_mode == "mode2" else 90
    valid = geometry.sun_in_fov(config, sun)

    if climate.presence:
        if valid and _not_sunny(climate):
            if climate.is_summer:
                trace.append("tilt, summer, dim: 45 deg preset")
                return 45 / degrees * 100, Intent.CLIMATE_TILT_PRESET
            trace.append("tilt, dim: basic strategy")
            return _evaluate_basic(config, sun, ctx, trace)
        trace.append("tilt, presence: 80 deg preset")
        return 80 / degrees * 100, Intent.CLIMATE_TILT_PRESET

    beta = np.rad2deg(geometry.tilt_beta(config, sun))
    if valid:
        if climate.is_summer:
            trace.append("tilt, summer, away: close fully")
            return 0, Intent.CLIMATE_BLOCK_HEAT
        if climate.is_winter and config.tilt_mode == "mode2":
            trace.append("tilt, winter, away: parallel to beams")
            return (beta + 90) / degrees * 100, Intent.CLIMATE_OPEN_HEAT
        trace.append("tilt, away: 80 deg preset")
        return 80 / degrees * 100, Intent.CLIMATE_TILT_PRESET
    trace.append("tilt, away, sun not in window: basic strategy")
    return _evaluate_basic(config, sun, ctx, trace)


def evaluate(
    config: CoverConfig,
    sun: SunSnapshot,
    ctx: TimeContext,
    climate: ClimateInputs | None = None,
) -> Decision:
    """Compute the target position for one instant."""
    trace: list[str] = []

    # Privacy runs before everything: a lit room against a dark sky is
    # visible from outside no matter what solar/climate logic says.
    if geometry.privacy_active(config, ctx):
        trace.append(
            f"dark outside: privacy position {config.privacy.position}"
        )
        result = _apply_limits(
            config.privacy.position, False, config, trace
        )
        return Decision(position=result, intent=Intent.PRIVACY, trace=tuple(trace))

    if climate is None:
        result, intent = _evaluate_basic(config, sun, ctx, trace)
        return Decision(position=result, intent=intent, trace=tuple(trace))

    if config.cover_type == "tilt":
        result, intent = _evaluate_climate_tilt(config, sun, ctx, climate, trace)
    else:
        result, intent = _evaluate_climate_normal(config, sun, ctx, climate, trace)
    dsv = geometry.direct_sun_valid(config, sun, ctx)
    result = _apply_limits(result, dsv, config, trace)
    return Decision(position=result, intent=intent, trace=tuple(trace))
