"""Move provenance: who moved each cover, when, and why.

Provenance is observed where users see it: the ``adaptive_cover_moved``
bus event (logbook) and the Position sensor's ``last_moves`` attribute.
"""

from __future__ import annotations

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

from .conftest import COMMON_OPTIONS
from .window_handle import WindowHandle, internal_coordinator

COVER = "cover.test_cover"


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Prov Test",
        data={"name": "Prov Test", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry):
    window = WindowHandle(hass, COVER)  # records from before the startup move
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_mock_service(hass, "cover", "set_cover_position")
    return window


def _nudge_sun(hass, elevation=44.0):
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": elevation}
    )


async def test_adaptive_move_records_source_and_intent(
    hass, mock_sun_entity
):
    entry = _entry(hass)
    window = await _setup(hass, entry)
    # The fixed first refresh positions the cover right at setup: make
    # that startup move explicit, then land the cover on its target so
    # the travel window clears and the adaptive nudge below commands.
    assert window.moves[0]["source"] == "startup"
    hass.states.async_set(
        COVER, "open", {"current_position": window.last_command}
    )
    await hass.async_block_till_done()
    events = []
    hass.bus.async_listen(
        "adaptive_cover_moved", lambda e: events.append(e.data)
    )

    _nudge_sun(hass)
    await hass.async_block_till_done()

    log = window.moves
    assert log[-1]["source"] == "adaptive"
    assert log[-1]["reason"] == "calculated"  # mock sun square in window
    assert events and events[-1]["entity_id"] == COVER


async def test_manual_takeover_recorded(hass, mock_sun_entity):
    entry = _entry(hass)
    window = await _setup(hass, entry)

    _nudge_sun(hass)
    await hass.async_block_till_done()
    target = window.last_command
    hass.states.async_set(COVER, "open", {"current_position": target})
    await hass.async_block_till_done()

    hass.states.async_set(COVER, "open", {"current_position": 90})
    await hass.async_block_till_done()

    log = window.moves
    assert log[-1]["source"] == "manual"
    assert log[-1]["position"] == 90


async def test_hub_gesture_recorded_as_all_covers(hass, mock_sun_entity):
    from custom_components.adaptive_cover.hub import AllShadesCover

    entry = _entry(hass)
    window = await _setup(hass, entry)

    aggregate = AllShadesCover(hass)
    await aggregate.async_set_cover_position(position=25)
    await hass.async_block_till_done()

    log = window.moves
    assert log[-1]["source"] == "all_covers"
    assert log[-1]["position"] == 25


async def test_last_moves_attribute(hass, mock_sun_entity):
    entry = _entry(hass)
    window = await _setup(hass, entry)
    # Land the startup move (fixed first refresh) so its travel window
    # clears and the nudge below produces the adaptive move under test.
    hass.states.async_set(
        COVER, "open", {"current_position": window.last_command}
    )
    await hass.async_block_till_done()

    _nudge_sun(hass)
    await hass.async_block_till_done()

    last_moves = window.attributes["last_moves"]
    assert COVER in last_moves
    assert "(adaptive: calculated)" in last_moves[COVER]


async def test_move_log_ring_buffer_capped(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    # contract: internal (the move-log ring buffer's bound is memory
    # hygiene no entity exposes; only its newest line is on last_moves)
    coordinator = internal_coordinator(hass, entry.entry_id)
    for i in range(25):
        coordinator.record_move_provenance(COVER, i, "adaptive", "test")
    assert len(coordinator.move_log[COVER]) == coordinator.MOVE_LOG_LIMIT
    assert coordinator.move_log[COVER][-1]["position"] == 24
