"""Entries created (or reloaded) after sunset must park at the sunset position.

Regression 2026-07-03: splitting the paired entries at 22:15 created six new
entries whose first refresh commanded the DAYTIME default (99) and physically
re-opened every shade at night. The autouse mock_sun_data fixture pins sunset
to tomorrow and sunrise to yesterday, so sunset_valid was always False in the
entire suite and the live night path had zero coverage. These tests run the
REAL SunData against the test hass location (astral), frozen at night.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
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
    CONF_SENSOR_TYPE,
    CONF_SUNSET_POS,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.sun import SunData

from .conftest import COMMON_OPTIONS

COVER = "cover.night_cover"

# Test hass default location: San Diego (32.87, -117.22), tz US/Pacific.
# 2026-07-04 05:15 UTC == 2026-07-03 22:15 PDT: well after sunset (~20:00 PDT),
# well before sunrise (~05:45 PDT).
NIGHT_UTC = "2026-07-04 05:15:00"


@pytest.fixture
def real_sun_data():
    """Give this module the REAL SunData (undo the autouse mock)."""
    import custom_components.adaptive_cover.calculation as calc

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(calc, "SunData", SunData)
        yield


@freeze_time(NIGHT_UTC)
async def test_regression_entry_born_at_night_parks_at_sunset_position(
    hass, real_sun_data
):
    """First refresh after sunset must use the sunset position, not default."""
    hass.states.async_set(
        "sun.sun", "below_horizon", {"azimuth": 320.0, "elevation": -9.0}
    )
    calls = async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 100})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "NightBorn", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
            CONF_SUNSET_POS: 3,
            "sunset_offset": 20,
            "sunrise_offset": -20,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    # The tick state itself must be the sunset position after dark.
    assert coordinator.state == 3, (
        f"night-born entry computed daytime state {coordinator.state}"
    )
    # And any startup command must have parked it at 3, never opened it.
    positions = [c.data["position"] for c in calls]
    assert all(p == 3 for p in positions), positions


@freeze_time(NIGHT_UTC)
async def test_regression_sun_data_dates_follow_configured_timezone(hass):
    """SunData must resolve 'today' in the HA-configured timezone.

    At 05:15 UTC on Jul 4 it is still Jul 3 in US/Pacific: sunset() must
    return Jul 3's sunset (already past), not Jul 4's (still ahead). On a
    host whose process timezone is UTC (HA OS containers), date.today()
    already reads Jul 4 - which silently pushes sunset into the future and
    disables the engine's whole night branch.
    """
    sun_data = SunData(hass.config.time_zone, hass)
    sunset = sun_data.sunset()
    now = datetime.now(UTC)
    assert sunset < now, f"sunset() returned a future time at night: {sunset}"
    sunrise = sun_data.sunrise()
    assert sunrise < now, f"sunrise() must be this morning (past): {sunrise}"
