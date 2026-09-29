"""The layered settings resolver (settings/resolve.py, ADR 0003).

- Precedence: window -> area -> floor -> house -> spec default (legacy
  values, which only the lift writes, sit above them all).
- Provenance names the layer each value came from.
- A value stored at a level the spec does not allow is an error.
"""

from __future__ import annotations

import json

import pytest

from custom_components.adaptive_cover.settings.resolve import (
    AreaProfile,
    FloorProfile,
    HouseProfile,
    LevelNotAllowedError,
    Placement,
    Profiles,
    Source,
    UnknownOptionError,
    WindowOverrides,
    check_profiles,
    resolve,
    resolve_with_provenance,
)
from custom_components.adaptive_cover.settings.spec import OPTS

WIN = "window-1"
OFFICE = Placement(area_id="office", floor_id="upstairs")


def _profiles(
    house=None,
    floor=None,
    area=None,
    window=None,
    *,
    unit="°C",
    place=OFFICE,
    windows=None,
):
    return Profiles(
        house=HouseProfile(house or {}, temperature_unit=unit),
        floors={"upstairs": FloorProfile(floor or {})},
        areas={"office": AreaProfile(area or {})},
        windows=windows or {WIN: window or WindowOverrides()},
        placement={WIN: place},
    )


def _resolved(profiles, key):
    result = resolve_with_provenance(WIN, profiles)
    return result.values[key], result.provenance[key]


# ------------------------------------------------------------ precedence


@pytest.mark.parametrize(
    ("layers", "expected"),
    [
        ({}, (22, Source.DEFAULT)),
        ({"house": 70.0}, (70.0, Source.HOUSE)),
        ({"house": 70.0, "floor": 71.0}, (71.0, Source.FLOOR)),
        ({"house": 70.0, "floor": 71.0, "area": 72.0}, (72.0, Source.AREA)),
        ({"floor": 71.0, "area": 72.0}, (72.0, Source.AREA)),
        ({"house": 70.0, "area": 72.0}, (72.0, Source.AREA)),
        (
            {"house": 70.0, "floor": 71.0, "area": 72.0, "legacy": 73.0},
            (73.0, Source.LEGACY),
        ),
    ],
    ids=[
        "default",
        "house",
        "floor",
        "area",
        "area_no_house",
        "area_no_floor",
        "legacy",
    ],
)
def test_narrower_layer_wins_for_a_floor_and_area_option(layers, expected):
    # temp_low lives at the house; a floor or an area may override it.
    profiles = _profiles(
        house={"temp_low": layers["house"]} if "house" in layers else None,
        floor={"temp_low": layers["floor"]} if "floor" in layers else None,
        area={"temp_low": layers["area"]} if "area" in layers else None,
        window=WindowOverrides(legacy={"temp_low": layers["legacy"]})
        if "legacy" in layers
        else None,
    )
    assert _resolved(profiles, "temp_low") == expected


def test_area_beats_floor():
    profiles = _profiles(
        house={"temp_high": 75.0},
        floor={"temp_high": 76.0},
        area={"temp_high": 77.0},
    )
    assert _resolved(profiles, "temp_high") == (77.0, Source.AREA)


def test_floor_beats_house():
    profiles = _profiles(house={"temp_high": 75.0}, floor={"temp_high": 76.0})
    assert _resolved(profiles, "temp_high") == (76.0, Source.FLOOR)


@pytest.mark.parametrize(
    ("layers", "expected"),
    [
        ({"house": 1.0}, (1.0, Source.HOUSE)),
        ({"house": 1.0, "area": 1.4}, (1.4, Source.AREA)),
        ({"house": 1.0, "area": 1.4, "window": 1.7}, (1.7, Source.WINDOW)),
        ({"window": 1.7}, (1.7, Source.WINDOW)),
    ],
    ids=["house", "area", "window", "window_only"],
)
def test_window_override_wins_where_the_spec_allows_it(layers, expected):
    # eye_height lives at the house; an area or a window may override it.
    profiles = _profiles(
        house={"eye_height": layers["house"]} if "house" in layers else None,
        area={"eye_height": layers["area"]} if "area" in layers else None,
        window=WindowOverrides(values={"eye_height": layers["window"]})
        if "window" in layers
        else None,
    )
    assert _resolved(profiles, "eye_height") == expected


def test_one_time_setting_comes_from_the_window_setup():
    profiles = _profiles(window=WindowOverrides(setup={"set_azimuth": 145.0}))
    assert _resolved(profiles, "set_azimuth") == (145.0, Source.WINDOW)


def test_floor_homed_option_comes_from_the_floor():
    profiles = _profiles(floor={"temp_entity": "sensor.upstairs"})
    assert _resolved(profiles, "temp_entity") == ("sensor.upstairs", Source.FLOOR)
    profiles = _profiles(
        floor={"temp_entity": "sensor.upstairs"}, area={"temp_entity": "sensor.office"}
    )
    assert _resolved(profiles, "temp_entity") == ("sensor.office", Source.AREA)


def test_window_without_area_or_floor_reads_the_house():
    profiles = _profiles(
        house={"temp_low": 70.0},
        floor={"temp_low": 71.0},
        area={"temp_low": 72.0},
        place=Placement(),
    )
    assert _resolved(profiles, "temp_low") == (70.0, Source.HOUSE)


def test_area_or_floor_without_a_profile_inherits():
    profiles = _profiles(
        house={"temp_low": 70.0},
        place=Placement(area_id="guest_room", floor_id="attic"),
    )
    assert _resolved(profiles, "temp_low") == (70.0, Source.HOUSE)


def test_stored_none_is_a_value_not_a_gap():
    profiles = _profiles(
        house={"start_entity": "sensor.sunrise", "quiet_start": None},
        area={"start_entity": None},
    )
    assert _resolved(profiles, "start_entity") == (None, Source.AREA)
    assert _resolved(profiles, "quiet_start") == (None, Source.HOUSE)


# ------------------------------------------------------------ defaults


@pytest.mark.parametrize(
    ("unit", "low", "high"),
    [("°C", 22, 24), ("°F", 72, 75), (None, 22, 24)],
    ids=["celsius", "fahrenheit", "no_unit"],
)
def test_threshold_defaults_follow_the_house_temperature_unit(unit, low, high):
    profiles = _profiles(unit=unit)
    assert _resolved(profiles, "temp_low") == (low, Source.DEFAULT)
    assert _resolved(profiles, "temp_high") == (high, Source.DEFAULT)


def test_option_without_a_default_resolves_to_none():
    profiles = _profiles()
    assert _resolved(profiles, "quiet_start") == (None, Source.DEFAULT)
    assert _resolved(profiles, "temp_entity") == (None, Source.DEFAULT)


def test_resolve_returns_every_spec_option_in_spec_order():
    result = resolve(WIN, _profiles())
    assert list(result) == [opt.key for opt in OPTS]


def test_resolved_values_are_copies():
    profiles = _profiles(house={"weather_state": ["sunny"]})
    first = resolve(WIN, profiles)
    first["weather_state"].append("cloudy")
    assert resolve(WIN, profiles)["weather_state"] == ["sunny"]
    default = resolve(WIN, profiles)["interp_list"]
    default.append("50")
    assert resolve(WIN, profiles)["interp_list"] == []


def test_profiles_copy_their_input():
    values = {"weather_state": ["sunny"]}
    profiles = _profiles(house=values)
    values["weather_state"].append("cloudy")
    assert resolve(WIN, profiles)["weather_state"] == ["sunny"]


def test_provenance_is_plain_strings_for_the_position_attribute():
    profiles = _profiles(
        house={"temp_low": 70.0},
        floor={"temp_high": 76.0},
        area={"start_time": "07:30:00"},
        window=WindowOverrides(
            setup={"set_azimuth": 100.0},
            values={"eye_height": 1.5},
            legacy={"sunrise_offset": 15.0},
        ),
    )
    provenance = resolve_with_provenance(WIN, profiles).provenance
    assert {
        key: provenance[key]
        for key in (
            "temp_low",
            "temp_high",
            "start_time",
            "set_azimuth",
            "eye_height",
            "sunrise_offset",
            "delta_time",
        )
    } == {
        "temp_low": "house",
        "temp_high": "floor",
        "start_time": "area",
        "set_azimuth": "window",
        "eye_height": "window",
        "sunrise_offset": "legacy",
        "delta_time": "default",
    }
    assert set(provenance) == {opt.key for opt in OPTS}
    json.dumps(dict(provenance))  # an HA state attribute must serialize


# ------------------------------------------------------------ errors


@pytest.mark.parametrize(
    ("where", "key"),
    [
        ("house", "temp_entity"),  # home is the floor
        ("house", "set_azimuth"),  # one-time: window only
        ("house", "mode"),  # internal: never stored
        ("floor", "eye_height"),  # area and window only
        ("floor", "start_time"),  # area only
        ("area", "delta_position"),  # house only
        ("area", "fov_left"),  # one-time
        ("window_values", "temp_low"),  # floor and area only
        ("window_values", "set_azimuth"),  # one-time goes in setup
        ("window_setup", "eye_height"),  # recurring goes in values
        ("window_legacy", "eye_height"),  # a window may hold it: not legacy
        ("window_legacy", "set_azimuth"),
    ],
)
def test_value_at_a_level_the_spec_forbids_is_an_error(where, key):
    value = {key: 1.0}
    profiles = _profiles(
        house=value if where == "house" else None,
        floor=value if where == "floor" else None,
        area=value if where == "area" else None,
        window=WindowOverrides(
            values=value if where == "window_values" else {},
            setup=value if where == "window_setup" else {},
            legacy=value if where == "window_legacy" else {},
        ),
    )
    with pytest.raises(LevelNotAllowedError, match=key):
        resolve(WIN, profiles)
    with pytest.raises(LevelNotAllowedError, match=key):
        check_profiles(profiles)


@pytest.mark.parametrize(
    "where", ["house", "floor", "area", "setup", "values", "legacy"]
)
def test_unknown_option_is_an_error(where):
    value = {"not_an_option": 1}
    profiles = _profiles(
        house=value if where == "house" else None,
        floor=value if where == "floor" else None,
        area=value if where == "area" else None,
        window=WindowOverrides(**{where: value})
        if where in ("setup", "values", "legacy")
        else None,
    )
    with pytest.raises(UnknownOptionError, match="not_an_option"):
        resolve(WIN, profiles)


def test_unknown_window_is_a_key_error():
    with pytest.raises(KeyError, match="nope"):
        resolve("nope", _profiles())


def test_check_profiles_covers_layers_no_window_reads():
    profiles = Profiles(
        house=HouseProfile({"temp_low": 70.0}),
        floors={"attic": FloorProfile({"eye_height": 1.0})},
        windows={WIN: WindowOverrides()},
    )
    assert resolve(WIN, profiles)["temp_low"] == 70.0  # its chain is fine
    with pytest.raises(LevelNotAllowedError, match="attic"):
        check_profiles(profiles)
