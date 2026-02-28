"""Tests for config flow."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_CLIMATE_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENABLE_BLIND_SPOT,
    CONF_END_TIME,
    CONF_ENTITIES,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_INTERP,
    CONF_INVERSE_STATE,
    CONF_LENGTH_AWNING,
    CONF_MANUAL_IGNORE_INTERMEDIATE,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
    CONF_MODE,
    CONF_RETURN_SUNSET,
    CONF_SENSOR_TYPE,
    CONF_START_TIME,
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    DOMAIN,
    SensorType,
)

VERTICAL_STEP_INPUT = {
    CONF_CLIMATE_MODE: False,
    CONF_ENTITIES: [],
    CONF_HEIGHT_WIN: 2.1,
    CONF_DISTANCE: 0.5,
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
}

HORIZONTAL_STEP_INPUT = {
    **VERTICAL_STEP_INPUT,
    CONF_LENGTH_AWNING: 2.1,
    CONF_AWNING_ANGLE: 0,
}

TILT_STEP_INPUT = {
    CONF_CLIMATE_MODE: False,
    CONF_ENTITIES: [],
    CONF_TILT_DEPTH: 3,
    CONF_TILT_DISTANCE: 2,
    CONF_TILT_MODE: "mode2",
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
}

AUTOMATION_STEP_INPUT = {
    CONF_DELTA_POSITION: 1,
    CONF_DELTA_TIME: 2,
    CONF_START_TIME: "00:00:00",
    CONF_MANUAL_OVERRIDE_DURATION: {"minutes": 15},
    CONF_MANUAL_OVERRIDE_RESET: False,
    CONF_MANUAL_IGNORE_INTERMEDIATE: False,
    CONF_END_TIME: "00:00:00",
    CONF_RETURN_SUNSET: False,
}


async def test_user_step_shows_form(hass):
    """Test that the initial step shows a form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_full_vertical_flow(hass):
    """Test complete config flow for vertical blinds."""
    # Step 1: User selects blind type
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Living Room", CONF_MODE: SensorType.BLIND},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "vertical"

    # Step 2: Vertical configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VERTICAL_STEP_INPUT,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "automation"

    # Step 3: Automation configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        AUTOMATION_STEP_INPUT,
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Vertical Living Room"
    assert result["data"][CONF_SENSOR_TYPE] == SensorType.BLIND
    assert result["options"][CONF_AZIMUTH] == 180


async def test_full_horizontal_flow(hass):
    """Test complete config flow for horizontal awnings."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Terrace", CONF_MODE: SensorType.AWNING},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "horizontal"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        HORIZONTAL_STEP_INPUT,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "automation"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        AUTOMATION_STEP_INPUT,
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Horizontal Terrace"
    assert result["data"][CONF_SENSOR_TYPE] == SensorType.AWNING


async def test_full_tilt_flow(hass):
    """Test complete config flow for tilt blinds."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Bedroom", CONF_MODE: SensorType.TILT},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "tilt"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        TILT_STEP_INPUT,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "automation"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        AUTOMATION_STEP_INPUT,
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Tilt Bedroom"
    assert result["data"][CONF_SENSOR_TYPE] == SensorType.TILT


async def test_elevation_validation_error(hass):
    """Test that max_elevation <= min_elevation shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Test", CONF_MODE: SensorType.BLIND},
    )
    assert result["step_id"] == "vertical"

    # Submit with max_elevation <= min_elevation
    bad_input = {
        **VERTICAL_STEP_INPUT,
        CONF_MIN_ELEVATION: 50,
        CONF_MAX_ELEVATION: 30,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        bad_input,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "vertical"
    assert result["errors"] is not None
    assert CONF_MAX_ELEVATION in result["errors"]
