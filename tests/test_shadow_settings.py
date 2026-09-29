"""Config entry migration 1.3 -> 1.4: the P5 shadow release (shadow.py).

On the live house snapshot (tests/fixtures/house_snapshot/, 15 windows,
°F, three floors), migration 1.4 lifts every window into the hub's house,
floor and area profiles and each window's sparse ``overrides``, recording
the states of the switches P5 drops, and leaves the legacy keys alone.
Afterwards every window resolves to exactly what it acts on today: no
``settings_differ`` repair issue. The Position sensor's ``provenance``
attribute names where each non-house value comes from.

Also pinned here: the switch capture reads the restored state when the
switches are not up; the lift is idempotent; a window added after the
lift (a copy of another window) joins the layered settings; a hub created
at 1.4 is not lifted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import State
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import issue_registry as ir
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
    mock_restore_cache,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)
from custom_components.adaptive_cover.migration import options_1_3

from .test_entity_surface_v2 import COVER, _entry, _load_live_house, _set_world, _setup
from .window_handle import WindowHandle

SNAPSHOT = Path(__file__).parent / "fixtures" / "house_snapshot"
UP = "sensor.upstairs_indoor_temperature"
DOWN = "sensor.downstairs_indoor_temperature"
_INERT = {
    "outside_threshold": None,
    "lux_threshold": None,
    "irradiance_threshold": None,
}

# What migration 1.4 stores for the live house (the review artifact).
HOUSE = {
    "climate_mode": True,
    "eye_height": 1.2,
    "occupied_distance": 2.0,
    "default_percentage": 99,
    "sunset_position": 0,
    "sunset_offset": 20,
    "sunrise_offset": 0,
    "delta_position": 1,
    "delta_time": 2,
    "start_time": "00:00:00",
    "start_entity": None,
    "manual_override_duration": {"hours": 2, "minutes": 0, "seconds": 0},
    "manual_override_reset": False,
    "manual_threshold": None,
    "manual_ignore_intermediate": False,
    "end_time": "00:00:00",
    "end_entity": None,
    "return_sunset": False,
    # Migration 1.3 stored None (the runtime's fallback) for the 13 windows
    # without privacy; the two south windows keep 30 / 0 as legacy values.
    "privacy_offset": None,
    "privacy_position": None,
    "quiet_start": None,
    "quiet_end": None,
    "max_moves_hour": None,
    "temp_low": 72,
    "temp_high": 75,
    "outside_temp": None,
    "outside_threshold": 0,
    "presence_entity": None,
    "lux_entity": None,
    "lux_threshold": 1000,
    "irradiance_entity": None,
    "irradiance_threshold": 300,
    "weather_entity": "weather.forecast_home_2",
    "weather_state": ["sunny", "partlycloudy", "clear", "windy", "windy-variant"],
    # The dropped switches: every one at its default in the snapshot (no
    # window has a lux or irradiance sensor, so those switches do not
    # exist and their initial state is recorded).
    "climate_on": True,
    "use_outside_temp": False,
    "use_lux": True,
    "use_irradiance": True,
    "manual_detection": True,
}
FLOORS = {
    "ground": {"temp_entity": DOWN},
    "main": {"temp_entity": DOWN},
    "upstairs": {"temp_entity": UP},
}
AREAS = {
    "den": {"default_percentage": 97, "sunset_offset": -30, "start_time": "06:00:00"},
    "family_room": {"sunrise_offset": -20},
    "master_bedroom": {"sunrise_offset": -20},
    "office": {
        "default_percentage": 100,
        "sunset_offset": 0,
        "sunrise_offset": 45,
        "start_time": "07:30:00",
    },
    "sw_bedroom": {
        "default_percentage": 97,
        "sunset_offset": -30,
        "start_time": "06:00:00",
    },
}
# title -> (window overrides, legacy values)
WINDOWS = {
    "Master trap": ({}, {"sunset_offset": 15, "sunrise_offset": 0}),
    "Office north": ({}, {}),
    "Office east": ({}, {}),
    "Office door": ({}, {}),
    "Leanne's door": ({"sunset_position": 5}, _INERT),
    "Leanne's south": ({}, _INERT),
    "Den south": ({}, _INERT),
    "Den southwest": ({"sunset_position": 5}, _INERT),
    "Den west": ({"sunset_position": 5}, _INERT),
    "Master east": ({}, {}),
    "Family east": ({}, {}),
    "Master door": ({"default_percentage": 100, "sunset_position": 3}, {}),
    "Family door": ({"default_percentage": 100, "sunset_position": 3}, {}),
    "Master south": ({}, {"privacy_offset": 30, "privacy_position": 0}),
    "Family south": ({}, {"privacy_offset": 30, "privacy_position": 0}),
}


@pytest.fixture
def cover_calls(hass):
    """Record (and absorb) the commands the windows send."""
    return async_mock_service(hass, "cover", "set_cover_position")


def _switch_states() -> dict[str, str]:
    """The live switch states of the snapshot, by entity_id."""
    states = json.loads((SNAPSHOT / "entity_states.json").read_text())["states"]
    return {
        entity_id: state["state"]
        for entity_id, state in states.items()
        if entity_id.startswith("switch.")
    }


def _live_house(hass, *, switch_states: dict[str, str] | None = None) -> list[dict]:
    """The live house at config 1.1, with its floors, °F and restored switches."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entries, _rows, _areas = _load_live_house(hass)
    floors = json.loads((SNAPSHOT / "floors_areas.json").read_text())
    floor_reg = fr.async_get(hass)
    for floor in floors["floors"]:
        created = floor_reg.async_create(floor["name"], level=floor["level"])
        assert created.floor_id == floor["floor_id"]
    for area in floors["areas"]:
        ar.async_get(hass).async_update(area["area_id"], floor_id=area["floor_id"])
    mock_restore_cache(
        hass,
        [
            State(eid, state)
            for eid, state in (switch_states or _switch_states()).items()
        ],
    )
    return entries


async def _set_up_live_house(hass, **kwargs) -> tuple[dict[str, str], MockConfigEntry]:
    """Set the live house up; return (title -> entry_id, the hub entry)."""
    entries = _live_house(hass, **kwargs)
    windows = {e["title"]: e["entry_id"] for e in entries if e["role"] == "window"}
    await _setup(
        hass, hass.config_entries.async_get_entry(next(iter(windows.values())))
    )
    (hub,) = (e for e in entries if e["role"] == "hub")
    return windows, hass.config_entries.async_get_entry(hub["entry_id"])


def _differ_issues(hass) -> dict[str, dict[str, str]]:
    return {
        issue_id: dict(issue.translation_placeholders or {})
        for (domain, issue_id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == "settings_differ"
    }


def _overrides(hass, entry_id: str) -> tuple[dict, dict]:
    stored = hass.config_entries.async_get_entry(entry_id).options["overrides"]
    assert stored["window_key"] == entry_id
    return stored["values"], stored["legacy"]


# ------------------------------------------------------ the live house


async def test_live_house_lifts_into_house_floor_and_area_profiles(hass, cover_calls):
    windows, hub = await _set_up_live_house(hass)
    snapshot = {
        e["entry_id"]: e
        for e in json.loads((SNAPSHOT / "config_entries.json").read_text())["entries"]
    }

    assert hub.minor_version == 5
    assert hub.options["house"] == HOUSE
    assert hub.options["temperature_unit"] == "°F"
    assert hub.options["floors"] == FLOORS
    assert hub.options["areas"] == AREAS
    assert set(windows) == set(WINDOWS)
    for title, entry_id in windows.items():
        entry = hass.config_entries.async_get_entry(entry_id)
        assert entry.state is ConfigEntryState.LOADED, title
        assert entry.minor_version == 5, title
        assert _overrides(hass, entry_id) == WINDOWS[title], title
        # the legacy keys are untouched: only "overrides" is new
        legacy = {k: v for k, v in entry.options.items() if k != "overrides"}
        assert legacy == options_1_3(snapshot[entry_id]["options"]), title
    # every window resolves to what it acts on today
    assert _differ_issues(hass) == {}


async def test_live_house_switch_that_is_on_is_recorded(hass, cover_calls):
    switch_states = _switch_states()
    den_south = "switch.den_south_outside_temperature"
    assert switch_states[den_south] == "off"
    switch_states[den_south] = "on"
    windows, hub = await _set_up_live_house(hass, switch_states=switch_states)

    # The house keeps the common state; Den south's switch is its own
    # legacy value (the outside-temperature flag is house-only).
    assert hub.options["house"]["use_outside_temp"] is False
    values, legacy = _overrides(hass, windows["Den south"])
    assert values == {}
    assert legacy == {**_INERT, "use_outside_temp": True}
    assert hass.states.get(den_south).state == "on"
    assert _differ_issues(hass) == {}


@pytest.mark.parametrize(
    ("title", "provenance"),
    [
        (
            "Office north",
            {
                "default_percentage": "area",
                "sunset_offset": "area",
                "sunrise_offset": "area",
                "start_time": "area",
                "temp_entity": "floor",
            },
        ),
        (
            "Master trap",
            {
                "sunset_offset": "legacy",
                "sunrise_offset": "legacy",
                "temp_entity": "floor",
            },
        ),
        (
            "Master door",
            {
                "default_percentage": "window",
                "sunset_position": "window",
                "sunrise_offset": "area",
                "temp_entity": "floor",
            },
        ),
        (
            "Master south",
            {
                "sunrise_offset": "area",
                "privacy_offset": "legacy",
                "privacy_position": "legacy",
                "temp_entity": "floor",
            },
        ),
    ],
    ids=["office_north", "master_trap", "master_door", "master_south"],
)
async def test_position_sensor_provenance(hass, cover_calls, title, provenance):
    windows, _hub = await _set_up_live_house(hass)
    window = WindowHandle.by_key(hass, windows[title])
    assert window.attributes["provenance"] == provenance


async def test_lift_is_idempotent(hass, cover_calls):
    windows, hub = await _set_up_live_house(hass)
    hub_options = dict(hub.options)
    window_options = {
        entry_id: dict(hass.config_entries.async_get_entry(entry_id).options)
        for entry_id in windows.values()
    }

    hass.config_entries.async_update_entry(hub, minor_version=3)
    assert await hass.config_entries.async_reload(hub.entry_id)
    await hass.async_block_till_done()

    assert hub.minor_version == 5
    assert dict(hub.options) == hub_options
    for entry_id, options in window_options.items():
        assert dict(hass.config_entries.async_get_entry(entry_id).options) == options
    assert _differ_issues(hass) == {}


async def test_window_added_after_the_lift_joins_it(hass, cover_calls):
    windows, _hub = await _set_up_live_house(hass)
    hass.states.async_set("cover.office_west_shades", "open", {"current_position": 50})

    result = await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {
            "name": "Office west",
            "cover": "cover.office_west_shades",
            "copy_from": "Office north",
            "sunset_position": 7,
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    # The copied "overrides" belong to Office north; the new window (a
    # cover without an area) is lifted alone against the house instead.
    new_id = result["entry_id"]
    assert new_id != windows["Office north"]
    values, legacy = _overrides(hass, new_id)
    assert values == {"default_percentage": 100, "sunset_position": 7}
    assert legacy == {
        "sunset_offset": 0,
        "sunrise_offset": 45,
        "start_time": "07:30:00",
        "temp_entity": UP,
    }
    assert _differ_issues(hass) == {}


# ------------------------------------------------------ switch capture


def _hub(hass, *, minor_version: int, disabled: bool = False) -> MockConfigEntry:
    hub = MockConfigEntry(
        domain=DOMAIN,
        title="Adaptive Cover All",
        data={"is_hub": True, "name": "Adaptive Cover All"},
        version=1,
        minor_version=minor_version,
        disabled_by=ConfigEntryDisabler.USER if disabled else None,
    )
    hub.add_to_hass(hass)
    return hub


async def test_lift_reads_the_restored_switch_state(hass, cover_calls):
    """The switch is not up when the hub migrates: its restored state counts."""
    _set_world(hass)
    hub = _hub(hass, minor_version=3, disabled=True)
    window = _entry(
        hass,
        minor_version=3,
        **{
            CONF_CLIMATE_MODE: True,
            CONF_TEMP_ENTITY: "sensor.indoor",
            CONF_WEATHER_ENTITY: "weather.home",
        },
    )
    switch = er.async_get(hass).async_get_or_create(
        "switch",
        DOMAIN,
        f"{window.entry_id}_Outside Temperature",
        suggested_object_id="office_door_outside_temperature",
        config_entry=window,
    )
    mock_restore_cache(hass, [State(switch.entity_id, "on")])
    handle = WindowHandle(hass, COVER)
    await _setup(hass, window)
    assert hass.states.get(switch.entity_id).state == "on"

    # Only the restore cache knows the switch's state now.
    assert await hass.config_entries.async_unload(window.entry_id)
    assert hass.states.get(switch.entity_id).state == "unavailable"
    assert await hass.config_entries.async_set_disabled_by(hub.entry_id, None)
    await hass.async_block_till_done()

    assert hub.minor_version == 5
    assert hub.options["house"]["use_outside_temp"] is True
    # (the indoor sensor lives on a floor; this window has no area)
    assert _overrides(hass, window.entry_id) == (
        {},
        {CONF_TEMP_ENTITY: "sensor.indoor"},
    )

    # Back up: the switch restores on again, as recorded.
    await _setup(hass, window)
    assert _differ_issues(hass) == {}
    assert handle.attributes["provenance"] == {CONF_TEMP_ENTITY: "legacy"}


async def test_lift_does_not_reload_a_running_window(hass, cover_calls):
    _set_world(hass)
    hub = _hub(hass, minor_version=3, disabled=True)
    window = _entry(hass, minor_version=3)
    handle = WindowHandle(hass, COVER)
    await _setup(hass, window)
    assert handle.attributes["provenance"] is None

    assert await hass.config_entries.async_set_disabled_by(hub.entry_id, None)
    await hass.async_block_till_done()

    assert hub.minor_version == 5
    assert _overrides(hass, window.entry_id) == ({}, {})
    assert handle.teardowns == 0
    # The new provenance reached the Position sensor without a reload.
    assert handle.attributes["provenance"] == {}
    assert _differ_issues(hass) == {}


async def test_hub_created_at_1_4_is_not_lifted(hass, cover_calls):
    _set_world(hass)
    window = _entry(hass, minor_version=3)
    handle = WindowHandle(hass, COVER)
    await _setup(hass, window)

    (hub,) = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("is_hub")
    ]
    assert hub.minor_version == 5
    assert "house" not in hub.options
    assert "overrides" not in window.options
    assert handle.attributes["provenance"] is None
    assert _differ_issues(hass) == {}
