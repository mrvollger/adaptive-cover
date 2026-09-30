"""The lift on the live house (tests/fixtures/house_snapshot/, 15 windows).

- The P5 guarantee: every window resolves to exactly its legacy options.
- What the lift makes of the real house: the house profile, one indoor
  temperature sensor per floor, room schedules as area profiles, the few
  window exceptions, and the legacy values the owner still has to settle.
"""

from __future__ import annotations

import pytest

from custom_components.adaptive_cover.settings.lift import (
    legacy_flat,
    lift,
    placements,
)
from custom_components.adaptive_cover.settings.resolve import (
    Source,
    check_profiles,
    resolve,
    resolve_with_provenance,
)
from custom_components.adaptive_cover.settings.spec import OPTS, Scope

from .house import TEMPERATURE_UNIT, load_house

HOUSE = load_house()
TITLES = sorted(HOUSE.titles.values())


def _slug(title: str) -> str:
    keep = "".join(c if c.isalnum() else "_" for c in title.lower())
    return "_".join(part for part in keep.split("_") if part)


UP = "sensor.upstairs_indoor_temperature"
DOWN = "sensor.downstairs_indoor_temperature"


@pytest.fixture(scope="module")
def lifted():
    return lift(
        HOUSE.windows, HOUSE.areas, HOUSE.floors, temperature_unit=TEMPERATURE_UNIT
    )


@pytest.fixture(scope="module")
def profiles(lifted):
    return lifted.profiles(placements(HOUSE.windows, HOUSE.areas))


def _window(title):
    (window,) = [w for w in HOUSE.windows if w.window_key == HOUSE.key(title)]
    return window


def test_snapshot_has_the_15_live_windows():
    assert len(HOUSE.windows) == 15


@pytest.mark.parametrize("title", TITLES, ids=[_slug(t) for t in TITLES])
def test_every_live_window_resolves_to_its_legacy_options(profiles, title):
    window = _window(title)
    expected = legacy_flat(window.options, temperature_unit=TEMPERATURE_UNIT)
    assert resolve(window.window_key, profiles) == expected


def test_lifted_house_passes_the_spec_check(profiles):
    check_profiles(profiles)


def test_house_profile(lifted):
    assert dict(lifted.house.values) == {
        "climate_mode": True,
        "eye_height": 1.2,
        "occupied_distance": 2.0,
        "default_percentage": 99.0,
        "sunset_position": 0.0,
        "sunset_offset": 20.0,
        "sunrise_offset": 0.0,
        "delta_position": 1.0,
        "delta_time": 2.0,
        "start_time": "00:00:00",
        "start_entity": None,
        "manual_override_duration": {"hours": 2, "minutes": 0, "seconds": 0},
        "manual_override_reset": False,
        "manual_threshold": None,
        "manual_ignore_intermediate": False,
        "end_time": "00:00:00",
        "end_entity": None,
        "return_sunset": False,
        "privacy_offset": 30,
        "privacy_position": 0,
        "quiet_start": None,
        "quiet_end": None,
        "max_moves_hour": None,
        "temp_low": 72.0,
        "temp_high": 75.0,
        # added after the snapshot: no window stores it, so the spec default
        "temp_hysteresis": 0,
        "outside_temp": None,
        "outside_threshold": 0,
        "presence_entity": None,
        "lux_entity": None,
        "lux_threshold": 1000.0,
        "irradiance_entity": None,
        "irradiance_threshold": 300.0,
        "weather_entity": "weather.forecast_home_2",
        "weather_state": ["sunny", "partlycloudy", "clear", "windy", "windy-variant"],
    }
    assert lifted.house.temperature_unit == "°F"


def test_indoor_temperature_sensor_per_floor(lifted):
    assert {f: dict(p.values) for f, p in lifted.floors.items()} == {
        "ground": {"temp_entity": DOWN},
        "main": {"temp_entity": DOWN},
        "upstairs": {"temp_entity": UP},
    }


def test_room_schedules_are_area_profiles(lifted):
    assert {a: dict(p.values) for a, p in lifted.areas.items()} == {
        "office": {
            "default_percentage": 100.0,
            "sunset_offset": 0.0,
            "sunrise_offset": 45.0,
            "start_time": "07:30:00",
        },
        "sw_bedroom": {
            "default_percentage": 97.0,
            "sunset_offset": -30.0,
            "start_time": "06:00:00",
        },
        "den": {
            "default_percentage": 97.0,
            "sunset_offset": -30.0,
            "start_time": "06:00:00",
        },
        # East/south/door windows share the -20 sunrise offset; Master
        # trap's 0 is the one legacy value left in its room.
        "master_bedroom": {"sunrise_offset": -20.0},
        "family_room": {"sunrise_offset": -20.0},
    }


def test_window_exceptions(lifted):
    exceptions = {
        HOUSE.titles[key]: dict(o.values)
        for key, o in lifted.overrides.items()
        if o.values
    }
    assert exceptions == {
        "Leanne's door": {"sunset_position": 5.0},
        "Den southwest": {"sunset_position": 5.0},
        "Den west": {"sunset_position": 5.0},
        "Master door": {"default_percentage": 100.0, "sunset_position": 3.0},
        "Family door": {"default_percentage": 100.0, "sunset_position": 3.0},
    }


def test_legacy_values_left_for_the_owner(lifted):
    inert = {
        "outside_threshold": None,
        "lux_threshold": None,
        "irradiance_threshold": None,
    }
    legacy = {
        HOUSE.titles[key]: dict(o.legacy)
        for key, o in lifted.overrides.items()
        if o.legacy
    }
    assert legacy == {
        # Only an area may set the offsets, and Master trap's room disagrees.
        "Master trap": {"sunrise_offset": 0.0, "sunset_offset": 15.0},
        # Stored None (the check is off) where the rest of the house has a
        # threshold; only the house may set these. No window has a lux,
        # irradiance or outside-temperature entity, so they change nothing.
        "Leanne's door": inert,
        "Leanne's south": inert,
        "Den south": inert,
        "Den southwest": inert,
        "Den west": inert,
    }


def test_one_time_options_stay_on_each_window(lifted):
    one_time = [opt.key for opt in OPTS if opt.scope is Scope.ONE_TIME]
    for window in HOUSE.windows:
        flat = legacy_flat(window.options, temperature_unit=TEMPERATURE_UNIT)
        setup = lifted.overrides[window.window_key].setup
        assert dict(setup) == {key: flat[key] for key in one_time}


@pytest.mark.parametrize(
    ("title", "key", "source"),
    [
        ("Office north", "start_time", Source.AREA),
        ("Office north", "temp_entity", Source.FLOOR),
        ("Office north", "temp_low", Source.HOUSE),
        ("Office north", "set_azimuth", Source.WINDOW),
        ("Office north", "mode", Source.DEFAULT),
        ("Master door", "default_percentage", Source.WINDOW),
        ("Master east", "default_percentage", Source.HOUSE),
        ("Master trap", "sunrise_offset", Source.LEGACY),
        ("Master east", "sunrise_offset", Source.AREA),
        ("Den south", "lux_threshold", Source.LEGACY),
        ("Family south", "lux_threshold", Source.HOUSE),
        ("Family south", "temp_entity", Source.FLOOR),
    ],
)
def test_provenance_on_live_windows(profiles, title, key, source):
    result = resolve_with_provenance(HOUSE.key(title), profiles)
    assert result.provenance[key] is source
