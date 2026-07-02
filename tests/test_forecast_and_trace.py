"""Forecast attribute, decision trace exposure, and get_forecast service."""

from __future__ import annotations

import datetime as dt

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.adaptive_cover.const import (
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_PRIVACY_MODE,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)

from .conftest import COMMON_OPTIONS

COVER = "cover.test_cover"


def _entry(hass, **extra):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Forecast Test", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
            **extra,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry):
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


async def test_forecast_attribute_present(hass, mock_sun_entity):
    """Coordinator publishes a change-point forecast for today."""
    coordinator = await _setup(hass, _entry(hass))
    forecast = coordinator.data.attributes["forecast_today"]
    assert isinstance(forecast, list) and forecast
    entry0 = forecast[0]
    assert set(entry0) == {"time", "position", "intent"}
    # Perpetual-noon mock sun: constant conditions collapse to few entries
    assert len(forecast) <= 5


async def test_forecast_is_change_points_only(hass, mock_sun_entity):
    coordinator = await _setup(hass, _entry(hass))
    forecast = coordinator.data.attributes["forecast_today"]
    pairs = [(e["position"], e["intent"]) for e in forecast]
    assert all(a != b for a, b in zip(pairs, pairs[1:]))


async def test_intent_and_trace_exposed(hass, mock_sun_entity):
    coordinator = await _setup(hass, _entry(hass))
    attrs = coordinator.data.attributes
    assert attrs["intent"] == "calculated"  # mock sun square in window
    assert isinstance(attrs["decision_trace"], list)
    assert any("calculated" in line for line in attrs["decision_trace"])


async def test_forecast_includes_privacy_window(
    hass, mock_sun_data, mock_sun_entity
):
    """With privacy on, the schedule contains privacy entries."""
    now = dt.datetime.now(dt.UTC)
    # Sunset in the recent past so part of the table falls in the window
    mock_sun_data.sunset.return_value = now - dt.timedelta(hours=2)
    mock_sun_data.sunrise.return_value = now - dt.timedelta(hours=14)
    coordinator = await _setup(hass, _entry(hass, **{CONF_PRIVACY_MODE: True}))
    forecast = coordinator.data.attributes["forecast_today"]
    intents = {e["intent"] for e in forecast}
    assert "privacy" in intents


async def test_get_forecast_service(hass, mock_sun_entity):
    entry = _entry(hass)
    coordinator = await _setup(hass, entry)
    response = await hass.services.async_call(
        DOMAIN,
        "get_forecast",
        {"config_entry": entry.entry_id},
        blocking=True,
        return_response=True,
    )
    assert response["forecast"] == coordinator.forecast


async def test_get_forecast_service_by_title(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    response = await hass.services.async_call(
        DOMAIN,
        "get_forecast",
        {"config_entry": entry.title},
        blocking=True,
        return_response=True,
    )
    assert isinstance(response["forecast"], list)


async def test_sun_geometry_attribute(hass, mock_sun_entity):
    """The sun attribute block feeds the sky-compass card."""
    coordinator = await _setup(hass, _entry(hass))
    sun = coordinator.data.attributes["sun"]
    assert sun["azimuth"] == 180.0
    assert sun["elevation"] == 45.0
    assert sun["gamma"] == 0.0
    assert sun["in_fov"] is True
    assert sun["window_azimuth"] == 180
    assert sun["fov_left"] == 90 and sun["fov_right"] == 90
