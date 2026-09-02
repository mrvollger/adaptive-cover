"""Behavior tests for the hub's aggregate cover / select / button entities.

wp10-hub-behavior: plain HA behavior tests driven only through public seams
(config entries, real state changes, real service calls, entity states).
No coordinator internals, no manager reads, no object.__new__.

Covered gaps: aggregate-set-marks-manual, reset-all-button,
house-mode-select, aggregate-cover.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
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
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.hub import HUB_UNIQUE_ID

from .conftest import COMMON_OPTIONS

AGGREGATE_COVER = "cover.adaptive_cover_all"


def _vertical_entry(hass, name, cover):
    """Create one vertical-blind entry driving a single cover."""
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


def _tilt_entry(hass, name, cover):
    """Create one venetian-tilt entry driving a single cover."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={"name": name, CONF_SENSOR_TYPE: SensorType.TILT},
        options={
            **COMMON_OPTIONS,
            CONF_TILT_DEPTH: 3,
            CONF_TILT_DISTANCE: 2,
            CONF_TILT_MODE: "mode2",
            CONF_ENTITIES: [cover],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_entries(hass, entries):
    """Set up config entries; the first setup may bootstrap the hub."""
    for entry in entries:
        if entry.state is not ConfigEntryState.LOADED:
            await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    await async_setup_component(hass, "homeassistant", {})


async def _setup_two_entries(hass):
    """Two vertical entries over fake cover states, hub bootstrapped."""
    hass.states.async_set("cover.a", "open", {"current_position": 80})
    hass.states.async_set("cover.b", "open", {"current_position": 20})
    e1 = _vertical_entry(hass, "Room A", "cover.a")
    e2 = _vertical_entry(hass, "Room B", "cover.b")
    await _setup_entries(hass, [e1, e2])
    return e1, e2


def _entry_eid(hass, domain, entry, suffix):
    """Resolve an entry's entity id from its unique-id suffix."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_{suffix}"
    )
    assert entity_id, f"no {domain} entity with unique-id suffix {suffix!r}"
    return entity_id


def _hub_eid(hass, domain, suffix):
    """Resolve a hub entity id from its unique-id suffix."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        domain, DOMAIN, f"{HUB_UNIQUE_ID}_{suffix}"
    )
    assert entity_id, f"no hub {domain} entity with suffix {suffix!r}"
    return entity_id


async def _poll(hass, entity_id):
    """Force a poll of a polling entity and return its fresh state."""
    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": entity_id}, blocking=True
    )
    return hass.states.get(entity_id)


def _manual_binary(hass, entry):
    """State of an entry's Manual Override binary sensor."""
    return hass.states.get(
        _entry_eid(hass, "binary_sensor", entry, "Manual Override")
    )


async def _latch_override_by_remote_move(hass, cover, position):
    """Latch a manual override through a real foreign cover state change."""
    hass.states.async_set(cover, "open", {"current_position": position})
    await hass.async_block_till_done()


async def test_aggregate_set_marks_manual(hass, mock_sun_entity):
    """A whole-house set marks every member manual; sun ticks don't revert it."""
    e1, e2 = await _setup_two_entries(hass)

    # Drive the aggregate through the REAL cover entity service.
    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": AGGREGATE_COVER, "position": 25},
        blocking=True,
    )
    await hass.async_block_till_done()

    # From here on capture what the integration commands. Elevation 50
    # computes ~28%, differing from both members' positions (80 and 20),
    # so absent the override BOTH would be commanded (see control case).
    calls = async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 50.0}
    )
    await hass.async_block_till_done()

    member_calls = [
        call
        for call in calls
        if call.data["entity_id"] in ("cover.a", "cover.b")
    ]
    assert member_calls == [], (
        "adaptive tick must not walk back a whole-house manual gesture"
    )
    for entry in (e1, e2):
        binary = _manual_binary(hass, entry)
        assert binary.state == "on"
        assert binary.attributes["manual_controlled"] == list(
            entry.options[CONF_ENTITIES]
        )


async def test_aggregate_set_marks_manual_control_case(hass, mock_sun_entity):
    """Control case: without the aggregate gesture the same sun tick commands.

    Proves the empty-calls assert above is not vacuous.
    """
    e1, e2 = await _setup_two_entries(hass)

    # The fixed startup refresh commanded both members at setup; land each
    # cover on its target so the travel windows clear and the elevation-50
    # tick below (~28%, differing from the landed positions) re-commands.
    for entry, cover in ((e1, "cover.a"), (e2, "cover.b")):
        coordinator = hass.data[DOMAIN][entry.entry_id]
        hass.states.async_set(
            cover, "open", {"current_position": coordinator.target_call[cover]}
        )
    await hass.async_block_till_done()

    calls = async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 50.0}
    )
    await hass.async_block_till_done()

    targeted = {call.data["entity_id"] for call in calls}
    assert targeted == {"cover.a", "cover.b"}


async def test_reset_all_button(hass, mock_sun_entity):
    """Reset-all re-applies adaptive positions after real remote-move latches."""
    e1, e2 = await _setup_two_entries(hass)

    await _latch_override_by_remote_move(hass, "cover.a", 55)
    await _latch_override_by_remote_move(hass, "cover.b", 70)
    assert _manual_binary(hass, e1).state == "on"
    assert _manual_binary(hass, e2).state == "on"

    calls = async_mock_service(hass, "cover", "set_cover_position")
    button_id = _hub_eid(hass, "button", "reset_all")
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()

    for entry, cover in ((e1, "cover.a"), (e2, "cover.b")):
        moved = [c for c in calls if c.data["entity_id"] == cover]
        assert moved, f"reset-all must re-apply the adaptive position to {cover}"
        sensor = hass.states.get(_entry_eid(hass, "sensor", entry, "Cover Position"))
        assert moved[-1].data["position"] == int(float(sensor.state))
        assert _manual_binary(hass, entry).state == "off"


async def test_house_mode_mixed_and_adaptive(hass, mock_sun_entity):
    """One control off shows Mixed; Adaptive skips the overridden cover."""
    e1, e2 = await _setup_two_entries(hass)

    # Latch a manual override on entry 2's cover via a real remote move.
    await _latch_override_by_remote_move(hass, "cover.b", 70)
    assert _manual_binary(hass, e2).state == "on"

    # Turn entry 1's Toggle Control off through the real switch service.
    switch_id = _entry_eid(hass, "switch", e1, "Toggle Control")
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(switch_id).state == "off"

    select_id = _hub_eid(hass, "select", "house_mode")
    assert (await _poll(hass, select_id)).state == "Mixed"

    calls = async_mock_service(hass, "cover", "set_cover_position")
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": select_id, "option": "Adaptive"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(switch_id).state == "on"
    assert (await _poll(hass, select_id)).state == "Adaptive"
    targeted = [call.data["entity_id"] for call in calls]
    assert "cover.a" in targeted, "resumed cover must be re-commanded"
    assert "cover.b" not in targeted, (
        "Adaptive must respect an existing manual override"
    )
    assert _manual_binary(hass, e2).state == "on"


async def test_aggregate_state_rules(hass, mock_sun_entity):
    """Closed only when all closed; average excludes tilt entries."""
    hass.states.async_set("cover.a", "closed", {"current_position": 0})
    hass.states.async_set("cover.b", "closed", {"current_position": 0})
    hass.states.async_set(
        "cover.t",
        "open",
        {"current_position": 100, "current_tilt_position": 100},
    )
    e1 = _vertical_entry(hass, "Room A", "cover.a")
    e2 = _vertical_entry(hass, "Room B", "cover.b")
    e3 = _tilt_entry(hass, "Room T", "cover.t")
    await _setup_entries(hass, [e1, e2, e3])

    state = await _poll(hass, AGGREGATE_COVER)
    assert state.state == "closed"
    assert state.attributes["current_position"] == 0
    assert state.attributes["covers"] == 2  # tilt entry excluded
    assert state.attributes["closed"] == 2
    assert state.attributes["partial"] == 0
    assert state.attributes["open"] == 0

    hass.states.async_set("cover.b", "open", {"current_position": 40})
    await hass.async_block_till_done()

    state = await _poll(hass, AGGREGATE_COVER)
    assert state.state == "open"
    # avg(0, 40) — a tilt cover reporting current_position=100 must not skew it
    assert state.attributes["current_position"] == 20
    assert state.attributes["covers"] == 2
    assert state.attributes["closed"] == 1
    assert state.attributes["partial"] == 1
    assert state.attributes["open"] == 0
