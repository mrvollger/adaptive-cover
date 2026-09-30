"""One Climate switch (house 3.2): climate_on, ignore_climate, migration 3.1 -> 3.2.

- Climate control runs for a window while the house's Climate switch
  (``climate_on``; a room can turn it off) is on, a temperature source
  resolves for it (an indoor temperature sensor from its window, room,
  floor or house, an outside temperature sensor or a weather entity) and it
  does not opt out with ``ignore_climate`` (a one-time window setting, in
  the window form's Advanced section). There is no ``climate_mode`` any
  more: no form, service or profile offers it.
- Migration 3.1 -> 3.2: a window whose ``climate_mode`` resolved to False
  (its own value, its room, the house, the default) gets
  ``ignore_climate: True``; ``climate_mode`` leaves every layer. On the
  live house every window had it on: nothing behavioral is written.

Observed through the Position sensor's ``decision_trace`` (a climate step
while climate control decides), the Control method sensor, the
diagnostics settings, the stored subentries and house options, the forms
and the services.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_IGNORE_CLIMATE,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)
from custom_components.adaptive_cover.settings.resolve import (
    Placement,
    WindowOverrides,
)
from custom_components.adaptive_cover.settings.window_record import WindowRecord
from custom_components.adaptive_cover.upgrade import (
    climate_mode_3_1,
    house_options_3_2,
    record_3_2,
)

from .conftest import COMMON_OPTIONS
from .consolidated_house import load_consolidated_house
from .house_model import Window, mock_house, window_subentry
from .window_form import (
    prefilled,
    record,
    shown,
    start_add,
    start_reconfigure,
    submit,
)
from .window_handle import WindowHandle, window_settings

pytestmark = pytest.mark.usefixtures("stub_sun_integration")

MILD = "sensor.indoor_temperature"  # between the thresholds: no season
OUTSIDE = "sensor.outside_temperature"
WEATHER = "weather.home"
# The first step of a decision climate control made (engine/evaluate.py);
# the sun logic's own steps never start like this.
CLIMATE_STEPS = (
    "no presence",
    "away",
    "summer",
    "winter",
    "not summer",
    "climate neutral",
    "tilt",
)


@pytest.fixture(autouse=True)
def cover_calls(hass):
    return async_mock_service(hass, "cover", "set_cover_position")


@pytest.fixture(autouse=True)
async def unload_all_entries(hass):
    """Unload the house (its polling aggregate cover) after each test."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _options(cover: str, **extra: Any) -> dict[str, Any]:
    return {
        **COMMON_OPTIONS,
        CONF_HEIGHT_WIN: 2.1,
        CONF_DISTANCE: 0.5,
        CONF_ENTITIES: [cover],
        CONF_TEMP_LOW: 20,
        CONF_TEMP_HIGH: 25,
        **extra,
    }


def _window(name: str, cover: str, **extra: Any) -> Window:
    return Window(name=name, options=_options(cover, **extra))


def _world(hass, *covers: str) -> None:
    hass.states.async_set(MILD, "22.0")
    hass.states.async_set(OUTSIDE, "22.0")
    hass.states.async_set(WEATHER, "sunny", {"temperature": 22.0})
    for cover in covers:
        hass.states.async_set(cover, "open", {"current_position": 60})


async def _start(hass, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _climate_decides(hass, key: str) -> bool:
    """Whether climate control made the window's current decision."""
    trace = WindowHandle.by_key(hass, key).attributes["decision_trace"]
    assert trace, key
    return trace[0].startswith(CLIMATE_STEPS)


def _house(hass) -> MockConfigEntry:
    (house,) = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("is_hub")
    ]
    return house


# ------------------------------------------------------------ the runtime rule


@pytest.mark.parametrize(
    ("extra", "toggles", "decides"),
    [
        ({CONF_TEMP_ENTITY: MILD}, {}, True),
        ({CONF_OUTSIDETEMP_ENTITY: OUTSIDE}, {}, True),
        ({CONF_WEATHER_ENTITY: WEATHER}, {}, True),
        ({}, {}, False),
        ({CONF_TEMP_ENTITY: MILD, CONF_IGNORE_CLIMATE: True}, {}, False),
        ({CONF_TEMP_ENTITY: MILD}, {"climate_on": False}, False),
    ],
    ids=[
        "indoor_sensor",
        "outside_sensor",
        "weather_entity",
        "no_temperature_source",
        "ignores_climate",
        "climate_switch_off",
    ],
)
async def test_climate_runs_with_the_switch_a_source_and_no_opt_out(
    hass, extra, toggles, decides
):
    """climate_on and not ignore_climate and a temperature source."""
    _world(hass, "cover.east")
    window = Window(
        name="East", options=_options("cover.east", **extra), toggles=toggles
    )
    await _start(hass, mock_house(hass, [window]))
    assert _climate_decides(hass, window.key) is decides
    settings = await window_settings(hass, window.key)
    assert "climate_mode" not in settings
    assert settings[CONF_IGNORE_CLIMATE] is bool(extra.get(CONF_IGNORE_CLIMATE))


async def test_the_house_climate_switch_turns_climate_off_and_on(hass):
    _world(hass, "cover.east")
    window = _window("East", "cover.east", **{CONF_TEMP_ENTITY: MILD})
    await _start(hass, mock_house(hass, [window]))
    switch = next(
        row.entity_id
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN
        and row.domain == "switch"
        and row.unique_id.endswith("climate_on")
    )
    assert _climate_decides(hass, window.key)
    for service, decides in (("turn_off", False), ("turn_on", True)):
        await hass.services.async_call(
            "switch", service, {"entity_id": switch}, blocking=True
        )
        await hass.async_block_till_done()
        assert _climate_decides(hass, window.key) is decides, service


async def test_ignore_climate_from_change_settings_and_reconfigure(hass):
    """The opt-out is a one-time window setting: stored in its geometry."""
    _world(hass, "cover.east")
    window = _window("East", "cover.east", **{CONF_TEMP_ENTITY: MILD})
    house = mock_house(hass, [window])
    await _start(hass, house)
    assert _climate_decides(hass, window.key)

    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": window.key, CONF_IGNORE_CLIMATE: True},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert record(window_subentry(house, window.key)).geometry[CONF_IGNORE_CLIMATE]
    assert not _climate_decides(hass, window.key)

    # Change window: the Advanced section shows it, pre-filled.
    result = await start_reconfigure(hass, house, window.subentry_id)
    assert CONF_IGNORE_CLIMATE in shown(result)["advanced"]
    values = prefilled(result)
    assert values[CONF_IGNORE_CLIMATE] is True
    result = await submit(hass, result, {**values, CONF_IGNORE_CLIMATE: False})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert not record(window_subentry(house, window.key)).geometry[CONF_IGNORE_CLIMATE]
    assert _climate_decides(hass, window.key)


# ------------------------------------------------ no surface offers climate_mode


async def test_the_window_form_has_ignore_climate_not_climate_mode(hass):
    result = await start_add(hass)
    fields = shown(result)
    assert all("climate_mode" not in section for section in fields.values())
    assert CONF_IGNORE_CLIMATE in fields["advanced"]
    assert CONF_TEMP_ENTITY in fields["exceptions_climate"]


async def test_the_house_form_has_the_climate_switch_not_climate_mode(hass):
    _world(hass, "cover.east")
    await _start(hass, mock_house(hass, [_window("East", "cover.east")]))
    result = await hass.config_entries.options.async_init(_house(hass).entry_id)
    fields = shown(result)
    assert all("climate_mode" not in section for section in fields.values())
    assert "climate_on" in fields["house_climate"]
    assert all(CONF_IGNORE_CLIMATE not in section for section in fields.values())


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("change_settings", {"climate_mode": True}),
        ("set_profile", {"scope": "house", "climate_mode": True}),
        ("set_profile", {"scope": "house", CONF_IGNORE_CLIMATE: True}),
        ("add_entry", {"name": "West", "cover": "cover.west", "climate_mode": True}),
    ],
    ids=["change_settings", "set_profile", "set_profile_one_time", "add_entry"],
)
async def test_the_services_no_longer_take_climate_mode(hass, service, data):
    _world(hass, "cover.east", "cover.west")
    window = _window("East", "cover.east")
    await _start(hass, mock_house(hass, [window]))
    if service == "change_settings":
        data = {"config_entry": window.key, **data}
    before = dict(_house(hass).options)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert dict(_house(hass).options) == before


async def test_get_profile_shows_no_climate_mode(hass):
    _world(hass, "cover.east")
    window = _window("East", "cover.east", **{CONF_TEMP_ENTITY: MILD})
    await _start(hass, mock_house(hass, [window]))
    house = await hass.services.async_call(
        DOMAIN, "get_profile", {"scope": "house"}, blocking=True, return_response=True
    )
    assert house["values"]["climate_on"] is True
    assert "climate_mode" not in house["values"]
    profile = await hass.services.async_call(
        DOMAIN,
        "get_profile",
        {"scope": "window", "id": window.key},
        blocking=True,
        return_response=True,
    )
    assert "climate_mode" not in profile["settings"]
    assert profile["settings"][CONF_IGNORE_CLIMATE] is False
    assert profile["provenance"][CONF_IGNORE_CLIMATE] == "window"


# ------------------------------------------------------------ migration 3.1 -> 3.2


def _as_3_1(
    hass,
    house: MockConfigEntry,
    *,
    house_climate_mode: bool | None,
    areas: dict[str, dict[str, Any]] | None = None,
    window_climate_mode: dict[str, bool] | None = None,
) -> None:
    """Store ``house`` as v2.1 did (3.1): climate_mode in its layers."""
    options = copy.deepcopy(dict(house.options))
    if house_climate_mode is not None:
        options["house"]["climate_mode"] = house_climate_mode
    options["areas"] = {**options.get("areas", {}), **(areas or {})}
    hass.config_entries.async_update_entry(house, options=options, minor_version=1)
    for key, climate_mode in (window_climate_mode or {}).items():
        subentry = window_subentry(house, key)
        data = copy.deepcopy(dict(subentry.data))
        data["overrides"]["legacy"]["climate_mode"] = climate_mode
        hass.config_entries.async_update_subentry(house, subentry, data=data)


def _place_cover(hass, cover: str, area_id: str) -> None:
    """Register the physical cover in a room (before its state exists)."""
    registry = er.async_get(hass)
    row = registry.async_get_or_create(
        "cover", "demo", cover, suggested_object_id=cover.split(".", 1)[1]
    )
    assert row.entity_id == cover
    registry.async_update_entity(cover, area_id=area_id)


async def test_migration_turns_climate_mode_off_into_ignore_climate(hass):
    """A window whose climate_mode resolved to False ignores climate control."""
    covers = ("cover.plain", "cover.opted", "cover.den", "cover.office")
    areas = ar.async_get(hass)
    den = areas.async_create("Den")
    office = areas.async_create("Office")
    _place_cover(hass, "cover.den", den.id)
    _place_cover(hass, "cover.office", office.id)
    _world(hass, *covers)
    windows = {
        cover: _window(cover.split(".")[1].title(), cover, **{CONF_TEMP_ENTITY: MILD})
        for cover in covers
    }
    house = mock_house(hass, list(windows.values()))
    _as_3_1(
        hass,
        house,
        house_climate_mode=True,
        areas={
            den.id: {"climate_mode": False, "default_percentage": 70},
            office.id: {"climate_mode": True},
        },
        window_climate_mode={windows["cover.opted"].key: False},
    )
    before = {
        cover: record(window_subentry(house, window.key))
        for cover, window in windows.items()
    }

    await _start(hass, house)

    assert (house.version, house.minor_version) == (3, 2)
    assert "climate_mode" not in house.options["house"]
    # A room keeps its other values; one left empty goes.
    assert house.options["areas"] == {den.id: {"default_percentage": 70}}
    opted_out = {"cover.opted", "cover.den"}
    for cover, window in windows.items():
        stored = record(window_subentry(house, window.key))
        expected = dict(before[cover].geometry)
        if cover in opted_out:
            expected[CONF_IGNORE_CLIMATE] = True
        assert dict(stored.geometry) == expected, cover
        assert "climate_mode" not in stored.overrides.legacy, cover
        assert _climate_decides(hass, window.key) is (cover not in opted_out), cover
        settings = await window_settings(hass, window.key)
        assert settings[CONF_IGNORE_CLIMATE] is (cover in opted_out), cover
        assert "climate_mode" not in settings
    assert (await window_settings(hass, windows["cover.den"].key))[
        "default_percentage"
    ] == 70


async def test_migration_of_a_house_without_climate_mode(hass):
    """climate_mode was off by default: every window ignores climate, unless its own."""
    _world(hass, "cover.east", "cover.west")
    east = _window("East", "cover.east", **{CONF_TEMP_ENTITY: MILD})
    west = _window("West", "cover.west", **{CONF_TEMP_ENTITY: MILD})
    house = mock_house(hass, [east, west])
    _as_3_1(hass, house, house_climate_mode=None, window_climate_mode={west.key: True})

    await _start(hass, house)

    assert (house.version, house.minor_version) == (3, 2)
    assert record(window_subentry(house, east.key)).geometry[CONF_IGNORE_CLIMATE]
    assert CONF_IGNORE_CLIMATE not in record(window_subentry(house, west.key)).geometry
    assert not _climate_decides(hass, east.key)
    assert _climate_decides(hass, west.key)


async def test_a_newer_house_is_not_migrated_again(hass):
    """A 3.2 house loads as is: an opt-out stays, nothing is rewritten."""
    _world(hass, "cover.east")
    east = _window(
        "East", "cover.east", **{CONF_TEMP_ENTITY: MILD, CONF_IGNORE_CLIMATE: True}
    )
    house = mock_house(hass, [east])
    stored = (dict(house.options), dict(window_subentry(house, east.key).data))
    await _start(hass, house)
    assert (house.version, house.minor_version) == (3, 2)
    assert (dict(house.options), dict(window_subentry(house, east.key).data)) == stored


async def test_the_live_house_takes_3_2_with_nothing_behavioral(hass):
    """Every live window had climate_mode on: none ignores climate control.

    From the live house as v2.0 consolidated it (2.1 -> 3.1 -> 3.2): no
    window stores ``ignore_climate``, climate_mode is gone from every
    layer, and climate control decides for all 15 windows (a cold day:
    Control method winter). The house replay pins each live window's
    positions through the same migrations (tests/replay).
    """
    for sensor in (
        "sensor.downstairs_indoor_temperature",
        "sensor.upstairs_indoor_temperature",
    ):
        hass.states.async_set(sensor, "50.0", {"unit_of_measurement": "°F"})
    house = load_consolidated_house(hass)

    await _start(hass, house)

    assert (house.version, house.minor_version) == (3, 2)
    for bucket in ("floors", "areas"):
        for profile in house.options[bucket].values():
            assert "climate_mode" not in profile
    assert "climate_mode" not in house.options["house"]
    assert len(house.subentries) == 15
    for subentry in house.subentries.values():
        stored = WindowRecord.from_data(subentry.data)
        assert CONF_IGNORE_CLIMATE not in stored.geometry, subentry.title
        key = subentry.data.get("window_key") or subentry.subentry_id
        handle = WindowHandle.by_key(hass, key)
        assert handle.state("control_method").state == "winter", subentry.title
        assert _climate_decides(hass, key), subentry.title


# ------------------------------------------------------------ the pure parts


_HUB = {
    "house": {"climate_mode": True, "sunset_position": 0},
    "floors": {"up": {"climate_mode": False, "temp_low": 18}},
    "areas": {
        "den": {"climate_mode": False},
        "office": {"default_percentage": 80},
    },
}


@pytest.mark.parametrize(
    ("overrides", "placement", "hub", "expected"),
    [
        (WindowOverrides(), Placement(), _HUB, True),
        (WindowOverrides(), Placement(area_id="den"), _HUB, False),
        (WindowOverrides(), Placement(area_id="office", floor_id="up"), _HUB, False),
        (WindowOverrides(legacy={"climate_mode": True}), Placement("den"), _HUB, True),
        (WindowOverrides(values={"climate_mode": False}), Placement(), _HUB, False),
        (WindowOverrides(legacy={"climate_mode": None}), Placement(), _HUB, False),
        (WindowOverrides(), Placement(), {"house": {}}, False),
        (WindowOverrides(), Placement(), {}, False),
    ],
    ids=[
        "house",
        "room",
        "floor",
        "own_beats_room",
        "own_value",
        "stored_none_was_off",
        "unset_default_off",
        "no_layers",
    ],
)
def test_climate_mode_3_1_follows_the_3_1_precedence(
    overrides, placement, hub, expected
):
    assert climate_mode_3_1(overrides, placement, hub) is expected


@pytest.mark.parametrize("climate_mode", [True, False])
def test_record_3_2(climate_mode):
    before = WindowRecord(
        name="East",
        cover="cover.east",
        cover_type="cover_blind",
        geometry={"set_azimuth": 90},
        overrides=WindowOverrides(
            values={"sunset_position": 5},
            legacy={"climate_mode": climate_mode, "lux_threshold": None},
        ),
        window_key="old-entry",
    )
    after = record_3_2(before, climate_mode)
    expected_geometry = {"set_azimuth": 90}
    if not climate_mode:
        expected_geometry[CONF_IGNORE_CLIMATE] = True
    assert dict(after.geometry) == expected_geometry
    assert dict(after.overrides.values) == {"sunset_position": 5}
    assert dict(after.overrides.legacy) == {"lux_threshold": None}
    assert (after.name, after.cover, after.cover_type, after.window_key) == (
        "East",
        "cover.east",
        "cover_blind",
        "old-entry",
    )


def test_house_options_3_2():
    options = {**copy.deepcopy(_HUB), "temperature_unit": "°F"}
    assert house_options_3_2(options) == {
        "house": {"sunset_position": 0},
        "floors": {"up": {"temp_low": 18}},
        "areas": {"office": {"default_percentage": 80}},
        "temperature_unit": "°F",
    }
    assert options == {**_HUB, "temperature_unit": "°F"}  # not changed in place
    assert house_options_3_2({}) == {}
