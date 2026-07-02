"""Movement smoothing (quiet hours, move budget) and privacy integration."""

from __future__ import annotations

import datetime as dt

from freezegun import freeze_time
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

from .characterization.test_coordinator_gating import OPTIONS, make_coordinator
from .conftest import COMMON_OPTIONS

COVER = "cover.test_cover"


class TestQuietHours:
    def _coord(self, **kw):
        return make_coordinator(
            quiet_start="22:00:00", quiet_end="07:00:00", max_moves_hour=None, **kw
        )

    @freeze_time("2026-03-20 23:00:00")
    def test_tracking_move_blocked_inside_window(self):
        assert self._coord().check_quiet_hours(42, OPTIONS) is False

    @freeze_time("2026-03-20 06:30:00")
    def test_window_crossing_midnight_still_quiet(self):
        assert self._coord().check_quiet_hours(42, OPTIONS) is False

    @freeze_time("2026-03-20 12:00:00")
    def test_tracking_move_allowed_outside_window(self):
        assert self._coord().check_quiet_hours(42, OPTIONS) is True

    @freeze_time("2026-03-20 23:00:00")
    def test_snap_positions_pass_through(self):
        coord = self._coord()
        assert coord.check_quiet_hours(0, OPTIONS) is True
        assert coord.check_quiet_hours(100, OPTIONS) is True
        assert coord.check_quiet_hours(60, OPTIONS) is True  # default height

    def test_unconfigured_is_inert(self):
        coord = make_coordinator(
            quiet_start=None, quiet_end=None, max_moves_hour=None
        )
        assert coord.check_quiet_hours(42, OPTIONS) is True


class TestMoveBudget:
    def _coord(self, budget=2):
        return make_coordinator(
            quiet_start=None, quiet_end=None, max_moves_hour=budget
        )

    def test_budget_allows_until_exhausted(self):
        coord = self._coord(budget=2)
        assert coord.check_move_budget(COVER, 42, OPTIONS) is True
        coord._record_move(COVER)
        assert coord.check_move_budget(COVER, 43, OPTIONS) is True
        coord._record_move(COVER)
        assert coord.check_move_budget(COVER, 44, OPTIONS) is False

    def test_old_moves_age_out(self):
        coord = self._coord(budget=1)
        coord._move_history[COVER] = [
            dt.datetime.now(dt.UTC) - dt.timedelta(minutes=61)
        ]
        assert coord.check_move_budget(COVER, 42, OPTIONS) is True

    def test_snap_positions_bypass_budget(self):
        coord = self._coord(budget=1)
        coord._record_move(COVER)
        assert coord.check_move_budget(COVER, 0, OPTIONS) is True
        assert coord.check_move_budget(COVER, 100, OPTIONS) is True

    def test_per_entity_budgets(self):
        coord = self._coord(budget=1)
        coord._record_move(COVER)
        assert coord.check_move_budget("cover.other", 42, OPTIONS) is True

    def test_unconfigured_is_inert(self):
        coord = make_coordinator(
            quiet_start=None, quiet_end=None, max_moves_hour=None
        )
        assert coord.check_move_budget(COVER, 42, OPTIONS) is True


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
    assert coordinator.manager.is_cover_manual(COVER) is True


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
    assert coordinator.manager.is_cover_manual(COVER) is True


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

    assert coordinator.manager.is_cover_manual(COVER) is True
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
