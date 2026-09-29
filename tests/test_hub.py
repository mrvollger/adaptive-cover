"""The All Shades hub: bootstrap, aggregate cover, house mode, reset-all."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity
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
from .window_handle import WindowHandle


def _regular_entry(hass, name, cover, delta_time=0):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={"name": name, CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [cover],
            CONF_DELTA_TIME: delta_time,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_two_entries(hass, delta_time_a=0):
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("cover.a", "open", {"current_position": 80})
    hass.states.async_set("cover.b", "open", {"current_position": 20})
    e1 = _regular_entry(hass, "Room A", "cover.a", delta_time=delta_time_a)
    e2 = _regular_entry(hass, "Room B", "cover.b")
    await hass.config_entries.async_setup(e1.entry_id)
    await hass.async_block_till_done()  # bootstrap may set up the component
    if e2.state is not ConfigEntryState.LOADED:
        await hass.config_entries.async_setup(e2.entry_id)
    await hass.async_block_till_done()
    # The aggregate cover polls. When the hub loads before Room B, its first
    # state misses B (a ~1% setup-order race); poll once so every test sees
    # both rooms.
    await async_update_entity(hass, "cover.adaptive_cover_all")
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
    from homeassistant.setup import async_setup_component

    await _setup_two_entries(hass)
    # The hub can render before entry B registers (a setup race that HA
    # 2026.8 hits often); it converges on its next poll, so force one.
    await async_setup_component(hass, "homeassistant", {})
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {"entity_id": "cover.adaptive_cover_all"},
        blocking=True,
    )
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
    assert hass.states.get(select_id).state == "auto"  # every window restores auto

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": select_id, "option": "off"},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Every window's Mode is off, and its Toggle Control alias reads off.
    for cover in ("cover.a", "cover.b"):
        assert WindowHandle(hass, cover).mode == "off"
        assert WindowHandle(hass, cover).state("control").state == "off"
    assert hass.states.get(select_id).state == "off"


def _manual_binary(hass, entry):
    """State of an entry's Manual Override binary sensor (entity surface)."""
    eid = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_Manual Override"
    )
    assert eid is not None
    return hass.states.get(eid)


async def test_reset_all_button_clears_overrides(hass, mock_sun_entity):
    """Reset-all clears overrides latched by REAL remote moves.

    Overrides are latched through foreign cover state changes and observed
    through the Manual Override binary sensors — no manager seeding/reads.
    """
    e1, e2 = await _setup_two_entries(hass)

    for cover, position in (("cover.a", 55), ("cover.b", 70)):
        hass.states.async_set(cover, "open", {"current_position": position})
        await hass.async_block_till_done()
    for entry in (e1, e2):
        assert _manual_binary(hass, entry).state == "on"

    registry = er.async_get(hass)
    button_id = registry.async_get_entity_id(
        "button", DOMAIN, f"{HUB_UNIQUE_ID}_reset_all"
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()

    for entry in (e1, e2):
        assert _manual_binary(hass, entry).state == "off"


async def test_hub_unloads_cleanly(hass, mock_sun_entity):
    await _setup_two_entries(hass)
    hub = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if is_hub_entry(entry)
    )
    assert await hass.config_entries.async_unload(hub.entry_id)


async def test_aggregate_cover_polls_and_recovers_from_boot_race(hass, mock_sun_entity):
    """Regression: frozen 'unknown / 0 covers' state after hub loaded first.

    The aggregate must poll so its state converges even when it rendered
    before regular entries registered their coordinators.
    """
    from custom_components.adaptive_cover.hub import AllShadesCover

    await _setup_two_entries(hass)
    assert AllShadesCover(hass).should_poll is True

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


async def test_reset_all_bypasses_time_throttle(hass, mock_sun_entity):
    """A human reset is a manual command: recovery is never throttled."""
    # Make any ordinary adaptive move impossible for the next hour: a
    # 60-minute time throttle, armed by the startup command at setup.
    await _setup_two_entries(hass, delta_time_a=60)
    window_a = WindowHandle(hass, "cover.a")

    # Cover was just manually moved (throttle window hot, override latched)
    hass.states.async_set("cover.a", "open", {"current_position": 40})
    await hass.async_block_till_done()
    assert window_a.is_manual

    calls = async_mock_service(hass, "cover", "set_cover_position")
    registry = er.async_get(hass)
    button_id = registry.async_get_entity_id(
        "button", DOMAIN, f"{HUB_UNIQUE_ID}_reset_all"
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert window_a.is_manual is False
    moved = [c for c in calls if c.data["entity_id"] == "cover.a"]
    assert moved, "reset-all must re-apply immediately despite the throttle"
    assert moved[-1].data["position"] == window_a.target
