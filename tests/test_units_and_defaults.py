"""Temperature units and shared defaults (v1.13.5).

Regression: climate thresholds were compared to the sensor's raw number
with no unit handling, and the wizard defaulted to Celsius-shaped 21/25.
A °F house therefore sat in permanent "summer" and winter/glare mode never
engaged.
"""

from __future__ import annotations

import logging

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MODE,
    CONF_OCCUPIED_DISTANCE,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_STATE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.settings.schema import add_entry_baseline

from .conftest import COMMON_OPTIONS

COVER = "cover.test_cover"
TEMP = "sensor.room_temp"


def _default_of(schema, key):
    for marker in schema.schema:
        if marker == key:
            default = marker.default
            return default() if callable(default) else default
    raise KeyError(key)


async def _wizard_forms(hass) -> dict:
    """The setup wizard's forms for a blind, by step id (climate pages on)."""
    forms = {}
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(
        result["flow_id"], {"name": "Defaults", CONF_MODE: SensorType.BLIND}
    )
    forms[result["step_id"]] = result["data_schema"]
    for user_input in (
        {CONF_CLIMATE_MODE: True},
        {},
        {CONF_TEMP_ENTITY: TEMP, CONF_WEATHER_ENTITY: "weather.home"},
    ):
        result = await flow.async_configure(result["flow_id"], user_input)
        forms[result["step_id"]] = result["data_schema"]
    flow.async_abort(result["flow_id"])
    assert set(forms) == {"vertical", "automation", "climate", "weather"}
    return forms


async def _setup_climate_entry(hass, *, low, high, reading, unit):
    hass.states.async_set(
        TEMP, str(reading), {"unit_of_measurement": unit, "device_class": "temperature"}
    )
    hass.states.async_set(COVER, "open", {"current_position": 60})
    async_mock_service(hass, "cover", "set_cover_position")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Units test", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.0,
            CONF_DISTANCE: 0.1,
            CONF_ENTITIES: [COVER],
            CONF_CLIMATE_MODE: True,
            CONF_TEMP_ENTITY: TEMP,
            CONF_TEMP_LOW: low,
            CONF_TEMP_HIGH: high,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _control_method(hass, entry) -> str:
    registry = er.async_get(hass)
    entity_id = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if "control_method" in e.entity_id
    )
    return hass.states.get(entity_id).state


# ------------------------------------------------------------ conversion


@pytest.mark.parametrize(
    ("system", "low", "high", "reading", "unit", "expected"),
    [
        # The house: °F system, °F sensor, °F thresholds -> unchanged behavior.
        (US_CUSTOMARY_SYSTEM, 72, 75, 71.0, "°F", "winter"),
        (US_CUSTOMARY_SYSTEM, 72, 75, 73.5, "°F", "intermediate"),
        (US_CUSTOMARY_SYSTEM, 72, 75, 78.0, "°F", "summer"),
        # Metric system with a °F sensor: 68 °F = 20 °C < 22 -> winter.
        (METRIC_SYSTEM, 22, 24, 68.0, "°F", "winter"),
        # Imperial system with a °C sensor: 26 °C = 78.8 °F > 75 -> summer.
        (US_CUSTOMARY_SYSTEM, 72, 75, 26.0, "°C", "summer"),
    ],
)
async def test_regression_sensor_unit_converted_to_system_unit(
    hass, mock_sun_entity, system, low, high, reading, unit, expected
):
    hass.config.units = system
    entry = await _setup_climate_entry(
        hass, low=low, high=high, reading=reading, unit=unit
    )
    assert _control_method(hass, entry) == expected


async def test_unitless_sensor_passes_through(hass, mock_sun_entity):
    """No unit attribute: the number is used as-is (historical behavior)."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    hass.states.async_set(COVER, "open", {"current_position": 60})
    entry = await _setup_climate_entry(hass, low=72, high=75, reading=70, unit=None)
    assert _control_method(hass, entry) == "winter"


async def test_regression_wrong_unit_thresholds_warn_once(
    hass, mock_sun_entity, caplog
):
    """Celsius-looking thresholds in a °F house log a warning."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    caplog.set_level(logging.WARNING)
    entry = await _setup_climate_entry(hass, low=21, high=23, reading=74, unit="°F")
    hass.states.async_set(TEMP, "74.5", {"unit_of_measurement": "°F"})
    await hass.async_block_till_done()
    warnings = [r for r in caplog.records if "look like the wrong unit" in r.message]
    assert len(warnings) == 1
    assert "temp_low=21" in warnings[0].message
    assert entry is not None


async def test_sane_thresholds_do_not_warn(hass, mock_sun_entity, caplog):
    hass.config.units = US_CUSTOMARY_SYSTEM
    caplog.set_level(logging.WARNING)
    await _setup_climate_entry(hass, low=72, high=75, reading=74, unit="°F")
    assert not [r for r in caplog.records if "wrong unit" in r.message]


# -------------------------------------------------------------- defaults


@pytest.mark.parametrize(
    ("system", "expected"),
    [(US_CUSTOMARY_SYSTEM, (72, 75)), (METRIC_SYSTEM, (22, 24))],
)
@pytest.mark.usefixtures("stub_sun_integration")
async def test_regression_threshold_defaults_follow_unit_system(hass, system, expected):
    hass.config.units = system
    schema = (await _wizard_forms(hass))["climate"]
    assert (
        _default_of(schema, CONF_TEMP_LOW),
        _default_of(schema, CONF_TEMP_HIGH),
    ) == expected


@pytest.mark.usefixtures("stub_sun_integration")
async def test_regression_default_position_fully_open(hass):
    """Wizard and add_entry service agree: 100 (the wizard said 60)."""
    schema = (await _wizard_forms(hass))["vertical"]
    assert _default_of(schema, CONF_DEFAULT_HEIGHT) == 100
    assert add_entry_baseline()[CONF_DEFAULT_HEIGHT] == 100


@pytest.mark.usefixtures("stub_sun_integration")
async def test_regression_manual_override_default_two_hours(hass):
    schema = (await _wizard_forms(hass))["automation"]
    wizard = _default_of(schema, CONF_MANUAL_OVERRIDE_DURATION)
    assert wizard == {"hours": 2, "minutes": 0, "seconds": 0}
    assert add_entry_baseline()[CONF_MANUAL_OVERRIDE_DURATION] == wizard


@pytest.mark.usefixtures("stub_sun_integration")
async def test_regression_sunny_conditions_exclude_cloudy(hass):
    states = _default_of((await _wizard_forms(hass))["weather"], CONF_WEATHER_STATE)
    assert "cloudy" not in states
    assert {"sunny", "partlycloudy", "clear"} <= set(states)


@pytest.mark.usefixtures("stub_sun_integration")
async def test_glare_defaults_prefilled_for_vertical_covers(hass):
    schema = (await _wizard_forms(hass))["vertical"]
    assert _default_of(schema, CONF_EYE_HEIGHT) == 1.2
    assert _default_of(schema, CONF_OCCUPIED_DISTANCE) == 2.0


# (min, max, default) of each threshold per HA temperature unit; step 0.5.
THRESHOLD_SHAPES = {
    "°C": {CONF_TEMP_LOW: (5, 30, 22), CONF_TEMP_HIGH: (10, 40, 24)},
    "°F": {CONF_TEMP_LOW: (40, 90, 72), CONF_TEMP_HIGH: (50, 100, 75)},
}


def _selector_shape(schema, key):
    """(min, max, step, unit) of the number selector for ``key``."""
    for marker, validator in schema.schema.items():
        if marker == key:
            config = validator.config
            return (
                config.get("min"),
                config.get("max"),
                config.get("step"),
                config.get("unit_of_measurement"),
            )
    raise KeyError(key)


@pytest.mark.parametrize(
    ("system", "unit", "inside", "outside"),
    [(METRIC_SYSTEM, "°C", 21.5, 72), (US_CUSTOMARY_SYSTEM, "°F", 70.5, 21)],
    ids=["celsius", "fahrenheit"],
)
@pytest.mark.usefixtures("stub_sun_integration")
async def test_regression_thresholds_unit_aware_everywhere(
    hass, system, unit, inside, outside
):
    """Heating/cooling thresholds use HA's temperature unit on every surface.

    Thresholds are stored and compared in HA's unit (v1.13.5) and the
    number entities followed it (v1.15.1), but the wizard and the options
    form still showed a unit-less 0-86 / 0-90 slider in whole degrees, and
    change_settings / add_entry accepted any number: a °F house could set
    21 (a Celsius value) and sit in permanent winter. Now every surface
    shows the unit with that unit's range and 0.5 steps, the services
    reject a value outside it, and the °C numbers default to the spec's
    22 / 24 (they showed 21 / 25). Ledger L0008.
    """
    hass.config.units = system
    shapes = THRESHOLD_SHAPES[unit]

    wizard = (await _wizard_forms(hass))["climate"]
    for key, (low, high, default) in shapes.items():
        assert _selector_shape(wizard, key) == (low, high, 0.5, unit)
        assert _default_of(wizard, key) == default

    entry = await _setup_climate_entry(
        hass, low=None, high=None, reading=shapes[CONF_TEMP_LOW][2], unit=unit
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    climate = result["data_schema"].schema["climate"].schema
    hass.config_entries.options.async_abort(result["flow_id"])
    registry = er.async_get(hass)
    for key, (low, high, default) in shapes.items():
        assert _selector_shape(climate, key) == (low, high, 0.5, unit)
        state = hass.states.get(
            registry.async_get_entity_id(
                "number", DOMAIN, f"{entry.entry_id}_number_{key}"
            )
        )
        assert float(state.state) == default
        assert (
            state.attributes["min"],
            state.attributes["max"],
            state.attributes["unit_of_measurement"],
        ) == (low, high, unit)

    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id, CONF_TEMP_LOW: inside},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_TEMP_LOW] == inside
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "change_settings",
            {"config_entry": entry.entry_id, CONF_TEMP_LOW: outside},
            blocking=True,
        )
    assert entry.options[CONF_TEMP_LOW] == inside
