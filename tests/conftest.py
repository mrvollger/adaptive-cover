"""Shared fixtures for adaptive_cover tests."""

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


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Log timers left running after teardown instead of failing the test.

    Since HA 2026.8, phcc's ``verify_cleanup`` inspects the test's own event
    loop (earlier releases looked at a different loop and never saw these).
    It exposes timers the integration does not cancel on unload: the
    125 s arrival poll (``_schedule_arrival_poll``), point-in-time
    trackers and the hub cover's polling interval. Remove this override
    once unload cancels them (runtime split, P4).
    """
    return True


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto-enable custom integrations defined in the test dir."""


@pytest.fixture(autouse=True)
def _restore_sun_data_factory():
    """Guard: no test can leak a sun-data override into the next test.

    (A simulation that fails before teardown never stops its override.)
    """
    from custom_components.adaptive_cover import calculation

    saved = calculation.sun_data_factory
    yield
    calculation.sun_data_factory = saved


@pytest.fixture(autouse=True)
def mock_sun_data(_restore_sun_data_factory):
    """Give every adapter the deterministic flat sun (no astral config needed).

    Yields the FlatSunData instance; tests move the day's boundaries with
    ``mock_sun_data.sunrise_at`` / ``mock_sun_data.sunset_at``.
    """
    # Sun-provider replacement is centralized in golden_lib (the single
    # sanctioned test-side seam); import lazily so collection stays light.
    from tests.characterization.golden_lib import FlatSunData, patch_sun_data

    sun = FlatSunData()
    with patch_sun_data(sun):
        yield sun


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
