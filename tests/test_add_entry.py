"""The adaptive_cover.add_entry service: wizard-free onboarding."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)

from .conftest import COMMON_OPTIONS
from .house_model import mock_window_entry, window_subentry
from .window_form import record
from .window_handle import WindowHandle

TEMPLATE_COVER = "cover.template_cover"


@pytest.fixture
def template_entry(hass):
    """A house with the "Template shades" window (key: the house's entry_id)."""
    return mock_window_entry(
        hass,
        {"name": "Template shades", CONF_SENSOR_TYPE: SensorType.BLIND},
        {
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.2,
            CONF_AZIMUTH: 235,
            CONF_ENTITIES: [TEMPLATE_COVER],
        },
    )


async def _setup(hass, entry):
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(TEMPLATE_COVER, "open", {"current_position": 50})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_add_entry_from_template(hass, template_entry, mock_sun_entity):
    await _setup(hass, template_entry)
    hass.states.async_set("cover.new_cover", "open", {"current_position": 50})

    response = await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {
            "name": "New window",
            "covers": ["cover.new_cover"],
            "copy_from": "Template shades",
            CONF_AZIMUTH: 280,
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    # A window of the house (the integration's one entry).
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    window = window_subentry(template_entry, response["entry_id"])
    stored = record(window)
    assert window.title == "New window"
    assert stored.geometry[CONF_AZIMUTH] == 280  # override applied
    assert stored.geometry[CONF_DISTANCE] == 0.2  # template value kept
    assert stored.cover == "cover.new_cover"
    # Running: the new window serves its Position sensor.
    assert template_entry.state is ConfigEntryState.LOADED
    assert WindowHandle(hass, "cover.new_cover").available


async def test_add_entry_defaults_without_template(
    hass, template_entry, mock_sun_entity
):
    await _setup(hass, template_entry)
    response = await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {"name": "Bare window", "covers": ["cover.x"], CONF_AZIMUTH: 90},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    stored = record(window_subentry(template_entry, response["entry_id"]))
    assert stored.geometry[CONF_AZIMUTH] == 90
    assert stored.geometry[CONF_HEIGHT_WIN] == 2.1  # default


async def test_add_entry_bad_template_raises(hass, template_entry, mock_sun_entity):
    await _setup(hass, template_entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "add_entry",
            {"name": "X", "covers": ["cover.x"], "copy_from": "nope"},
            blocking=True,
        )
