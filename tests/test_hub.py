"""The All Shades hub: bootstrap, aggregate cover, house mode, reset-all."""

from __future__ import annotations

import datetime as dt

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.hub import HUB_UNIQUE_ID, is_hub_entry

from .conftest import COMMON_OPTIONS


def _regular_entry(hass, name, cover):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={"name": name, CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [cover],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_two_entries(hass):
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.a", "open", {"current_position": 80})
    hass.states.async_set("cover.b", "open", {"current_position": 20})
    e1 = _regular_entry(hass, "Room A", "cover.a")
    e2 = _regular_entry(hass, "Room B", "cover.b")
    await hass.config_entries.async_setup(e1.entry_id)
    await hass.async_block_till_done()  # bootstrap may set up the component
    if e2.state is not ConfigEntryState.LOADED:
        await hass.config_entries.async_setup(e2.entry_id)
    await hass.async_block_till_done()
    return e1, e2


async def test_hub_auto_bootstrapped_once(hass, mock_sun_entity):
    await _setup_two_entries(hass)
    hubs = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if is_hub_entry(entry)
    ]
    assert len(hubs) == 1
    assert hubs[0].title == "Adaptive Cover All"


async def test_aggregate_cover_average_position(hass, mock_sun_entity):
    await _setup_two_entries(hass)
    state = hass.states.get("cover.adaptive_cover_all")
    assert state is not None
    assert state.attributes["current_position"] == 50  # avg(80, 20)


async def test_aggregate_set_position_fans_out(hass, mock_sun_entity):
    from custom_components.adaptive_cover.hub import AllShadesCover

    await _setup_two_entries(hass)
    calls = async_mock_service(hass, "cover", "set_cover_position")

    aggregate = AllShadesCover(hass)
    await aggregate.async_set_cover_position(position=37)
    await hass.async_block_till_done()

    targeted = {call.data["entity_id"] for call in calls}
    assert targeted == {"cover.a", "cover.b"}
    assert all(call.data["position"] == 37 for call in calls)


async def test_house_mode_flips_all_entries(hass, mock_sun_entity):
    e1, e2 = await _setup_two_entries(hass)
    registry = er.async_get(hass)
    select_id = registry.async_get_entity_id(
        "select", DOMAIN, f"{HUB_UNIQUE_ID}_house_mode"
    )
    assert select_id
    from homeassistant.setup import async_setup_component

    await async_setup_component(hass, "homeassistant", {})
    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": select_id}, blocking=True
    )
    assert hass.states.get(select_id).state == "Adaptive"  # switches restore on

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": select_id, "option": "Manual"},
        blocking=True,
    )
    await hass.async_block_till_done()

    for entry in (e1, e2):
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.control_toggle is False
    assert hass.states.get(select_id).state == "Manual"


async def test_reset_all_button_clears_overrides(hass, mock_sun_entity):
    e1, e2 = await _setup_two_entries(hass)
    for entry, cover in ((e1, "cover.a"), (e2, "cover.b")):
        coordinator = hass.data[DOMAIN][entry.entry_id]
        coordinator.manager.mark_manual_control(cover)
        coordinator.manager.manual_control_time[cover] = dt.datetime.now(dt.UTC)

    registry = er.async_get(hass)
    button_id = registry.async_get_entity_id(
        "button", DOMAIN, f"{HUB_UNIQUE_ID}_reset_all"
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()

    for entry, cover in ((e1, "cover.a"), (e2, "cover.b")):
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.manager.is_cover_manual(cover) is False


async def test_hub_unloads_cleanly(hass, mock_sun_entity):
    await _setup_two_entries(hass)
    hub = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if is_hub_entry(entry)
    )
    assert await hass.config_entries.async_unload(hub.entry_id)


async def test_aggregate_cover_polls_and_recovers_from_boot_race(
    hass, mock_sun_entity
):
    """Regression: frozen 'unknown / 0 covers' state after hub loaded first.

    The aggregate must poll so its state converges even when it rendered
    before regular entries registered their coordinators.
    """
    from custom_components.adaptive_cover.hub import AllShadesCover

    await _setup_two_entries(hass)
    assert AllShadesCover(hass)._attr_should_poll is True

    from homeassistant.setup import async_setup_component

    await async_setup_component(hass, "homeassistant", {})
    # Underlying covers move; a poll/update must reflect it
    hass.states.async_set("cover.a", "open", {"current_position": 100})
    hass.states.async_set("cover.b", "open", {"current_position": 100})
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {"entity_id": "cover.adaptive_cover_all"},
        blocking=True,
    )
    state = hass.states.get("cover.adaptive_cover_all")
    assert state.attributes["current_position"] == 100
    assert state.attributes["covers"] == 2
