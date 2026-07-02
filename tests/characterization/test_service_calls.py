"""Characterization + regressions: the integration actually moving covers.

First tests anywhere that assert cover.set_cover_position is/isn't called,
plus regression tests for past bug-fix commits:

- 179536b: unavailable/unknown cover transitions must not latch manual override
- 1b2b668:  manual override must be visible in the same update cycle's data
- bbca2e9:  _predict_position_at_time must index sun tables across timezones
- 80f0fbf:  get_safe_attr replaces the removed HA state_attr helper
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.calculation import AdaptiveVerticalCover
from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
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
from custom_components.adaptive_cover.helpers import get_safe_attr

from ..conftest import COMMON_OPTIONS
from .golden_lib import SLC, FakeSunData

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


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _set_cover(hass, position, state="open"):
    hass.states.async_set(
        COVER, state, {"current_position": position} if position is not None else {}
    )


def _nudge_sun(hass, elevation=44.0):
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": elevation}
    )


async def test_fresh_setup_makes_no_cover_call(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    """QUIRK: first refresh runs before the control switch restores, so a
    fresh setup never positions the covers until the first event."""
    _set_cover(hass, 60)
    await _setup(hass, cover_entry)
    assert cover_calls == []


async def test_sun_change_triggers_position_call(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    _set_cover(hass, 60)
    await _setup(hass, cover_entry)
    cover_calls = async_mock_service(hass, "cover", "set_cover_position")

    _nudge_sun(hass)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][cover_entry.entry_id]
    expected = coordinator.data.states["state"]
    assert len(cover_calls) == 1
    assert cover_calls[0].data == {"entity_id": COVER, "position": expected}


async def test_regression_179536b_unavailable_transition_no_override(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    """Cover going unavailable and coming back must not latch manual override."""
    _set_cover(hass, 60)
    await _setup(hass, cover_entry)
    coordinator = hass.data[DOMAIN][cover_entry.entry_id]

    hass.states.async_set(COVER, "unavailable")
    await hass.async_block_till_done()
    # Comes back at a position far from the calculated state
    _set_cover(hass, 90)
    await hass.async_block_till_done()

    assert coordinator.manager.is_cover_manual(COVER) is False
    assert coordinator.data.states["manual_override"] is False


async def test_regression_1b2b668_override_visible_same_cycle(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    """A manual move must latch override AND show in the same cycle's data."""
    _set_cover(hass, 60)
    await _setup(hass, cover_entry)
    cover_calls = async_mock_service(hass, "cover", "set_cover_position")
    coordinator = hass.data[DOMAIN][cover_entry.entry_id]

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

    assert coordinator.manager.is_cover_manual(COVER) is True
    assert coordinator.data.states["manual_override"] is True
    assert coordinator.data.states["last_change_reason"] == "Manual override"
    assert coordinator.data.states["last_change_new"] == 90


async def test_manual_change_ignored_while_waiting_for_target(
    hass, cover_entry, mock_sun_entity, cover_calls
):
    """QUIRK: while the integration waits for its own move to finish, any
    other position change is swallowed and never marks manual override."""
    _set_cover(hass, 60)
    await _setup(hass, cover_entry)
    cover_calls = async_mock_service(hass, "cover", "set_cover_position")
    coordinator = hass.data[DOMAIN][cover_entry.entry_id]

    _nudge_sun(hass)
    await hass.async_block_till_done()
    assert len(cover_calls) == 1

    # Cover "moves" to a position that is neither old nor the target.
    _set_cover(hass, 90)
    await hass.async_block_till_done()

    assert coordinator.manager.is_cover_manual(COVER) is False
    assert coordinator.wait_for_target[COVER] is True


def test_regression_bbca2e9_predict_position_timezone():
    """UTC target times must index a tz-aware sun table correctly."""
    date = pd.Timestamp("2026-03-20")
    sun_data = FakeSunData(SLC["lat"], SLC["lon"], SLC["tz"], date)
    logger = ConfigContextAdapter(logging.getLogger("predict"))
    logger.set_config_name("Predict")
    with patch(
        "custom_components.adaptive_cover.calculation.SunData",
        return_value=sun_data,
    ):
        cover = AdaptiveVerticalCover(
            hass=SimpleNamespace(),
            logger=logger,
            sol_azi=180.0,
            sol_elev=45.0,
            sunset_pos=0,
            sunset_off=0,
            sunrise_off=0,
            timezone=SLC["tz"],
            fov_left=90,
            fov_right=90,
            win_azi=180,
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

    from custom_components.adaptive_cover.coordinator import (
        AdaptiveDataUpdateCoordinator,
    )

    coord = object.__new__(AdaptiveDataUpdateCoordinator)
    coord.logger = logger

    # Local noon expressed in UTC: 2026-03-20 12:00 MDT == 18:00 UTC.
    target_utc = pd.Timestamp("2026-03-20 18:00", tz="UTC").to_pydatetime()
    predicted = coord._predict_position_at_time(cover, target_utc)

    idx = sun_data.times.get_indexer(
        [pd.Timestamp("2026-03-20 12:00", tz=SLC["tz"])], method="nearest"
    )[0]
    expected = cover.calculate_percentage_at(
        sun_data.solar_azimuth[idx], sun_data.solar_elevation[idx]
    )
    assert predicted == expected
    # Local noon in March has the sun ~47 deg high in front of a south
    # window: the position must be the calculated one, not the default.
    assert predicted != 60


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
