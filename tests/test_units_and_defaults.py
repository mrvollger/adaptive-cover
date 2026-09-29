"""Temperature units and shared defaults (v1.13.5).

Regression: climate thresholds were compared to the sensor's raw number
with no unit handling, and the wizard defaulted to Celsius-shaped 21/25.
A °F house therefore sat in permanent "summer" and winter/glare mode never
engaged.
"""

from __future__ import annotations

import logging

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.config_flow import (
    AUTOMATION_CONFIG,
    OPTIONS,
    VERTICAL_OPTIONS,
    WEATHER_OPTIONS,
    climate_options_for,
)
from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_OCCUPIED_DISTANCE,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_WEATHER_STATE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.options_spec import DEFAULT_OPTIONS

from .conftest import COMMON_OPTIONS

COVER = "cover.test_cover"
TEMP = "sensor.room_temp"


def _default_of(schema, key):
    for marker in schema.schema:
        if marker == key:
            default = marker.default
            return default() if callable(default) else default
    raise KeyError(key)


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
    entry = await _setup_climate_entry(
        hass, low=72, high=75, reading=70, unit=None
    )
    assert _control_method(hass, entry) == "winter"


async def test_regression_wrong_unit_thresholds_warn_once(
    hass, mock_sun_entity, caplog
):
    """Celsius-looking thresholds in a °F house log a warning."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    caplog.set_level(logging.WARNING)
    entry = await _setup_climate_entry(
        hass, low=21, high=23, reading=74, unit="°F"
    )
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
def test_regression_threshold_defaults_follow_unit_system(hass, system, expected):
    hass.config.units = system
    schema = climate_options_for(hass)
    assert (
        _default_of(schema, CONF_TEMP_LOW),
        _default_of(schema, CONF_TEMP_HIGH),
    ) == expected


def test_regression_default_position_fully_open():
    """Wizard and add_entry service agree: 100 (the wizard said 60)."""
    assert _default_of(OPTIONS, CONF_DEFAULT_HEIGHT) == 100
    assert DEFAULT_OPTIONS[CONF_DEFAULT_HEIGHT] == 100


def test_regression_manual_override_default_90_minutes():
    wizard = _default_of(AUTOMATION_CONFIG, CONF_MANUAL_OVERRIDE_DURATION)
    assert wizard == {"hours": 1, "minutes": 30, "seconds": 0}
    assert DEFAULT_OPTIONS[CONF_MANUAL_OVERRIDE_DURATION] == wizard


def test_regression_sunny_conditions_exclude_cloudy():
    states = _default_of(WEATHER_OPTIONS, CONF_WEATHER_STATE)
    assert "cloudy" not in states
    assert {"sunny", "partlycloudy", "clear"} <= set(states)


def test_glare_defaults_prefilled_for_vertical_covers():
    assert _default_of(VERTICAL_OPTIONS, CONF_EYE_HEIGHT) == 1.2
    assert _default_of(VERTICAL_OPTIONS, CONF_OCCUPIED_DISTANCE) == 2.0
