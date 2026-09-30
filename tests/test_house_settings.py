"""The house's settings on the hub device (P5 flip).

The hub ("Adaptive Cover All") carries the house-level settings as
entities: the Climate switch (primary), the detection and use-flag
switches and the threshold, override duration, eye height, seat distance
and privacy delay numbers (CONFIG). Each shows and sets the house's value
in the layered settings; every window acts on a change at once, without a
reload. The seven window numbers are gone (their old rows are removed at
the window's setup).

Observed through entity states, the registries, the hub's config entry and
the diagnostics settings.
"""

from __future__ import annotations

import pytest
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_CLIMATE_ON,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.entity_surface import HUB_UNIQUE_ID

from .conftest import COMMON_OPTIONS
from .window_handle import WindowHandle, window_settings

COVERS = ("cover.office", "cover.den")
SWITCHES = (
    "climate_on",
    "manual_detection",
    "use_outside_temp",
    "use_lux",
    "use_irradiance",
)
NUMBERS = (
    "temp_low",
    "temp_high",
    "manual_override_duration",
    "eye_height",
    "occupied_distance",
    "privacy_offset",
)


def _entry(hass, cover: str, **extra) -> MockConfigEntry:
    name = cover.split(".")[1].title()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={"name": name, CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [cover],
            CONF_CLIMATE_MODE: True,
            CONF_TEMP_ENTITY: "sensor.indoor",
            **extra,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _house(hass, **extra) -> list[MockConfigEntry]:
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("sensor.indoor", "22.0")
    entries = []
    for cover in COVERS:
        hass.states.async_set(cover, "open", {"current_position": 60})
        entry = _entry(hass, cover, **extra)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries.append(entry)
    await hass.async_block_till_done()
    return entries


def _hub_eid(hass, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{HUB_UNIQUE_ID}_{key}"
    )
    assert entity_id, (platform, key)
    return entity_id


def _hub(hass) -> MockConfigEntry:
    (hub,) = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("is_hub")
    ]
    return hub


async def test_house_settings_are_hub_entities(hass, mock_sun_entity):
    entries = await _house(hass, **{CONF_TEMP_LOW: 21, CONF_TEMP_HIGH: 25})
    registry = er.async_get(hass)
    hub_device = registry.async_get(_hub_eid(hass, "select", "house_mode")).device_id
    for platform, keys in (("switch", SWITCHES), ("number", NUMBERS)):
        for key in keys:
            row = registry.async_get(_hub_eid(hass, platform, key))
            assert row.device_id == hub_device, key
            expected = None if key == CONF_CLIMATE_ON else EntityCategory.CONFIG
            assert row.entity_category == expected, key
            assert row.disabled_by is None and row.hidden_by is None, key
    # The windows have no number entities any more.
    for entry in entries:
        rows = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert not [row for row in rows if row.domain == "number"], entry.title


async def test_house_numbers_show_the_house_values(hass, mock_sun_entity):
    await _house(hass, **{CONF_TEMP_LOW: 21, CONF_TEMP_HIGH: 25})
    shown = {
        key: hass.states.get(_hub_eid(hass, "number", key)).state for key in NUMBERS
    }
    assert shown == {
        "temp_low": "21",
        "temp_high": "25",
        "manual_override_duration": "15.0",  # COMMON_OPTIONS: 15 minutes
        "eye_height": "unknown",  # no house value, no default shown
        "occupied_distance": "unknown",
        "privacy_offset": "30",  # the spec default, shown while unset
    }
    assert hass.states.get(_hub_eid(hass, "switch", "climate_on")).state == "on"
    assert hass.states.get(_hub_eid(hass, "switch", "use_outside_temp")).state == "off"


@pytest.mark.parametrize(
    ("units", "low", "high", "unit", "low_range", "high_range"),
    [
        (METRIC_SYSTEM, 21, 25, "°C", (5, 30), (10, 40)),
        (US_CUSTOMARY_SYSTEM, 72, 75, "°F", (40, 90), (50, 100)),
    ],
    ids=["celsius", "fahrenheit"],
)
async def test_regression_threshold_numbers_follow_unit_system(
    hass, mock_sun_entity, units, low, high, unit, low_range, high_range
):
    """The house threshold numbers show HA's temperature unit and fit its range.

    (Pinned since v1.15.1 on the window numbers, whose job the house
    numbers took over in the P5 flip.) A value inside the unit's range is
    stored as given: the entity never converts the stored value.
    """
    hass.config.units = units
    entries = await _house(hass, **{CONF_TEMP_LOW: low, CONF_TEMP_HIGH: high})
    shown = {}
    for key in (CONF_TEMP_LOW, CONF_TEMP_HIGH):
        state = hass.states.get(_hub_eid(hass, "number", key))
        shown[key] = (
            state.state,
            state.attributes["unit_of_measurement"],
            (state.attributes["min"], state.attributes["max"]),
            state.attributes["step"],
        )
    assert shown == {
        CONF_TEMP_LOW: (str(low), unit, low_range, 0.5),
        CONF_TEMP_HIGH: (str(high), unit, high_range, 0.5),
    }

    new_low = low - 1.5
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _hub_eid(hass, "number", CONF_TEMP_LOW), "value": new_low},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert _hub(hass).options["house"][CONF_TEMP_LOW] == new_low
    for entry in entries:
        assert (await window_settings(hass, entry.entry_id))[CONF_TEMP_LOW] == new_low


async def test_a_house_setting_reaches_every_window_without_a_reload(
    hass, mock_sun_entity
):
    entries = await _house(hass)
    handles = [WindowHandle.by_key(hass, entry.entry_id) for entry in entries]
    before = [handle.teardowns for handle in handles]

    await hass.services.async_call(
        "number",
        "set_value",
        {
            "entity_id": _hub_eid(hass, "number", CONF_MANUAL_OVERRIDE_DURATION),
            "value": 90,
        },
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": _hub_eid(hass, "switch", CONF_CLIMATE_ON)},
        blocking=True,
    )
    await hass.async_block_till_done()

    house = _hub(hass).options["house"]
    assert house[CONF_MANUAL_OVERRIDE_DURATION] == {
        "hours": 1,
        "minutes": 30,
        "seconds": 0,
    }
    assert house[CONF_CLIMATE_ON] is False
    for entry, handle, teardowns in zip(entries, handles, before, strict=True):
        settings = await window_settings(hass, entry.entry_id)
        assert (
            settings[CONF_MANUAL_OVERRIDE_DURATION]
            == house[CONF_MANUAL_OVERRIDE_DURATION]
        )
        assert settings[CONF_CLIMATE_ON] is False
        assert handle.teardowns == teardowns, entry.title
        # The window's hidden Climate mode alias follows what it acts on.
        assert handle.state("climate_mode").state == "off"
    assert hass.states.get(_hub_eid(hass, "switch", CONF_CLIMATE_ON)).state == "off"
    assert (
        hass.states.get(_hub_eid(hass, "number", CONF_MANUAL_OVERRIDE_DURATION)).state
        == "90.0"
    )


async def test_a_window_with_its_own_value_keeps_it(hass, mock_sun_entity):
    office, den = await _house(hass)
    # The office's hidden Climate mode alias: the office's own value.
    await WindowHandle.by_key(hass, office.entry_id).turn("climate_mode", False)
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": _hub_eid(hass, "switch", CONF_CLIMATE_ON)},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert (await window_settings(hass, office.entry_id))[CONF_CLIMATE_ON] is False
    assert (await window_settings(hass, den.entry_id))[CONF_CLIMATE_ON] is True


async def test_house_times_reach_every_window_without_a_reload(hass, mock_sun_entity):
    """The end time and the quiet hours are hub time entities (CONFIG)."""
    entries = await _house(hass)
    registry = er.async_get(hass)
    handles = [WindowHandle.by_key(hass, entry.entry_id) for entry in entries]
    before = [handle.teardowns for handle in handles]
    for key in ("end_time", "quiet_start", "quiet_end"):
        row = registry.async_get(_hub_eid(hass, "time", key))
        assert row.entity_category == EntityCategory.CONFIG, key
    # No quiet hours yet: unknown.
    assert hass.states.get(_hub_eid(hass, "time", "quiet_start")).state == "unknown"

    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": _hub_eid(hass, "time", "quiet_start"), "time": "22:30:00"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert _hub(hass).options["house"]["quiet_start"] == "22:30:00"
    assert hass.states.get(_hub_eid(hass, "time", "quiet_start")).state == "22:30:00"
    for entry, handle, teardowns in zip(entries, handles, before, strict=True):
        assert (await window_settings(hass, entry.entry_id))[
            "quiet_start"
        ] == "22:30:00"
        assert handle.teardowns == teardowns, entry.title
