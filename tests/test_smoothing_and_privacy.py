"""Privacy integration and manual-override/travel-window entity behavior.

Quiet-hours and move-budget gating are pinned at behavior level by the
simulation days in tests/simulation/test_gates_and_windows.py
(test_quiet_hours_midnight_span_snap_bypass, test_move_budget).
"""

from __future__ import annotations

import datetime as dt

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
    CONF_PRIVACY_MODE,
    CONF_PRIVACY_OFFSET,
    CONF_PRIVACY_POSITION,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)

from .conftest import COMMON_OPTIONS

COVER = "cover.test_cover"


def _manual_override_sensor(hass, entry):
    """The entry's Manual Override binary sensor state (entity surface)."""
    eid = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_Manual Override"
    )
    assert eid is not None
    return hass.states.get(eid)


async def test_privacy_closes_after_dusk(hass, mock_sun_data, mock_sun_entity):
    """End-to-end: privacy mode drives the cover to the privacy position."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Privacy Test", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
            CONF_PRIVACY_MODE: True,
            CONF_PRIVACY_OFFSET: 30,
            CONF_PRIVACY_POSITION: 7,
        },
    )
    entry.add_to_hass(hass)
    calls = async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})

    # Sunset was 40 minutes ago, sunrise long past: privacy window active.
    now = dt.datetime.now(dt.UTC)
    mock_sun_data.sunset.return_value = now - dt.timedelta(minutes=40)
    mock_sun_data.sunrise.return_value = now - dt.timedelta(hours=12)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    calls = async_mock_service(hass, "cover", "set_cover_position")

    hass.states.async_set(
        "sun.sun", "below_horizon", {"azimuth": 300.0, "elevation": -8.0}
    )
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.states["state"] == 7
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": COVER, "position": 7}


async def test_privacy_offset_zero_engages_at_sunset(
    hass, mock_sun_data, mock_sun_entity
):
    """privacy_offset=0 means 'close right at sunset', not the 30-min default.

    Ten minutes after sunset the privacy position must already be commanded;
    an `offset or 30` coercion would still be waiting.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Privacy Zero", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
            CONF_PRIVACY_MODE: True,
            CONF_PRIVACY_OFFSET: 0,
            CONF_PRIVACY_POSITION: 7,
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set(COVER, "open", {"current_position": 60})

    now = dt.datetime.now(dt.UTC)
    mock_sun_data.sunset.return_value = now - dt.timedelta(minutes=10)
    mock_sun_data.sunrise.return_value = now - dt.timedelta(hours=12)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    calls = async_mock_service(hass, "cover", "set_cover_position")

    hass.states.async_set(
        "sun.sun", "below_horizon", {"azimuth": 300.0, "elevation": -8.0}
    )
    await hass.async_block_till_done()

    # Privacy (7), not the sunset position (0) the basic path would pick.
    assert calls
    assert calls[-1].data == {"entity_id": COVER, "position": 7}


async def test_sunrise_offset_falls_back_to_sunset_offset(
    hass, mock_sun_data, mock_sun_entity
):
    """Legacy entries without a sunrise offset inherit the sunset offset.

    Sunset offset -60, sunrise 30 min ahead: with the inherited -60 the
    before-sunrise window already released, so the sun is tracked; a
    fallback of 0 would still be holding the sunset position.
    """
    from custom_components.adaptive_cover.const import CONF_SUNSET_OFFSET

    options = {
        **COMMON_OPTIONS,
        CONF_HEIGHT_WIN: 2.1,
        CONF_DISTANCE: 0.5,
        CONF_ENTITIES: [COVER],
        CONF_DELTA_TIME: 0,
        CONF_SUNSET_OFFSET: -60,
    }
    from custom_components.adaptive_cover.const import CONF_SUNRISE_OFFSET

    options.pop(CONF_SUNRISE_OFFSET)  # key absent: the fallback must engage
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Sunrise Fallback", CONF_SENSOR_TYPE: SensorType.BLIND},
        options=options,
    )
    entry.add_to_hass(hass)
    hass.states.async_set(COVER, "open", {"current_position": 60})

    now = dt.datetime.now(dt.UTC)
    mock_sun_data.sunrise.return_value = now + dt.timedelta(minutes=30)
    mock_sun_data.sunset.return_value = now + dt.timedelta(hours=8)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    calls = async_mock_service(hass, "cover", "set_cover_position")

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()

    # Tracked position (23 for this geometry), not the sunset snap (0).
    assert calls
    assert calls[-1].data == {"entity_id": COVER, "position": 23}


async def test_privacy_beats_winter_open(hass, mock_sun_data, mock_sun_entity):
    """The aquarium fix: climate winter logic must not reopen after dusk."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Privacy Climate", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            "climate_mode": True,
            "temp_entity": "sensor.indoor",
            "temp_low": 21,
            "temp_high": 25,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
            CONF_PRIVACY_MODE: True,
            CONF_PRIVACY_OFFSET: 30,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    hass.states.async_set("sensor.indoor", "17.0")  # cold: winter mode

    now = dt.datetime.now(dt.UTC)
    mock_sun_data.sunset.return_value = now - dt.timedelta(minutes=40)
    mock_sun_data.sunrise.return_value = now - dt.timedelta(hours=12)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set(
        "sun.sun", "below_horizon", {"azimuth": 300.0, "elevation": -8.0}
    )
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.states["state"] == 0  # privacy, not winter-100


async def test_regression_target_latch_tolerance(
    hass, mock_sun_data, mock_sun_entity
):
    """Cover lands NEAR the target (99 vs 100): latch must clear so the
    next human move is detected as manual. Production bug 2026-07-02."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Latch Test", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()
    target = coordinator.target_call[COVER]

    # Motor lands 2 off the target: within tolerance -> latch clears
    hass.states.async_set(COVER, "open", {"current_position": target - 2})
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is False

    # Now a human move MUST latch the override
    hass.states.async_set(COVER, "open", {"current_position": 5})
    await hass.async_block_till_done()
    assert _manual_override_sensor(hass, entry).state == "on"


async def test_regression_target_latch_expiry(
    hass, mock_sun_data, mock_sun_entity
):
    """Cover never approaches the target: after TARGET_TIMEOUT the latch
    expires and human moves are manual again (not swallowed forever)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Latch Expiry", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is True

    # Simulate the command having been sent long ago
    coordinator.target_call_time[COVER] = dt.datetime.now(dt.UTC) - dt.timedelta(
        minutes=10
    )
    # Human parks it far from target: expiry clears latch, move is manual
    hass.states.async_set(COVER, "open", {"current_position": 5})
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is False
    assert _manual_override_sensor(hass, entry).state == "on"


async def test_user_context_move_latches_even_mid_window(
    hass, mock_sun_data, mock_sun_entity
):
    """A change carrying a user_id is human: manual latches instantly,
    even inside a fresh travel window. Production bug 2026-07-02 (2)."""
    from homeassistant.core import Context

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "UserCtx", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is True  # window armed

    hass.states.async_set(
        COVER,
        "open",
        {"current_position": 5},
        context=Context(user_id="0123456789abcdef0123456789abcdef"),
    )
    await hass.async_block_till_done()

    assert _manual_override_sensor(hass, entry).state == "on"
    assert coordinator.wait_for_target[COVER] is False


async def test_no_recommand_while_awaiting_target(
    hass, mock_sun_data, mock_sun_entity
):
    """While a command is in flight, adaptive ticks must not re-send:
    only the latest command matters, no stacking."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "NoStack", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    calls = async_mock_service(hass, "cover", "set_cover_position")
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()
    assert len(calls) == 1  # first command in flight

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 43.0}
    )
    await hass.async_block_till_done()
    # flush the sensor-refresh debouncer so the gate actually evaluates
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        async_fire_time_changed,
    )

    async_fire_time_changed(hass, dt_util.utcnow() + dt.timedelta(seconds=15))
    await hass.async_block_till_done()

    assert len(calls) == 1  # no stacking
    assert (
        coordinator.data.attributes["move_blocked_by"].get(COVER)
        == "awaiting_target"
    )


async def test_poll_forced_when_landing_report_missing(
    hass, mock_sun_data, mock_sun_entity
):
    """Zigbee dropped the landing report: we force a device poll after
    the travel timeout instead of staying stale forever."""
    from pytest_homeassistant_custom_component.common import (
        async_fire_time_changed,
    )
    from homeassistant.util import dt as dt_util

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "PollTest", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    update_calls = async_mock_service(hass, "homeassistant", "update_entity")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is True

    # No landing report ever arrives; jump past TARGET_TIMEOUT + margin
    async_fire_time_changed(hass, dt_util.utcnow() + dt.timedelta(seconds=130))
    await hass.async_block_till_done()

    assert any(c.data["entity_id"] == COVER for c in update_calls)


async def test_no_poll_when_cover_arrived(hass, mock_sun_data, mock_sun_entity):
    """Landing report arrived: no needless device poll."""
    from pytest_homeassistant_custom_component.common import (
        async_fire_time_changed,
    )
    from homeassistant.util import dt as dt_util

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "PollTest2", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    update_calls = async_mock_service(hass, "homeassistant", "update_entity")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()
    target = coordinator.target_call[COVER]
    hass.states.async_set(COVER, "open", {"current_position": target})
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is False

    async_fire_time_changed(hass, dt_util.utcnow() + dt.timedelta(seconds=130))
    await hass.async_block_till_done()

    assert not any(c.data["entity_id"] == COVER for c in update_calls)


async def test_regression_manual_latch_on_movement_start(
    hass, mock_sun_data, mock_sun_entity
):
    """Foreign opening/closing latches manual the moment travel starts.

    Regression 2026-07-03: these shades report position only at journey
    end, so latching on the landing report left a 1-3 minute window where
    a person's move read as auto-controlled mid-travel.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "StartLatch", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is True
    target = coordinator.target_call[COVER]

    # Cover lands on our target: window clears, cover is auto-controlled.
    hass.states.async_set(COVER, "open", {"current_position": target})
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is False
    assert _manual_override_sensor(hass, entry).state == "off"

    # Human starts moving it: state flips to "closing" but position still
    # reads the old value (no landing report yet, no user context - e.g. a
    # paired remote). Manual must latch NOW, not minutes later.
    hass.states.async_set(COVER, "closing", {"current_position": target})
    await hass.async_block_till_done()
    assert _manual_override_sensor(hass, entry).state == "on"


async def test_regression_no_latch_when_movement_is_ours(
    hass, mock_sun_data, mock_sun_entity
):
    """Movement while our own command is in flight must NOT latch manual."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "OwnMove", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
    )
    await hass.async_block_till_done()
    assert coordinator.wait_for_target[COVER] is True  # our command in flight

    # Device reports travel toward OUR target: not a human act.
    hass.states.async_set(COVER, "closing", {"current_position": 60})
    await hass.async_block_till_done()
    assert _manual_override_sensor(hass, entry).state == "off"


async def test_regression_resume_button_rename_keeps_unique_id(
    hass, mock_sun_data, mock_sun_entity
):
    """The reset button reads "Return to Auto" but its unique_id keeps
    the historical "Reset Manual Override" slug (renaming the unique_id
    would orphan every existing registry entry). Regression 2026-07-03."""
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Rename", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    button_entity = registry.async_get_entity_id(
        "button", DOMAIN, f"{entry.entry_id}_Reset Manual Override"
    )
    assert button_entity is not None
    state = hass.states.get(button_entity)
    assert "Return to Auto" in state.attributes["friendly_name"]
