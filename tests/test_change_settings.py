"""The adaptive_cover.change_settings service: persistent scripted tuning."""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.adaptive_cover.const import (
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_PRIVACY_MODE,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)

from .conftest import COMMON_OPTIONS
from .house_model import mock_window_entry, window_subentry
from .window_form import record
from .window_handle import internal_coordinator, window_settings

COVER = "cover.test_cover"


@pytest.fixture
def entry(hass):
    """A house with one window: title "SE test shades", name "Family room test".

    ``entry.entry_id`` is also the window's key.
    """
    return mock_window_entry(
        hass,
        {"name": "Family room test", CONF_SENSOR_TYPE: SensorType.BLIND},
        {
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.0,
            CONF_DISTANCE: 0.1,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
        title="SE test shades",
    )


def _window(entry):
    """The window subentry of the fixture's house."""
    return window_subentry(entry, entry.entry_id)


async def _setup(hass, entry):
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_change_settings_persists_and_reloads(hass, entry, mock_sun_entity):
    """Rolling the pilot config to an entry is one service call."""
    await _setup(hass, entry)

    response = await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {
            "config_entry": entry.entry_id,
            CONF_OVERHANG_DEPTH: 1.2,
            CONF_OVERHANG_HEIGHT: 2.6,
            CONF_EYE_HEIGHT: 1.2,
            CONF_PRIVACY_MODE: True,
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    geometry = record(_window(entry)).geometry
    assert geometry[CONF_OVERHANG_DEPTH] == 1.2
    assert geometry[CONF_OVERHANG_HEIGHT] == 2.6
    assert geometry[CONF_PRIVACY_MODE] is True
    assert response["changed"] == sorted(
        [CONF_OVERHANG_DEPTH, CONF_OVERHANG_HEIGHT, CONF_EYE_HEIGHT, CONF_PRIVACY_MODE]
    )
    # Reload picked it up: the cover adapter now has the overhang.
    # contract: internal (no entity exposes the adapter's overhang/privacy
    # config; the P5 Position `provenance` attribute will)
    coordinator = internal_coordinator(hass, entry.entry_id)
    cover_data = coordinator.get_blind_data(coordinator.options)
    assert cover_data.overhang is not None
    assert cover_data.privacy is not None and cover_data.privacy.enabled


async def test_lookup_by_title_and_name(hass, entry, mock_sun_entity):
    await _setup(hass, entry)
    for reference in ("SE test shades", "Family room test"):
        await hass.services.async_call(
            DOMAIN,
            "change_settings",
            {"config_entry": reference, CONF_EYE_HEIGHT: 1.0},
            blocking=True,
        )
        await hass.async_block_till_done()
        # A recurring setting: the window's own value (P5 flip: an override).
        assert (await window_settings(hass, entry.entry_id))[CONF_EYE_HEIGHT] == 1.0


async def test_unknown_entry_raises(hass, entry, mock_sun_entity):
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "change_settings",
            {"config_entry": "nope", CONF_EYE_HEIGHT: 1.0},
            blocking=True,
        )


async def test_unknown_key_rejected_by_schema(hass, entry, mock_sun_entity):
    await _setup(hass, entry)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "change_settings",
            {"config_entry": entry.entry_id, "sensor_type": "cover_tilt"},
            blocking=True,
        )


async def test_no_changes_raises(hass, entry, mock_sun_entity):
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "change_settings",
            {"config_entry": entry.entry_id},
            blocking=True,
        )


async def test_regression_rename_updates_title_and_device_name(
    hass, entry, mock_sun_entity
):
    """change_settings with name renames the window without breaking entities.

    User request 2026-07-04: room-based names ("Office north") replacing the
    compass wizard names ("NE north shade") - without recreating entries.
    """
    from homeassistant.helpers import entity_registry as er

    await _setup(hass, entry)
    registry = er.async_get(hass)
    before = {
        e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert before

    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id, "name": "Office north"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert _window(entry).title == "Office north"
    assert record(_window(entry)).name == "Office north"
    after = {
        e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert after == before  # rename must never orphan entities


async def test_rename_combines_with_option_changes(hass, entry, mock_sun_entity):
    await _setup(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id, "name": "Renamed", CONF_EYE_HEIGHT: 1.4},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert _window(entry).title == "Renamed"
    assert (await window_settings(hass, entry.entry_id))[CONF_EYE_HEIGHT] == 1.4


async def test_regression_change_settings_enables_climate_mode(
    hass, entry, mock_sun_entity
):
    """Climate control and its sensors can be rolled out via the service.

    Previously climate_mode / temp_entity / weather settings were not
    changeable, so enabling winter behavior on an existing entry required
    walking the whole options wizard per window. Since 3.2 (one Climate
    switch) a temperature source is all a window needs: there is no
    climate_mode to turn on.
    """
    from homeassistant.helpers import entity_registry as er
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

    # A °F house: the services validate thresholds in HA's unit (L0008),
    # and 70 / 74 are °F values.
    hass.config.units = US_CUSTOMARY_SYSTEM
    hass.states.async_set("sensor.room_temp", "68.0")
    hass.states.async_set("weather.home", "sunny")
    await _setup(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {
            "config_entry": entry.entry_id,
            "temp_entity": "sensor.room_temp",
            "weather_entity": "weather.home",
            "weather_state": ["sunny", "clear"],
            "temp_low": 70,
            "temp_high": 74,
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    # Recurring settings: the window's own values (P5 flip: overrides).
    settings = await window_settings(hass, entry.entry_id)
    assert "climate_mode" not in settings
    assert settings["ignore_climate"] is False
    assert settings["temp_entity"] == "sensor.room_temp"
    assert settings["weather_state"] == ["sunny", "clear"]
    # The window was rebuilt in climate mode and the season resolves in the
    # sensor's own unit: 68 °F < 70 → winter.
    registry = er.async_get(hass)
    method = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_Control Method"
    )
    assert hass.states.get(method).state == "winter"


async def test_change_settings_rejects_bad_entity_id(hass, entry, mock_sun_entity):
    """Entity fields are validated as entity ids."""
    await _setup(hass, entry)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "change_settings",
            {"config_entry": entry.entry_id, "temp_entity": "not an entity"},
            blocking=True,
        )
