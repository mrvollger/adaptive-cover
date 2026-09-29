"""The legacy lift (settings/lift.py, ADR 0003 "Moving the live house").

- The house takes the most common value; a floor or area takes a value all
  its windows share; a window keeps a true outlier where the spec allows
  it; anything else stays as a legacy value. One-time options stay on the
  window.
- Legacy values come first: the lift departs from those rules only when
  that avoids a legacy value.
- Property tests: whatever the options, lift -> resolve gives them back
  exactly; options the allowed levels can express lift without legacy
  values; nothing is stored that the window would inherit anyway.
"""

from __future__ import annotations

import json
import random

import pytest

from custom_components.adaptive_cover.settings.lift import (
    LegacyWindow,
    Lifted,
    legacy_flat,
    lift,
    placements,
)
from custom_components.adaptive_cover.settings.resolve import (
    AreaProfile,
    FloorProfile,
    HouseProfile,
    Placement,
    Profiles,
    UnknownOptionError,
    WindowOverrides,
    allowed_levels,
    check_profiles,
    resolve,
    spec_default,
)
from custom_components.adaptive_cover.settings.spec import (
    OPTS,
    OPTS_BY_KEY,
    Kind,
    Level,
    Scope,
)

H, F, A, W = Level.HOUSE, Level.FLOOR, Level.AREA, Level.WINDOW

AREAS = {"office": "upstairs", "bedroom": "upstairs", "den": "ground", "closet": None}
FLOORS = ("upstairs", "ground")
ONE_TIME = [opt.key for opt in OPTS if opt.scope is Scope.ONE_TIME]


def _win(key, area, **options):
    return LegacyWindow(window_key=key, options=options, area_id=area)


def _lift(windows, **kwargs) -> tuple[Lifted, Profiles]:
    lifted = lift(windows, AREAS, FLOORS, **kwargs)
    return lifted, lifted.profiles(placements(windows, AREAS))


def _dump(value) -> str:
    """Type-exact comparison (30 vs 30.0 differ)."""
    return json.dumps(value, sort_keys=True)


def _assert_round_trip(windows, lifted_profiles, unit=None):
    for window in windows:
        flat = legacy_flat(window.options, temperature_unit=unit)
        assert resolve(window.window_key, lifted_profiles) == flat, window.window_key


def _only(lifted: Lifted, key: str):
    """Where one option ended up (everything but the house is sparse)."""
    return {
        "house": lifted.house.values.get(key, "-"),
        "floors": {
            f: p.values[key] for f, p in lifted.floors.items() if key in p.values
        },
        "areas": {a: p.values[key] for a, p in lifted.areas.items() if key in p.values},
        "windows": {
            w: o.values[key] for w, o in lifted.overrides.items() if key in o.values
        },
        "legacy": {
            w: o.legacy[key] for w, o in lifted.overrides.items() if key in o.legacy
        },
    }


# ------------------------------------------------------------ the rules


def test_house_takes_the_most_common_value_and_an_agreeing_area_its_own():
    windows = [
        _win("w1", "office", start_time="07:30:00"),
        _win("w2", "office", start_time="07:30:00"),
        _win("w3", "bedroom", start_time="00:00:00"),
        _win("w4", "den", start_time="00:00:00"),
        _win("w5", "den", start_time="00:00:00"),
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "start_time") == {
        "house": "00:00:00",
        "floors": {},
        "areas": {"office": "07:30:00"},
        "windows": {},
        "legacy": {},
    }
    _assert_round_trip(windows, profiles)


def test_area_value_needs_every_window_to_agree():
    windows = [
        _win("w1", "office", eye_height=1.0),
        _win("w2", "office", eye_height=1.0),
        _win("w3", "office", eye_height=1.2),
        _win("w4", "bedroom", eye_height=1.2),
        _win("w5", "den", eye_height=1.2),
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "eye_height") == {
        "house": 1.2,
        "floors": {},
        "areas": {},
        "windows": {"w1": 1.0, "w2": 1.0},
        "legacy": {},
    }
    _assert_round_trip(windows, profiles)


def test_floor_takes_a_value_all_its_windows_share():
    windows = [
        _win("w1", "office", temp_low=70.0),
        _win("w2", "bedroom", temp_low=70.0),
        _win("w3", "bedroom", temp_low=70.0),
        _win("w4", "den", temp_low=68.0),
        _win("w5", "den", temp_low=68.0),
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "temp_low") == {
        "house": 70.0,
        "floors": {"ground": 68.0},
        "areas": {},
        "windows": {},
        "legacy": {},
    }
    _assert_round_trip(windows, profiles)


def test_outlier_becomes_a_window_override():
    windows = [
        _win("w1", "office", default_percentage=100.0),
        _win("w2", "office", default_percentage=50.0),
        _win("w3", "bedroom", default_percentage=100.0),
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "default_percentage")["windows"] == {"w2": 50.0}
    assert resolve("w2", profiles)["default_percentage"] == 50.0
    _assert_round_trip(windows, profiles)


def test_outlier_no_allowed_level_can_hold_stays_as_legacy():
    windows = [
        _win("w1", "office", delta_position=1.0),
        _win("w2", "office", delta_position=5.0),
        _win("w3", "bedroom", delta_position=1.0),
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "delta_position") == {
        "house": 1.0,
        "floors": {},
        "areas": {},
        "windows": {},
        "legacy": {"w2": 5.0},
    }
    _assert_round_trip(windows, profiles)


def test_one_time_options_stay_on_every_window():
    # Every window faces 180 degrees, yet azimuth is never lifted.
    windows = [_win(f"w{i}", "office", set_azimuth=180.0) for i in range(3)]
    lifted, _ = _lift(windows)
    for overrides in lifted.overrides.values():
        assert list(overrides.setup) == ONE_TIME
        assert overrides.setup["set_azimuth"] == 180.0
    layered = [lifted.house, *lifted.floors.values(), *lifted.areas.values()]
    assert not {key for layer in layered for key in layer.values} & set(ONE_TIME)


def test_house_stores_every_house_level_option():
    lifted, _ = _lift([_win("w1", "office")])
    assert set(lifted.house.values) == {opt.key for opt in OPTS if opt.home is H}


def test_floor_homed_option_goes_to_each_floor():
    windows = [
        _win("w1", "office", temp_entity="sensor.up"),
        _win("w2", "bedroom", temp_entity="sensor.up"),
        _win("w3", "den", temp_entity="sensor.down"),
        _win("w4", "closet", temp_entity="sensor.closet"),  # area without floor
        _win("w5", None, temp_entity="sensor.nowhere"),  # no area at all
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "temp_entity") == {
        "house": "-",  # a floor option: the house cannot hold it
        "floors": {"upstairs": "sensor.up", "ground": "sensor.down"},
        "areas": {"closet": "sensor.closet"},
        "windows": {},
        "legacy": {"w5": "sensor.nowhere"},
    }
    _assert_round_trip(windows, profiles)


def test_internal_option_different_from_its_default_stays_as_legacy():
    windows = [_win("w1", "office", mode="basic"), _win("w2", "office", mode="x")]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "mode") == {
        "house": "-",
        "floors": {},
        "areas": {},
        "windows": {},
        "legacy": {"w2": "x"},
    }
    _assert_round_trip(windows, profiles)


# ------------------------------------------------------------ tie-breaks


def test_tie_goes_to_the_value_needing_fewer_overrides():
    # 97 and 99 twice each (default 100): 99 at the house leaves one area
    # value, 97 would leave two.
    windows = [
        _win("w1", "office", default_percentage=97.0),
        _win("w2", "office", default_percentage=97.0),
        _win("w3", "bedroom", default_percentage=99.0),
        _win("w4", "den", default_percentage=99.0),
    ]
    lifted, _ = _lift(windows)
    assert lifted.house.values["default_percentage"] == 99.0
    assert _only(lifted, "default_percentage")["areas"] == {"office": 97.0}


def test_tie_then_goes_to_the_spec_default():
    windows = [
        _win("w1", "office", default_percentage=97.0),
        _win("w2", "bedroom", default_percentage=100.0),
    ]
    lifted, _ = _lift(windows)
    assert lifted.house.values["default_percentage"] == 100.0


def test_tie_then_goes_to_the_first_window():
    windows = [
        _win("w2", "bedroom", default_percentage=99.0),
        _win("w1", "office", default_percentage=97.0),
    ]
    lifted, _ = _lift(windows)
    assert lifted.house.values["default_percentage"] == 97.0  # w1 sorts first


def test_house_departs_from_the_most_common_value_to_avoid_legacy():
    # 07:30 is the most common, but the window without an area can only
    # inherit the house, and only the house holds its 00:00.
    windows = [
        _win("w1", "office", start_time="07:30:00"),
        _win("w2", "office", start_time="07:30:00"),
        _win("w3", "office", start_time="07:30:00"),
        _win("w4", "bedroom", start_time="00:00:00"),
        _win("w5", None, start_time="00:00:00"),
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "start_time") == {
        "house": "00:00:00",
        "floors": {},
        "areas": {"office": "07:30:00"},
        "windows": {},
        "legacy": {},
    }
    _assert_round_trip(windows, profiles)


def test_area_departs_from_unanimity_to_avoid_legacy():
    # Office disagrees; its majority -20 as the area value leaves one legacy
    # value instead of two.
    windows = [
        _win("w1", "office", sunrise_offset=0.0),
        _win("w2", "office", sunrise_offset=-20.0),
        _win("w3", "office", sunrise_offset=-20.0),
        _win("w4", "bedroom", sunrise_offset=0.0),
        _win("w5", "bedroom", sunrise_offset=0.0),
        _win("w6", "den", sunrise_offset=0.0),
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "sunrise_offset") == {
        "house": 0.0,
        "floors": {},
        "areas": {"office": -20.0},
        "windows": {},
        "legacy": {"w1": 0.0},
    }
    _assert_round_trip(windows, profiles)


def test_equal_ints_and_floats_are_one_value():
    windows = [
        _win("w1", "office", privacy_offset=30),
        _win("w2", "office", privacy_offset=30.0),
        _win("w3", "office", privacy_offset=30.0),
    ]
    lifted, profiles = _lift(windows)
    assert _only(lifted, "privacy_offset")["house"] == 30.0  # most common form
    assert not any(o.values or o.legacy for o in lifted.overrides.values())
    _assert_round_trip(windows, profiles)


def test_bools_never_equal_numbers():
    windows = [
        _win("w1", "office", manual_threshold=1),
        _win("w2", "office", manual_threshold=True),
    ]
    lifted, profiles = _lift(windows)
    assert len(_only(lifted, "manual_threshold")["legacy"]) == 1
    _assert_round_trip(windows, profiles)


def test_lift_does_not_depend_on_entry_order():
    rng = random.Random(7)
    windows = _random_flat_windows(rng, _random_layout(rng))
    expected = lift(windows, AREAS_P, FLOORS_P)
    for _ in range(3):
        shuffled = list(windows)
        rng.shuffle(shuffled)
        assert lift(shuffled, AREAS_P, FLOORS_P) == expected


# ------------------------------------------------------------ inputs


def test_legacy_flat_fills_missing_keys_from_the_spec():
    flat = legacy_flat(
        {"name": "Office", "sensor_type": "cover_blind", "quiet_start": None},
        temperature_unit="°F",
    )
    assert list(flat) == [opt.key for opt in OPTS]  # identity keys dropped
    assert flat["quiet_start"] is None  # stored None kept
    assert flat["privacy_offset"] == 30  # missing -> spec default
    assert flat["temp_low"] == 72  # per-unit default
    assert flat["temp_entity"] is None  # no default


def test_legacy_flat_rejects_unknown_options():
    with pytest.raises(UnknownOptionError, match="bogus"):
        legacy_flat({"bogus": 1})
    with pytest.raises(UnknownOptionError, match="bogus"):
        lift([_win("w1", "office", bogus=1)], AREAS, FLOORS)


@pytest.mark.parametrize(
    ("windows", "areas", "match"),
    [
        ([_win("w1", "office"), _win("w1", "den")], AREAS, "duplicate"),
        ([_win("w1", "attic")], AREAS, "attic"),
        ([_win("w1", "office")], {"office": "roof"}, "roof"),
    ],
    ids=["duplicate_window", "unknown_area", "unknown_floor"],
)
def test_lift_rejects_bad_places(windows, areas, match):
    with pytest.raises(ValueError, match=match):
        lift(windows, areas, FLOORS)


# ------------------------------------------------------------ properties

AREAS_P = {"a1": "f1", "a2": "f1", "a3": "f2", "a4": None}
FLOORS_P = ("f1", "f2")
SEEDS = range(40)


def _pool(opt) -> list:
    """A few values per option, so windows often agree."""
    if opt.kind in (Kind.BOOL, Kind.SWITCH):
        return [True, False]
    if opt.kind is Kind.TIME:
        return [None, "00:00:00", "06:00:00", "07:30:00"]
    if opt.kind is Kind.DURATION:
        return [
            {"hours": 2, "minutes": 0, "seconds": 0},
            {"hours": 0, "minutes": 45, "seconds": 0},
        ]
    if opt.kind is Kind.ENTITY:
        if opt.multiple:
            return [["cover.a"], ["cover.b"]]
        return [None, "sensor.a", "sensor.b"]
    if opt.kind is Kind.SELECT:
        if opt.multiple:
            return [[], ["0", "100"], ["sunny", "clear"]]
        return list(opt.options)
    if opt.kind is Kind.INTERNAL:
        return [opt.default]
    # Not integral: no pool value equals an int spec default (0 vs 0.0 are
    # one setting, which the type-exact checks below would not accept).
    return [None, 0.5, 1.5, 20.25]


def _random_layout(rng) -> list[tuple[str, str | None]]:
    """(window_key, area_id) for 1-3 windows per area plus 0-2 without one."""
    layout = []
    for area in [*AREAS_P, None]:
        for _ in range(rng.randint(0 if area is None else 1, 2 if area is None else 3)):
            layout.append((f"w{len(layout):02d}", area))
    return layout


def _random_flat_windows(rng, layout) -> list[LegacyWindow]:
    """Arbitrary flat options: a common value per key with random outliers."""
    windows = []
    common = {opt.key: rng.choice(_pool(opt)) for opt in OPTS}
    area_values = {
        (opt.key, area): rng.choice(_pool(opt)) for opt in OPTS for area in AREAS_P
    }
    for key, area in layout:
        options = {}
        for opt in OPTS:
            roll = rng.random()
            if roll < 0.5:
                options[opt.key] = common[opt.key]
            elif roll < 0.8 and area is not None:
                options[opt.key] = area_values[(opt.key, area)]
            else:
                options[opt.key] = rng.choice(_pool(opt))
        windows.append(LegacyWindow(key, options, area))
    return windows


def _random_profiles(rng, layout) -> Profiles:
    """Profiles that only use levels the spec allows."""
    house, floors, areas = {}, {f: {} for f in FLOORS_P}, {a: {} for a in AREAS_P}
    setup = {key: {} for key, _ in layout}
    values = {key: {} for key, _ in layout}
    for opt in OPTS:
        pool, allowed = _pool(opt), allowed_levels(opt)
        if H in allowed and rng.random() < 0.8:
            house[opt.key] = rng.choice(pool)
        for level, units in ((F, floors), (A, areas)):
            for stored in units.values():
                if level in allowed and rng.random() < 0.35:
                    stored[opt.key] = rng.choice(pool)
        for key, _ in layout:
            if opt.home is W:
                setup[key][opt.key] = rng.choice(pool)
            elif W in allowed and rng.random() < 0.2:
                values[key][opt.key] = rng.choice(pool)
    return Profiles(
        house=HouseProfile(house),
        floors={f: FloorProfile(v) for f, v in floors.items()},
        areas={a: AreaProfile(v) for a, v in areas.items()},
        windows={
            key: WindowOverrides(setup=setup[key], values=values[key])
            for key, _ in layout
        },
        placement={
            key: Placement(area, AREAS_P.get(area) if area else None)
            for key, area in layout
        },
    )


def _reference(profiles: Profiles, window_key: str, *, skip_window=False) -> dict:
    """ADR 0003 precedence written out independently of resolve.py."""
    window = profiles.windows[window_key]
    place = profiles.placement[window_key]
    empty: dict = {}
    area = profiles.areas.get(place.area_id) if place.area_id else None
    floor = profiles.floors.get(place.floor_id) if place.floor_id else None
    layers = [
        empty if skip_window else window.legacy,
        empty if skip_window else window.values,
        empty if skip_window else window.setup,
        area.values if area else empty,
        floor.values if floor else empty,
        profiles.house.values,
    ]
    flat = {}
    for opt in OPTS:
        found = [layer[opt.key] for layer in layers if opt.key in layer]
        flat[opt.key] = found[0] if found else spec_default(opt)
    return flat


@pytest.mark.parametrize("seed", SEEDS)
def test_expressible_options_lift_exactly_without_legacy(seed):
    rng = random.Random(seed)
    layout = _random_layout(rng)
    original = _random_profiles(rng, layout)
    windows = [
        LegacyWindow(key, _reference(original, key), area) for key, area in layout
    ]
    lifted, profiles = _lift_p(windows)
    check_profiles(profiles)
    for window in windows:
        assert _dump(resolve(window.window_key, profiles)) == _dump(window.options)
    assert not [o.legacy for o in lifted.overrides.values() if o.legacy]


@pytest.mark.parametrize("seed", SEEDS)
def test_any_options_lift_exactly(seed):
    rng = random.Random(1000 + seed)
    windows = _random_flat_windows(rng, _random_layout(rng))
    lifted, profiles = _lift_p(windows)
    check_profiles(profiles)
    for window in windows:
        assert _dump(resolve(window.window_key, profiles)) == _dump(window.options)
    _assert_nothing_redundant(lifted, profiles)


def _lift_p(windows) -> tuple[Lifted, Profiles]:
    lifted = lift(windows, AREAS_P, FLOORS_P)
    return lifted, lifted.profiles(placements(windows, AREAS_P))


def _assert_nothing_redundant(lifted: Lifted, profiles: Profiles) -> None:
    """Every narrower value changes what some window gets."""
    for key, overrides in lifted.overrides.items():
        inherited = _reference(profiles, key, skip_window=True)
        for part in (overrides.values, overrides.legacy):
            for option, value in part.items():
                assert _dump(value) != _dump(inherited[option]), (key, option)
        for option in overrides.legacy:
            assert W not in allowed_levels(OPTS_BY_KEY[option])
    house = profiles.house.values
    for area_id, area in lifted.areas.items():
        floor = lifted.floors.get(AREAS_P[area_id] or "", FloorProfile())
        for option, value in area.values.items():
            above = floor.values.get(option, house.get(option))
            if OPTS_BY_KEY[option].home is not A:
                assert _dump(value) != _dump(above), (area_id, option)
    for floor_id, floor in lifted.floors.items():
        for option, value in floor.values.items():
            if OPTS_BY_KEY[option].home is not F:
                assert _dump(value) != _dump(house.get(option)), (floor_id, option)
