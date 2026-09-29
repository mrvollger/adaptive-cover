"""The clock seam (P2, ADR 0005): a coordinator reads "now" only from its clock.

``tests/engine/test_purity.py`` proves structurally that nothing outside
``runtime/clock.py`` reads the wall clock. These tests prove the seam is
live: a clock injected through ``coordinator.default_clock`` reaches what
users see (the ``adaptive_cover_moved`` logbook event), and the real clock
follows the ``freezer`` fixture the rest of the suite relies on.
"""

from __future__ import annotations

import datetime as dt

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover import coordinator as coordinator_module
from custom_components.adaptive_cover.const import (
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.runtime.clock import SYSTEM_CLOCK

from .characterization.golden_lib import use_real_sun_data
from .conftest import COMMON_OPTIONS
from .window_handle import WindowHandle

COVER = "cover.clock_seam"


class FixedClock:
    """A clock stopped at one instant, far from HA's own clock."""

    def __init__(self, when: dt.datetime) -> None:
        self.when = when

    def utcnow(self) -> dt.datetime:
        return self.when

    def now(self, tz: dt.tzinfo) -> dt.datetime:
        return self.when.astimezone(tz)


async def test_injected_clock_stamps_the_moves(hass, mock_sun_entity, monkeypatch):
    fake_now = dt.datetime(2031, 1, 2, 3, 4, 5, tzinfo=dt.UTC)
    monkeypatch.setattr(coordinator_module, "default_clock", FixedClock(fake_now))
    events = []
    hass.bus.async_listen("adaptive_cover_moved", lambda e: events.append(e.data))
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Clock Seam",
        data={"name": "Clock Seam", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert events, "setup should position the cover"
    assert {event["time"] for event in events} == {
        fake_now.isoformat(timespec="seconds")
    }
    assert dt_util.utcnow().year != 2031  # HA's own clock was not touched


async def test_real_clock_follows_the_freezer(freezer):
    freezer.move_to("2026-11-01 08:30:00+00:00")  # 01:30 MST, after the fold
    assert SYSTEM_CLOCK.utcnow() == dt.datetime(2026, 11, 1, 8, 30, tzinfo=dt.UTC)
    denver = dt_util.get_time_zone("America/Denver")
    local = SYSTEM_CLOCK.now(denver)
    assert local.utcoffset() == dt.timedelta(hours=-7)
    assert (local.hour, local.minute) == (1, 30)


async def test_regression_adapters_use_the_coordinator_clock(
    hass, mock_sun_entity, monkeypatch
):
    """The cover adapters read the coordinator's clock, not the system one.

    build_cover never passed the coordinator's clock, so every adapter (and
    the SunData it builds) fell back to SYSTEM_CLOCK: an injected clock
    reached the move log but not the day the forecast and the engine used.
    """
    fake_now = dt.datetime(2031, 6, 21, 19, 0, tzinfo=dt.UTC)
    monkeypatch.setattr(coordinator_module, "default_clock", FixedClock(fake_now))
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    window = WindowHandle(hass, COVER)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Clock Seam",
        data={"name": "Clock Seam", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
        },
    )
    entry.add_to_hass(hass)
    with use_real_sun_data():
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    forecast = window.attributes["forecast_today"]
    assert forecast, "no forecast"
    tz = dt_util.get_time_zone(hass.config.time_zone)
    days = {dt.datetime.fromisoformat(point["time"]).date() for point in forecast}
    assert days == {fake_now.astimezone(tz).date()}
    assert dt_util.utcnow().year != 2031  # HA's own clock was not touched
