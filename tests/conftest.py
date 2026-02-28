"""Shared fixtures for adaptive_cover tests."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_CLIMATE_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENABLE_BLIND_SPOT,
    CONF_ENABLE_MAX_POSITION,
    CONF_ENABLE_MIN_POSITION,
    CONF_ENTITIES,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_INTERP,
    CONF_INVERSE_STATE,
    CONF_LENGTH_AWNING,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MODE,
    CONF_SENSOR_TYPE,
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    DOMAIN,
    SensorType,
)

COMMON_OPTIONS = {
    CONF_MODE: "basic",
    CONF_AZIMUTH: 180,
    CONF_DEFAULT_HEIGHT: 60,
    CONF_FOV_LEFT: 90,
    CONF_FOV_RIGHT: 90,
    CONF_SUNSET_POS: 0,
    CONF_SUNSET_OFFSET: 0,
    CONF_SUNRISE_OFFSET: 0,
    CONF_INVERSE_STATE: False,
    CONF_ENABLE_BLIND_SPOT: False,
    CONF_INTERP: False,
    CONF_CLIMATE_MODE: False,
    CONF_ENTITIES: [],
    CONF_ENABLE_MAX_POSITION: False,
    CONF_ENABLE_MIN_POSITION: False,
    CONF_DELTA_POSITION: 1,
    CONF_DELTA_TIME: 2,
    CONF_MANUAL_OVERRIDE_DURATION: {"minutes": 15},
    CONF_MANUAL_OVERRIDE_RESET: False,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto-enable custom integrations defined in the test dir."""


@pytest.fixture(autouse=True)
def mock_sun_data():
    """Mock SunData to avoid needing real astral location config."""
    # Use UTC-based dates to avoid local/UTC date mismatch with datetime.utcnow()
    now_utc = datetime.now(timezone.utc)
    tomorrow = now_utc + timedelta(days=1)
    yesterday = now_utc - timedelta(days=1)
    mock_instance = MagicMock()
    mock_instance.sunset.return_value = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 23, 59, 59, tzinfo=timezone.utc
    )
    mock_instance.sunrise.return_value = datetime(
        yesterday.year, yesterday.month, yesterday.day, 0, 0, 1, tzinfo=timezone.utc
    )
    # Provide solar data for solar_times() method
    today = now_utc.date()
    times = pd.date_range(start=today, periods=289, freq="5min", tz="UTC")
    mock_instance.times = times
    mock_instance.solar_azimuth = [180.0] * len(times)
    mock_instance.solar_elevation = [45.0] * len(times)

    with patch(
        "custom_components.adaptive_cover.calculation.SunData",
        return_value=mock_instance,
    ):
        yield mock_instance


@pytest.fixture
def mock_sun_entity(hass):
    """Set up sun.sun entity with azimuth/elevation attributes."""
    hass.states.async_set(
        "sun.sun",
        "above_horizon",
        {"azimuth": 180.0, "elevation": 45.0},
    )


@pytest.fixture
def vertical_config_entry(hass):
    """Create a mock config entry for vertical cover."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Test Vertical", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def horizontal_config_entry(hass):
    """Create a mock config entry for horizontal cover."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Test Horizontal", CONF_SENSOR_TYPE: SensorType.AWNING},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_LENGTH_AWNING: 2.1,
            CONF_AWNING_ANGLE: 0,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def tilt_config_entry(hass):
    """Create a mock config entry for tilt cover."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Test Tilt", CONF_SENSOR_TYPE: SensorType.TILT},
        options={
            **COMMON_OPTIONS,
            CONF_TILT_DEPTH: 3,
            CONF_TILT_DISTANCE: 2,
            CONF_TILT_MODE: "mode2",
        },
    )
    entry.add_to_hass(hass)
    return entry
