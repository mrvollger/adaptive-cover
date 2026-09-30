"""The pure layered-settings store (settings/shadow.py, window_record.py).

- The toggles that replaced the per-window switches are layered settings
  of their own (``TOGGLE_OPTS``), outside ``OPTS``, so no window form or
  service shows them.
- ``legacy_values`` = a window's flat options plus its toggle values.
- Stored layers round-trip through the house options and the window
  records: every lifted window compares equal, whatever its toggles.
- A v2.0 window's own overrides are the ones naming it (a copy's are not).
- A differing option is reported (30 == 30.0; a bool is not a number).
- ``adopt`` lifts one new window against stored layers exactly.
- The provenance summary leaves out house, default and one-time values.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import Any

import pytest

from custom_components.adaptive_cover.const import (
    CONF_DEFAULT_HEIGHT,
    CONF_MANUAL_DETECTION,
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_POS,
    CONF_TEMP_ENTITY,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
)
from custom_components.adaptive_cover.runtime.shade_config import absent_options
from custom_components.adaptive_cover.settings.lift import LegacyWindow, placements
from custom_components.adaptive_cover.settings.normalize import normalize_cover
from custom_components.adaptive_cover.settings.resolve import (
    Placement,
    Resolution,
    Source,
    WindowOverrides,
)
from custom_components.adaptive_cover.settings.shadow import (
    SHADOW_SPEC,
    TOGGLE_KEYS,
    TOGGLE_OPTS,
    adopt,
    compare,
    differing_keys,
    hub_options,
    legacy_values,
    lift_house,
    provenance_summary,
)
from custom_components.adaptive_cover.settings.spec import OPTS, Level
from custom_components.adaptive_cover.settings.window_record import (
    overrides_data,
    overrides_from_data,
    v2_0_overrides,
)

from .house import TEMPERATURE_UNIT, load_house

HOUSE = load_house()
DEFAULTS = {opt.key: opt.default for opt in TOGGLE_OPTS}


def _flat(options: Mapping[str, Any]) -> dict[str, Any]:
    """A window's flat options as the runtime reads them (fallbacks written)."""
    return normalize_cover({**options, **absent_options(options)})


def _house_legacy(toggles_for) -> dict[str, dict]:
    return {
        w.window_key: legacy_values(
            _flat(w.options),
            toggles_for(w.window_key),
            temperature_unit=TEMPERATURE_UNIT,
        )
        for w in HOUSE.windows
    }


def _lift_house(legacy: dict[str, dict]):
    windows = [
        LegacyWindow(w.window_key, legacy[w.window_key], w.area_id)
        for w in HOUSE.windows
    ]
    lifted = lift_house(
        windows, HOUSE.areas, HOUSE.floors, temperature_unit=TEMPERATURE_UNIT
    )
    return lifted, hub_options(lifted)


def test_toggles_are_house_settings_outside_the_option_spec():
    assert not set(TOGGLE_KEYS) & {opt.key for opt in OPTS}
    assert (*OPTS, *TOGGLE_OPTS) == SHADOW_SPEC
    assert {opt.key: opt.home for opt in TOGGLE_OPTS} == dict.fromkeys(
        TOGGLE_KEYS, Level.HOUSE
    )
    # plan: climate on/off and detection per room; the use-flags house-only
    assert {opt.key for opt in TOGGLE_OPTS if Level.AREA in opt.overridable_at} == {
        "climate_on",
        CONF_MANUAL_DETECTION,
    }
    # (the switches' initial states before P5: control, lux and irradiance on)
    assert DEFAULTS == {
        "climate_on": True,
        CONF_USE_OUTSIDE_TEMP: False,
        CONF_USE_LUX: True,
        "use_irradiance": True,
        CONF_MANUAL_DETECTION: True,
    }


def test_legacy_values_are_the_options_plus_the_switches():
    options = {
        **_flat(HOUSE.windows[0].options),
        "overrides": {"window_key": "x"},
        "name": "not an option",
    }
    values = legacy_values(options, {CONF_USE_LUX: False})
    assert set(values) == {opt.key for opt in SHADOW_SPEC}
    assert values[CONF_USE_LUX] is False
    assert values[CONF_MANUAL_DETECTION] is True  # not given: the default
    assert values[CONF_SUNSET_POS] == options[CONF_SUNSET_POS]


def test_stored_layers_round_trip_whatever_the_switches():
    rng = random.Random(1804)
    toggles = {
        w.window_key: {key: rng.random() < 0.5 for key in TOGGLE_KEYS}
        for w in HOUSE.windows
    }
    legacy = _house_legacy(lambda key: toggles[key])
    lifted, hub = _lift_house(legacy)
    # The house options hold the layers and nothing else.
    assert set(hub) == {"house", "floors", "areas", "temperature_unit"}
    where = placements(HOUSE.windows, HOUSE.areas)
    for key, values in legacy.items():
        # A window record stores its overrides; they read back the same.
        overrides = overrides_from_data(overrides_data(lifted.overrides[key]))
        check = compare(key, values, hub, overrides, where[key])
        assert check.differing == (), HOUSE.titles[key]
        assert dict(check.resolved) == values


def test_overrides_belong_to_their_window():
    """A v2.0 window's overrides named their window (window_record.v2_0_overrides)."""
    stored = {"overrides": {"window_key": "a", "values": {"x": 1}, "legacy": {}}}
    assert v2_0_overrides("a", stored) == WindowOverrides(values={"x": 1})
    assert v2_0_overrides("b", stored) is None  # a copy of window a
    assert v2_0_overrides("a", {}) is None


def test_a_changed_legacy_value_differs():
    legacy = _house_legacy(lambda _key: DEFAULTS)
    lifted, hub = _lift_house(legacy)
    key = HOUSE.key("Office north")
    place = placements(HOUSE.windows, HOUSE.areas)[key]
    changed = {**legacy[key], CONF_SUNSET_POS: 40, CONF_USE_OUTSIDE_TEMP: True}
    check = compare(key, changed, hub, lifted.overrides[key], place)
    assert check.differing == (CONF_SUNSET_POS, CONF_USE_OUTSIDE_TEMP)


@pytest.mark.parametrize(
    ("resolved", "legacy", "differs"),
    [(30, 30.0, False), (True, 1, True), (None, 0, True), ([1, 2], [1, 2], False)],
)
def test_values_compare_as_settings(resolved, legacy, differs):
    spec = OPTS[:1]
    key = spec[0].key
    assert differing_keys({key: resolved}, {key: legacy}, spec) == (
        (key,) if differs else ()
    )


def test_adopt_lifts_a_new_window_exactly():
    legacy = _house_legacy(lambda _key: DEFAULTS)
    _lifted, hub = _lift_house(legacy)
    office = legacy[HOUSE.key("Office north")]
    new = {**office, CONF_SUNSET_POS: 7, CONF_USE_LUX: False}

    # In the office: the room profile covers its schedule.
    in_office = Placement(area_id="office", floor_id="upstairs")
    overrides = adopt("new", new, hub, in_office)
    assert dict(overrides.values) == {CONF_SUNSET_POS: 7}
    assert dict(overrides.legacy) == {CONF_USE_LUX: False}
    assert compare("new", new, hub, overrides, in_office).differing == ()

    # Nowhere: the room's values have no level to live at but the window.
    overrides = adopt("new", new, hub, Placement())
    assert dict(overrides.values) == {CONF_DEFAULT_HEIGHT: 100, CONF_SUNSET_POS: 7}
    assert set(overrides.legacy) == {
        CONF_SUNRISE_OFFSET,
        "sunset_offset",
        "start_time",
        CONF_TEMP_ENTITY,
        CONF_USE_LUX,
    }
    assert compare("new", new, hub, overrides, Placement()).differing == ()


def test_provenance_summary_keeps_it_small():
    resolution = Resolution(
        values={},
        provenance={
            "set_azimuth": Source.WINDOW,  # one-time: always the window's
            CONF_SUNSET_POS: Source.WINDOW,  # a window override
            CONF_DEFAULT_HEIGHT: Source.AREA,
            CONF_TEMP_ENTITY: Source.FLOOR,
            CONF_SUNRISE_OFFSET: Source.LEGACY,
            "temp_low": Source.HOUSE,
            "quiet_start": Source.DEFAULT,
        },
    )
    assert provenance_summary(resolution) == {
        CONF_SUNSET_POS: "window",
        CONF_DEFAULT_HEIGHT: "area",
        CONF_TEMP_ENTITY: "floor",
        CONF_SUNRISE_OFFSET: "legacy",
    }
