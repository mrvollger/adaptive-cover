"""Characterization + regressions: the integration actually moving covers.

First tests anywhere that assert cover.set_cover_position is/isn't called,
plus regression tests for past bug-fix commits:

- 179536b: unavailable/unknown cover transitions must not latch manual override
- 1b2b668:  manual override must be visible in the same update cycle's data
- bbca2e9:  the predicted sun-entry position must index the tz-aware sun table
- 80f0fbf:  get_safe_attr replaces the removed HA state_attr helper

Everything is observed through the window's public surface (WindowHandle):
entity states, the call_service bus record, adaptive_cover_moved events.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pandas as pd
import pytest
from freezegun import freeze_time
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.calculation import AdaptiveVerticalCover
from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
)
from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.engine import geometry as engine_geometry
from custom_components.adaptive_cover.helpers import get_safe_attr

from ..conftest import COMMON_OPTIONS
from ..window_handle import WindowHandle, internal_coordinator
from .golden_lib import SLC, FakeSunData, patch_sun_data

COVER = "cover.test_cover"


@pytest.fixture
def cover_entry(hass):
    """Config entry driving one cover, with the time throttle disabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Test Vertical", CONF_SENSOR_TYPE: SensorType.BLIND},
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


@pytest.fixture
def cover_calls(hass):
    return async_mock_service(hass, "cover", "set_cover_position")


async def _setup(hass, entry) -> WindowHandle:
    """Set the entry up; the handle records from before the startup move."""
    window = WindowHandle(hass, COVER)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return window


async def _land_startup_move(hass, window):
    """Complete the startup positioning the fixed first refresh performs.

    Setup now commands the cover (source='startup') as soon as the control
    switch restores; land the cover on that target so the in-flight travel
    window clears before the behavior under test begins.
    """
    _set_cover(hass, window.last_command)
    await hass.async_block_till_done()


def _set_cover(hass, position, state="open"):
    hass.states.async_set(
        COVER, state, {"current_position": position} if position is not None else {}
    )


def _nudge_sun(hass, elevation=44.0):
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": elevation}
    )


async def test_fresh_setup_positions_covers(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    """A fresh setup positions the covers immediately (source='startup').

    The first refresh used to run before the control switch restored and
    consumed the one-shot flag with the toggle still None — covers then
    sat at their stale position until the next sun change. The fix defers
    the flag, so the switch's restore-refresh performs the startup move.
    (The command itself is measured from HA's call_service bus event
    because the hub bootstrap replaces any pre-setup service mock during
    setup.)
    """
    _set_cover(hass, 60)
    window = await _setup(hass, cover_entry)
    assert window.commands, "no startup command was issued"
    assert window.last_command == window.target
    assert window.moves[0]["source"] == "startup"


async def test_sun_change_triggers_position_call(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    _set_cover(hass, 60)
    window = await _setup(hass, cover_entry)
    await _land_startup_move(hass, window)
    cover_calls = async_mock_service(hass, "cover", "set_cover_position")

    _nudge_sun(hass)
    await hass.async_block_till_done()

    expected = window.target
    assert len(cover_calls) == 1
    assert cover_calls[0].data == {"entity_id": COVER, "position": expected}


async def test_regression_179536b_unavailable_transition_no_override(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    """Cover going unavailable and coming back must not latch manual override."""
    _set_cover(hass, 60)
    window = await _setup(hass, cover_entry)

    hass.states.async_set(COVER, "unavailable")
    await hass.async_block_till_done()
    # Comes back at a position far from the calculated state
    _set_cover(hass, 90)
    await hass.async_block_till_done()

    assert window.is_manual is False
    assert window.manual_override is False


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_regression_1b2b668_override_visible_same_cycle(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    """A manual move must latch override AND show in the same cycle's data."""
    _set_cover(hass, 60)
    window = await _setup(hass, cover_entry)
    await _land_startup_move(hass, window)
    cover_calls = async_mock_service(hass, "cover", "set_cover_position")

    # Integration moves the cover; simulate it reaching its target so the
    # wait-for-target latch clears.
    _nudge_sun(hass)
    await hass.async_block_till_done()
    target = cover_calls[0].data["position"]
    _set_cover(hass, target)
    await hass.async_block_till_done()

    # Now a human moves it somewhere else.
    _set_cover(hass, 90)
    await hass.async_block_till_done()

    assert window.is_manual is True
    assert window.manual_override is True
    last_change = window.state("last_change").attributes
    assert last_change["reason"] == "Manual override"
    assert last_change["new_position"] == 90


async def test_regression_foreign_landing_during_wait_latches_manual(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    """A definitive landing far from OUR target during the travel window is
    a human move: it must clear the wait and latch a manual override.

    (Previously this was swallowed as a motor echo and the next sun tick
    reverted the human's position — the reported override-loss symptom.)
    """
    _set_cover(hass, 60)
    window = await _setup(hass, cover_entry)
    await _land_startup_move(hass, window)
    cover_calls = async_mock_service(hass, "cover", "set_cover_position")

    _nudge_sun(hass)
    await hass.async_block_till_done()
    assert len(cover_calls) == 1

    # Cover reports a position that is neither old nor the target.
    _set_cover(hass, 90)
    await hass.async_block_till_done()

    assert window.is_manual is True
    # contract: internal (travel-window latch; no entity exposes an
    # in-flight command)
    coordinator = internal_coordinator(hass, cover_entry.entry_id)
    assert coordinator.wait_for_target[COVER] is False


# 2026-03-20 16:00 UTC == 10:00 MDT: after sunrise, hours before the sun
# swings round to a west-facing window.
@freeze_time("2026-03-20 16:00:00")
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_regression_bbca2e9_predicted_entry_position(hass, cover_calls):
    """The predicted 'Sun enters window' position comes from the right row.

    Regression bbca2e9: the prediction looked its target time up in the
    tz-aware sun table without converting it to the table's zone, missed,
    and fell back to the default position. Observed at the entity
    boundary: the Next State Change sensor's expected_position for the sun
    entering the window must be the calculated position at that table row
    (table-local time), not the default.
    """
    await hass.config.async_set_time_zone(SLC["tz"])
    sun_data = FakeSunData(
        SLC["lat"], SLC["lon"], SLC["tz"], pd.Timestamp("2026-03-20")
    )
    win_azi, fov = 250, 45
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Predict", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_AZIMUTH: win_azi,
            CONF_FOV_LEFT: fov,
            CONF_FOV_RIGHT: fov,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    _nudge_sun(hass, elevation=45.0)
    _set_cover(hass, 60)
    with patch_sun_data(sun_data):
        window = await _setup(hass, entry)
        # The expected value, computed the way production predicts it: the
        # first in-window table row, through the adapter's geometry.
        cover = AdaptiveVerticalCover(
            hass=SimpleNamespace(),
            logger=_predict_logger(),
            sol_azi=180.0,
            sol_elev=45.0,
            sunset_pos=0,
            sunset_off=0,
            sunrise_off=0,
            timezone=SLC["tz"],
            fov_left=fov,
            fov_right=fov,
            win_azi=win_azi,
            h_def=60,
            max_pos=None,
            min_pos=None,
            max_pos_bool=False,
            min_pos_bool=False,
            blind_spot_left=None,
            blind_spot_right=None,
            blind_spot_elevation=None,
            blind_spot_on=False,
            min_elevation=None,
            max_elevation=None,
            distance=0.5,
            h_win=2.1,
        )

    azi_min = (win_azi - fov + 360) % 360
    entry_rows = [
        i
        for i in range(len(sun_data.times))
        if (sun_data.solar_azimuth[i] - azi_min) % 360 <= (2 * fov) % 360
        and engine_geometry.valid_elevation(sun_data.solar_elevation[i], None, None)
    ]
    idx = entry_rows[0]
    expected = cover.calculate_percentage_at(
        sun_data.solar_azimuth[idx], sun_data.solar_elevation[idx]
    )

    state = window.state("next_change")
    assert state.attributes["event"] == "Sun enters window"
    assert (
        dt_util.parse_datetime(state.attributes["expected_time"])
        == sun_data.times[idx].to_pydatetime()
    )
    assert state.attributes["expected_position"] == expected
    # Mid-afternoon sun ~46 deg high enters a west window: the prediction
    # must be the calculated one, not the default.
    assert expected != 60


def _predict_logger() -> ConfigContextAdapter:
    logger = ConfigContextAdapter(logging.getLogger("predict"))
    logger.set_config_name("Predict")
    return logger


class TestGetSafeAttr:
    """Regression 80f0fbf: get_safe_attr replaces removed HA helper."""

    def test_returns_attribute(self, hass):
        hass.states.async_set("sun.sun", "above_horizon", {"azimuth": 123.0})
        assert get_safe_attr(hass, "sun.sun", "azimuth") == 123.0

    def test_missing_attribute_none(self, hass):
        hass.states.async_set("sun.sun", "above_horizon", {})
        assert get_safe_attr(hass, "sun.sun", "azimuth") is None

    def test_missing_entity_none(self, hass):
        assert get_safe_attr(hass, "sensor.nope", "azimuth") is None
