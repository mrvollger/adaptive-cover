"""Move provenance: who moved each cover, when, and why."""

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
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_mock_service(hass, "cover", "set_cover_position")
    return hass.data[DOMAIN][entry.entry_id]


def _nudge_sun(hass, elevation=44.0):
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": elevation}
    )


async def test_adaptive_move_records_source_and_intent(
    hass, mock_sun_entity
):
    entry = _entry(hass)
    coordinator = await _setup(hass, entry)
    events = []
    hass.bus.async_listen(
        "adaptive_cover_moved", lambda e: events.append(e.data)
    )

    _nudge_sun(hass)
    await hass.async_block_till_done()

    log = coordinator.move_log[COVER]
    assert log[-1]["source"] == "adaptive"
    assert log[-1]["reason"] == "calculated"  # mock sun square in window
    assert events and events[-1]["entity_id"] == COVER


async def test_manual_takeover_recorded(hass, mock_sun_entity):
    entry = _entry(hass)
    coordinator = await _setup(hass, entry)

    _nudge_sun(hass)
    await hass.async_block_till_done()
    target = coordinator.target_call[COVER]
    hass.states.async_set(COVER, "open", {"current_position": target})
    await hass.async_block_till_done()

    hass.states.async_set(COVER, "open", {"current_position": 90})
    await hass.async_block_till_done()

    log = coordinator.move_log[COVER]
    assert log[-1]["source"] == "manual"
    assert log[-1]["position"] == 90


async def test_hub_gesture_recorded_as_all_covers(hass, mock_sun_entity):
    from custom_components.adaptive_cover.hub import AllShadesCover

    entry = _entry(hass)
    coordinator = await _setup(hass, entry)

    aggregate = AllShadesCover(hass)
    await aggregate.async_set_cover_position(position=25)
    await hass.async_block_till_done()

    log = coordinator.move_log[COVER]
    assert log[-1]["source"] == "all_covers"
    assert log[-1]["position"] == 25


async def test_last_moves_attribute(hass, mock_sun_entity):
    entry = _entry(hass)
    coordinator = await _setup(hass, entry)

    _nudge_sun(hass)
    await hass.async_block_till_done()

    last_moves = coordinator.data.attributes["last_moves"]
    assert COVER in last_moves
    assert "(adaptive: calculated)" in last_moves[COVER]


async def test_move_log_ring_buffer_capped(hass, mock_sun_entity):
    entry = _entry(hass)
    coordinator = await _setup(hass, entry)
    for i in range(25):
        coordinator.record_move_provenance(COVER, i, "adaptive", "test")
    assert len(coordinator.move_log[COVER]) == coordinator.MOVE_LOG_LIMIT
    assert coordinator.move_log[COVER][-1]["position"] == 24
