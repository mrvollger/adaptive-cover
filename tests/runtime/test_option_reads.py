"""One read per option: CoverGeometry, ClimateOptions and ABSENT (P3).

``ShadeConfig`` carries what the cover and climate adapters read, so every
option has one read with one fallback (``ABSENT``). Config migration 1.3
writes those fallbacks into entries (``absent_options``), which must not
change any read.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_CLIMATE_MODE,
    CONF_DELTA_POSITION,
    CONF_ENTITIES,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MODE,
    CONF_OUTSIDE_THRESHOLD,
    CONF_PRIVACY_MODE,
    CONF_PRIVACY_OFFSET,
    CONF_PRIVACY_POSITION,
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_TILT_DEPTH,
    CONF_WEATHER_STATE,
    DEFAULT_MANUAL_OVERRIDE_DURATION,
)
from custom_components.adaptive_cover.runtime.shade_config import (
    ABSENT,
    ClimateOptions,
    CoverGeometry,
    ShadeConfig,
    absent_options,
)
from custom_components.adaptive_cover.settings.spec import OPTS

# Spec keys the runtime never reads: the migration has nothing to freeze.
NOT_READ = {CONF_MODE, CONF_ENTITIES, CONF_SUNRISE_OFFSET}


def test_every_spec_option_has_a_runtime_fallback():
    """A new option must say what it reads as when unset."""
    spec_keys = {opt.key for opt in OPTS}
    assert spec_keys - NOT_READ <= set(ABSENT), sorted(
        spec_keys - NOT_READ - set(ABSENT)
    )
    assert set(ABSENT) <= spec_keys


def test_geometry_fallbacks():
    geometry = CoverGeometry.from_options({})
    assert geometry.max_pos_bool is False
    assert geometry.min_pos_bool is False
    assert geometry.blind_spot_on is False
    assert geometry.privacy_offset == 30
    assert geometry.privacy_position == 0
    assert geometry.win_azi is None
    assert geometry.sunrise_off is None


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({CONF_SUNSET_OFFSET: 15}, 15),  # unset: the sunset offset
        ({CONF_SUNSET_OFFSET: 15, CONF_SUNRISE_OFFSET: -5}, -5),
        ({CONF_SUNSET_OFFSET: 15, CONF_SUNRISE_OFFSET: None}, None),
    ],
)
def test_sunrise_offset_falls_back_to_the_sunset_offset(options, expected):
    assert CoverGeometry.from_options(options).sunrise_off == expected


@pytest.mark.parametrize(
    ("stored", "expected"),
    [({}, 30), ({CONF_PRIVACY_OFFSET: None}, 30), ({CONF_PRIVACY_OFFSET: 0}, 0)],
    ids=["unset", "none", "zero_kept"],
)
def test_privacy_offset_zero_is_not_the_fallback(stored, expected):
    assert CoverGeometry.from_options(stored).privacy_offset == expected


@pytest.mark.parametrize("stored", [{}, {CONF_PRIVACY_POSITION: None}])
def test_privacy_position_reads_zero_for_the_engine(stored):
    assert CoverGeometry.from_options(stored).privacy_position == 0
    # the gates keep the raw value (None is never a position)
    assert ShadeConfig.from_options(stored).privacy_position is None


def test_climate_options_land_in_their_fields():
    climate = ClimateOptions.from_options(
        {CONF_WEATHER_STATE: ["sunny"], CONF_OUTSIDE_THRESHOLD: 18}
    )
    assert climate.weather_condition == ["sunny"]
    assert climate.temp_summer_outside == 18
    assert ClimateOptions.from_options({}).weather_condition is None


def test_setup_flags_use_the_coordinator_fallbacks():
    config = ShadeConfig.from_options({})
    assert (
        config.climate_mode,
        config.inverse_state,
        config.interpolation,
        config.return_sunset,
        config.ignore_intermediate,
    ) == (False, False, False, None, False)
    assert ShadeConfig.from_options({CONF_CLIMATE_MODE: True}).climate_mode is True


def test_absent_options_fill_only_missing_keys():
    stored = {CONF_AZIMUTH: 190, CONF_PRIVACY_MODE: None, CONF_SUNSET_OFFSET: 20}
    missing = absent_options(stored)
    assert CONF_AZIMUTH not in missing
    assert CONF_PRIVACY_MODE not in missing  # stored None stays None
    assert missing[CONF_SUNRISE_OFFSET] == 20
    assert missing[CONF_DELTA_POSITION] == 1
    assert absent_options({**stored, **missing}) == {}


def test_absent_options_copy_mutable_fallbacks():
    missing = absent_options({})
    missing[CONF_MANUAL_OVERRIDE_DURATION]["hours"] = 9
    assert DEFAULT_MANUAL_OVERRIDE_DURATION["hours"] == 2


def _random_options(rng: random.Random) -> dict[str, Any]:
    """A random subset of options, some stored as None, some as values."""
    options: dict[str, Any] = {}
    for key in [*ABSENT, CONF_SUNRISE_OFFSET]:
        roll = rng.random()
        if roll < 0.4:
            continue  # unset
        if roll < 0.55:
            options[key] = None
        else:
            options[key] = rng.choice([0, 1, 7, 45.5, True, False, "x", ["a"]])
    return options


@pytest.mark.parametrize("seed", range(200))
def test_writing_the_fallbacks_changes_no_read(seed):
    """Property: absent_options is invisible to every runtime read."""
    options = _random_options(random.Random(seed))
    filled = {**options, **absent_options(options)}
    assert ShadeConfig.from_options(filled) == ShadeConfig.from_options(options)


def test_tilt_fields_read_under_their_adapter_names():
    assert CoverGeometry.from_options({CONF_TILT_DEPTH: 3}).slat_depth == 3
