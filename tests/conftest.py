"""Shared fixtures for adaptive_cover tests."""

from unittest.mock import patch

import pytest

from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
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
def stub_sun_integration(hass, mock_sun_entity):
    """Keep HA's real ``sun`` integration from loading as our dependency.

    Starting a config flow loads adaptive_cover and with it ``sun``, whose
    entry is created by an async import flow: our entry's first refresh can
    then run before ``sun.sun`` exists. Its unload also removes ``sun.sun``
    around the platform, leaking the platform's polling timer past
    teardown. Marking it loaded and providing ``sun.sun`` avoids both.
    """
    hass.config.components.add("sun")


VERTICAL_WINDOW = (
    {"name": "Test Vertical", CONF_SENSOR_TYPE: SensorType.BLIND},
    {**COMMON_OPTIONS, CONF_HEIGHT_WIN: 2.1, CONF_DISTANCE: 0.5},
)
HORIZONTAL_WINDOW = (
    {"name": "Test Horizontal", CONF_SENSOR_TYPE: SensorType.AWNING},
    {
        **COMMON_OPTIONS,
        CONF_HEIGHT_WIN: 2.1,
        CONF_DISTANCE: 0.5,
        CONF_LENGTH_AWNING: 2.1,
        CONF_AWNING_ANGLE: 0,
    },
)
TILT_WINDOW = (
    {"name": "Test Tilt", CONF_SENSOR_TYPE: SensorType.TILT},
    {
        **COMMON_OPTIONS,
        CONF_TILT_DEPTH: 3,
        CONF_TILT_DISTANCE: 2,
        CONF_TILT_MODE: "mode2",
    },
)


@pytest.fixture
def vertical_config_entry(hass):
    """A house with one vertical window (``entry_id`` is also the window key)."""
    from tests.house_model import mock_window_entry

    return mock_window_entry(hass, *VERTICAL_WINDOW)


@pytest.fixture
def horizontal_config_entry(hass):
    """A house with one awning window (``entry_id`` is also the window key)."""
    from tests.house_model import mock_window_entry

    return mock_window_entry(hass, *HORIZONTAL_WINDOW)


@pytest.fixture
def tilt_config_entry(hass):
    """A house with one tilted-blind window (``entry_id`` is also the window key)."""
    from tests.house_model import mock_window_entry

    return mock_window_entry(hass, *TILT_WINDOW)


@pytest.fixture
def entity_registry_enabled_by_default():
    """Create every entity enabled, including the disabled-by-default ones.

    Start sun, End sun, Next change and Last change are diagnostic and
    disabled by default (refactor plan, "Entity surface"). Tests that read
    their states request this fixture, as Home Assistant core tests do.
    """
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
    ):
        yield


@pytest.fixture(autouse=True)
def fail_on_ha_deprecation_reports(caplog):
    """Fail any test in which HA reports deprecated usage by this integration.

    HA's frame helper logs "Detected that custom integration 'adaptive_cover'
    calls ..." instead of raising a DeprecationWarning, so the pytest
    filterwarnings error does not catch it (v1.15.0 shipped one this way).
    """
    yield
    reports = [
        record.getMessage()
        for record in caplog.get_records("call")
        if "Detected that custom integration 'adaptive_cover'" in record.getMessage()
    ]
    assert not reports, "HA reported deprecated usage:\n" + "\n".join(reports)
