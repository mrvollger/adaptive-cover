"""Shared machinery for the climate-mode truth table.

Enumerates a cross-product of climate inputs and evaluates the CURRENT
``ClimateCoverState`` implementation for each combination. The recorded
outputs (``climate_truth_table.json``) are the spec that the intent-rule
refactor must reproduce.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.adaptive_cover.calculation import (
    AdaptiveTiltCover,
    AdaptiveVerticalCover,
    ClimateCoverData,
    ClimateCoverState,
)
from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
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


class _FakeStates:
    """Minimal stand-in for hass.states supporting get()."""

    def __init__(self):
        self._states = {}

    def set(self, entity_id, state, attributes=None):
        self._states[entity_id] = SimpleNamespace(
            state=state, attributes=attributes or {}
        )

    def get(self, entity_id):
        return self._states.get(entity_id)


def _make_logger():
    logger = ConfigContextAdapter(logging.getLogger("truth_table"))
    logger.set_config_name("TruthTable")
    return logger


def _make_hass(temp, presence_entity, presence_state, weather_entity, weather_state):
    hass = MagicMock()
    states = _FakeStates()
    states.set("sensor.indoor_temp", str(temp))
    if presence_entity:
        states.set(presence_entity, presence_state)
    if weather_entity:
        states.set(weather_entity, weather_state)
    hass.states = states
    return hass


def _cover_kwargs(sol_azi, sol_elev):
    return dict(
        logger=_make_logger(),
        sol_azi=sol_azi,
        sol_elev=sol_elev,
        sunset_pos=0,
        sunset_off=0,
        sunrise_off=0,
        timezone="UTC",
        fov_left=90,
        fov_right=90,
        win_azi=180,
        h_def=60,
        max_pos=None,
        min_pos=None,
        max_pos_bool=False,
        min_pos_bool=False,
        blind_spot_left=None,
        blind_spot_right=None,
        blind_spot_elevation=None,
        blind_spot_on=False,
        min_elevation=None,
        max_elevation=None,
    )


def _make_cover(hass, blind_case, sun):
    sol_azi, sol_elev = sun
    if blind_case == "cover_blind":
        return AdaptiveVerticalCover(
            hass=hass, **_cover_kwargs(sol_azi, sol_elev), distance=0.5, h_win=2.1
        )
    mode = "mode1" if blind_case == "tilt_mode1" else "mode2"
    return AdaptiveTiltCover(
        hass=hass,
        **_cover_kwargs(sol_azi, sol_elev),
        slat_distance=2,
        depth=3,
        mode=mode,
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


def evaluate_combo(presence, temp, weather, blind, valid, transparent):
    """Run the current climate implementation for one combination."""
    presence_entity, presence_state = PRESENCE_CASES[presence]
    weather_entity, weather_state = WEATHER_CASES[weather]
    temp_value = TEMP_CASES[temp]
    hass = _make_hass(
        temp_value, presence_entity, presence_state, weather_entity, weather_state
    )
    sun = SUN_VALID if valid else SUN_INVALID
    cover = _make_cover(hass, blind, sun)
    blind_type = "cover_tilt" if blind.startswith("tilt") else blind
    climate = ClimateCoverData(
        hass=hass,
        logger=_make_logger(),
        temp_entity="sensor.indoor_temp",
        temp_low=TEMP_LOW,
        temp_high=TEMP_HIGH,
        presence_entity=presence_entity,
        weather_entity=weather_entity,
        weather_condition=WEATHER_CONDITIONS if weather_entity else None,
        outside_entity=None,
        temp_switch=False,
        blind_type=blind_type,
        transparent_blind=transparent,
        lux_entity=None,
        irradiance_entity=None,
        lux_threshold=None,
        irradiance_threshold=None,
        temp_summer_outside=0,
        _use_lux=False,
        _use_irradiance=False,
    )
    state = ClimateCoverState(cover, climate)
    return {
        "state": round(float(state.get_state())),
        "is_summer": bool(climate.is_summer),
        "is_winter": bool(climate.is_winter),
        "is_presence": bool(climate.is_presence),
    }


def build_table():
    """Evaluate every combination and return {key: result}."""
    return {
        combo_key(*combo): evaluate_combo(*combo) for combo in iter_combos()
    }


def load_table():
    """Load the committed truth table."""
    return json.loads(TRUTH_TABLE_PATH.read_text())
