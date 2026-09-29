"""Tests for config flow."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_CLIMATE_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENABLE_BLIND_SPOT,
    CONF_END_ENTITY,
    CONF_END_TIME,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_INTERP,
    CONF_INVERSE_STATE,
    CONF_LENGTH_AWNING,
    CONF_MANUAL_IGNORE_INTERMEDIATE,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MANUAL_THRESHOLD,
    CONF_MAX_ELEVATION,
    CONF_MAX_MOVES_HOUR,
    CONF_MIN_ELEVATION,
    CONF_MODE,
    CONF_OCCUPIED_DISTANCE,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_PRIVACY_MODE,
    CONF_PRIVACY_OFFSET,
    CONF_PRIVACY_POSITION,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_RETURN_SUNSET,
    CONF_SENSOR_TYPE,
    CONF_START_ENTITY,
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


pytestmark = pytest.mark.usefixtures("stub_sun_integration")


@pytest.fixture(autouse=True)
async def unload_all_entries(hass):
    """Unload every entry the flow created (incl. the auto-created hub).

    Completing a flow sets the entry up, and the hub's aggregate cover
    polls on an interval; leaving it loaded leaks that timer past teardown.
    """
    yield
    for entry in hass.config_entries.async_entries():
        if entry.state is config_entries.ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


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
    assert result["title"] == "Living Room"
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
    assert result["title"] == "Terrace"
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
    assert result["title"] == "Bedroom"
    assert result["data"][CONF_SENSOR_TYPE] == SensorType.TILT


async def test_regression_wizard_drops_automation_keys(hass):
    """The setup wizard must persist every option it collects.

    Regression: async_step_update built the created entry's options from a
    hand-maintained whitelist, silently dropping end_time, end_entity,
    return_sunset, privacy_*, quiet_*, max_moves_hour, and overhang/glare
    keys — a fresh entry configured with an end time never closed at end of
    day.  The OptionsFlow already preserved these keys; the wizard must
    round-trip them too.
    """
    geometry_input = {
        **VERTICAL_STEP_INPUT,
        CONF_OVERHANG_DEPTH: 0.6,
        CONF_OVERHANG_HEIGHT: 2.4,
        CONF_EYE_HEIGHT: 1.2,
        CONF_OCCUPIED_DISTANCE: 2.5,
    }
    automation_input = {
        CONF_DELTA_POSITION: 5,
        CONF_DELTA_TIME: 3,
        CONF_START_TIME: "06:30:00",
        CONF_START_ENTITY: "input_datetime.cover_start",
        CONF_MANUAL_OVERRIDE_DURATION: {"minutes": 30},
        CONF_MANUAL_OVERRIDE_RESET: True,
        CONF_MANUAL_THRESHOLD: 10,
        CONF_MANUAL_IGNORE_INTERMEDIATE: True,
        CONF_END_TIME: "22:15:00",
        CONF_END_ENTITY: "input_datetime.cover_end",
        CONF_RETURN_SUNSET: True,
        CONF_PRIVACY_MODE: True,
        CONF_PRIVACY_OFFSET: 45,
        CONF_PRIVACY_POSITION: 10,
        CONF_QUIET_START: "22:00:00",
        CONF_QUIET_END: "07:00:00",
        CONF_MAX_MOVES_HOUR: 4,
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Round Trip", CONF_MODE: SensorType.BLIND},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], geometry_input
    )
    assert result["step_id"] == "automation"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], automation_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    options = result["options"]
    for key, value in {**geometry_input, **automation_input}.items():
        assert key in options, f"wizard dropped option key: {key}"
        assert options[key] == value, (
            f"wizard mangled option {key}: {options[key]!r} != {value!r}"
        )


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


async def _wizard_blind(hass, geometry: dict, automation: dict):
    """Run the setup wizard for a blind; return the final flow result."""
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(
        result["flow_id"], {"name": "Drift fix", CONF_MODE: SensorType.BLIND}
    )
    result = await flow.async_configure(
        result["flow_id"], {**VERTICAL_STEP_INPUT, **geometry}
    )
    assert result["step_id"] == "automation", result
    return await flow.async_configure(
        result["flow_id"], {**AUTOMATION_STEP_INPUT, **automation}
    )


async def _options_submit(hass, entry, **sections: dict):
    """Submit the one-page options form with only ``sections`` filled in."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    user_input = {
        name: sections.get(name, {})
        for name in ("covers_geometry", "sun_behavior", "automation_timing", "climate")
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=user_input
    )
    await hass.async_block_till_done()
    return result


async def test_regression_height_distance_max_ten(hass):
    """Window height and shaded-area distance take up to 10 m on every surface.

    Before P3 the change_settings and add_entry services took 0.1-10 m, but
    the wizard and the options form capped the height at 6 m and the
    distance at 2 m. A tall window or a deep room set by the service could
    not be saved from the options form again. Ledger L0005.
    """
    result = await _wizard_blind(hass, {CONF_HEIGHT_WIN: 8.5, CONF_DISTANCE: 3.0}, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert (entry.options[CONF_HEIGHT_WIN], entry.options[CONF_DISTANCE]) == (8.5, 3.0)

    result = await _options_submit(
        hass, entry, covers_geometry={CONF_HEIGHT_WIN: 10, CONF_DISTANCE: 10}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (entry.options[CONF_HEIGHT_WIN], entry.options[CONF_DISTANCE]) == (10, 10)


async def test_regression_delta_time_min_zero(hass):
    """A time delta of 0 (no throttle) is accepted on every surface.

    Before P3 the services took delta_time >= 0 (and many entries run with
    0), but the wizard and the options form required at least 2 minutes, so
    such an entry could not be saved from the options form without raising
    its throttle. Ledger L0006.
    """
    result = await _wizard_blind(hass, {}, {CONF_DELTA_TIME: 0})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.options[CONF_DELTA_TIME] == 0

    result = await _options_submit(hass, entry, automation_timing={CONF_DELTA_TIME: 1})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    result = await _options_submit(hass, entry, automation_timing={CONF_DELTA_TIME: 0})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DELTA_TIME] == 0
