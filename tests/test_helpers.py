"""Tests for helper functions."""

import datetime as dt

from custom_components.adaptive_cover.helpers import (
    get_datetime_from_str,
    get_domain,
    get_safe_state,
)


async def test_get_safe_state_returns_value(hass):
    """Test get_safe_state returns entity state."""
    hass.states.async_set("sensor.test", "23.5")
    assert get_safe_state(hass, "sensor.test") == "23.5"


async def test_get_safe_state_returns_none_for_unknown(hass):
    """Test get_safe_state returns None for unknown state."""
    hass.states.async_set("sensor.test", "unknown")
    assert get_safe_state(hass, "sensor.test") is None


async def test_get_safe_state_returns_none_for_unavailable(hass):
    """Test get_safe_state returns None for unavailable state."""
    hass.states.async_set("sensor.test", "unavailable")
    assert get_safe_state(hass, "sensor.test") is None


async def test_get_safe_state_returns_none_for_missing(hass):
    """Test get_safe_state returns None for non-existent entity."""
    assert get_safe_state(hass, "sensor.nonexistent") is None


def test_get_domain():
    """Test get_domain extracts domain from entity_id."""
    assert get_domain("cover.bedroom") == "cover"
    assert get_domain("sensor.temperature") == "sensor"
    assert get_domain("binary_sensor.motion") == "binary_sensor"


def test_get_domain_returns_none_for_none():
    """Test get_domain returns None for None input."""
    assert get_domain(None) is None


def test_get_datetime_from_str():
    """Test get_datetime_from_str parses datetime string."""
    result = get_datetime_from_str("2024-06-21 14:30:00")
    assert result == dt.datetime(2024, 6, 21, 14, 30, 0)


def test_get_datetime_from_str_ignores_tz():
    """Test get_datetime_from_str ignores timezone info."""
    result = get_datetime_from_str("2024-06-21T14:30:00+02:00")
    assert result == dt.datetime(2024, 6, 21, 14, 30, 0)


def test_get_datetime_from_str_returns_none_for_none():
    """Test get_datetime_from_str returns None for None input."""
    assert get_datetime_from_str(None) is None
