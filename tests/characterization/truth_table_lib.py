"""Shared machinery for the climate-mode truth table.

Enumerates a cross-product of climate inputs and evaluates the engine seam
``engine.evaluate(CoverConfig, SunSnapshot, TimeContext, ClimateInputs)``
for each combination. The recorded outputs (``climate_truth_table.json``)
are the spec that any refactor of the climate logic must reproduce.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from custom_components.adaptive_cover.engine import evaluate as engine_evaluate
from custom_components.adaptive_cover.engine.models import (
    ClimateInputs,
    CoverConfig,
    SunSnapshot,
    TimeContext,
)

TRUTH_TABLE_PATH = Path(__file__).parent / "climate_truth_table.json"

TEMP_LOW = 21.0
TEMP_HIGH = 23.0
WEATHER_CONDITIONS = ["sunny", "partlycloudy", "clear"]

# Sun positions: "valid" puts the sun square in front of a south window at
# 45 deg elevation; "invalid" puts it behind the window (north).
SUN_VALID = (180.0, 45.0)
SUN_INVALID = (0.0, 45.0)

PRESENCE_CASES = {
    "none": (None, None),
    "home": ("device_tracker.person", "home"),
    "away": ("device_tracker.person", "not_home"),
}
TEMP_CASES = {"cold": 18.0, "mid": 22.0, "hot": 26.0}
WEATHER_CASES = {
    "none": (None, None),
    "sunny": ("weather.home", "sunny"),
    "cloudy": ("weather.home", "cloudy"),
}
BLIND_CASES = ["cover_blind", "tilt_mode1", "tilt_mode2"]

# Mid-day between sunrise and sunset: sunset_valid is False, matching the
# historical mocked SunData (sunset far ahead, sunrise far behind).
_CTX = TimeContext(
    now_utc=datetime(2026, 6, 21, 12, 0, 0),
    sunrise_utc=datetime(2026, 6, 21, 0, 0, 1),
    sunset_utc=datetime(2026, 6, 21, 23, 59, 59),
)


def _make_config(blind_case: str) -> CoverConfig:
    """Engine config for one blind case (mirrors the historical fixtures)."""
    common = dict(
        window_azimuth=180,
        fov_left=90,
        fov_right=90,
        default_position=60,
        sunset_position=0,
        sunset_offset_min=0,
        sunrise_offset_min=0,
        min_elevation=None,
        max_elevation=None,
    )
    if blind_case == "cover_blind":
        return CoverConfig(
            cover_type="vertical",
            distance_shaded_area=0.5,
            window_height=2.1,
            **common,
        )
    mode = "mode1" if blind_case == "tilt_mode1" else "mode2"
    return CoverConfig(
        cover_type="tilt",
        slat_distance=2,
        slat_depth=3,
        tilt_mode=mode,
        **common,
    )


def combo_key(presence, temp, weather, blind, valid, transparent):
    """Stable string key for one combination."""
    return (
        f"presence={presence}|temp={temp}|weather={weather}"
        f"|blind={blind}|valid={valid}|transparent={transparent}"
    )


def iter_combos():
    """Yield every combination in the truth table."""
    for presence in PRESENCE_CASES:
        for temp in TEMP_CASES:
            for weather in WEATHER_CASES:
                for blind in BLIND_CASES:
                    for valid in (True, False):
                        transparents = (
                            (False, True) if blind == "cover_blind" else (False,)
                        )
                        for transparent in transparents:
                            yield presence, temp, weather, blind, valid, transparent


def _resolve_inputs(presence, temp, weather, transparent):
    """Resolve one combo's readings the way the adapter would.

    presence: no entity -> present; device_tracker -> state == "home".
    season: inside temp vs thresholds (no outside entity -> outside_high
    permissive). weather: no entity -> sunny; entity -> condition-list match.
    """
    _, presence_state = PRESENCE_CASES[presence]
    weather_entity, weather_state = WEATHER_CASES[weather]
    temp_value = TEMP_CASES[temp]
    if weather_entity is None:
        is_sunny = True
    else:
        is_sunny = weather_state in WEATHER_CONDITIONS
    return ClimateInputs(
        presence=presence_state is None or presence_state == "home",
        is_summer=temp_value > TEMP_HIGH,
        is_winter=temp_value < TEMP_LOW,
        is_sunny=is_sunny,
        lux_dim=False,
        irradiance_dim=False,
        transparent_blind=bool(transparent),
    )


def evaluate_combo(presence, temp, weather, blind, valid, transparent):
    """Run the engine for one combination."""
    config = _make_config(blind)
    sol_azi, sol_elev = SUN_VALID if valid else SUN_INVALID
    inputs = _resolve_inputs(presence, temp, weather, transparent)
    decision = engine_evaluate(
        config,
        SunSnapshot(azimuth=sol_azi, elevation=sol_elev),
        _CTX,
        inputs,
    )
    return {
        "state": round(float(decision.position)),
        "is_summer": inputs.is_summer,
        "is_winter": inputs.is_winter,
        "is_presence": inputs.presence,
    }


def build_table():
    """Evaluate every combination and return {key: result}."""
    return {
        combo_key(*combo): evaluate_combo(*combo) for combo in iter_combos()
    }


def load_table():
    """Load the committed truth table."""
    return json.loads(TRUTH_TABLE_PATH.read_text())
