"""The adaptive_cover.add_entry service: wizard-free onboarding."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

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

TEMPLATE_COVER = "cover.template_cover"


@pytest.fixture
def template_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Template shades",
        data={"name": "Template shades", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.2,
            CONF_AZIMUTH: 235,
            CONF_ENTITIES: [TEMPLATE_COVER],
        },
    )
    entry.add_to_hass(hass)
    return entry


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

    entry = hass.config_entries.async_get_entry(response["entry_id"])
    assert entry.title == "New window"
    assert entry.options[CONF_AZIMUTH] == 280  # override applied
    assert entry.options[CONF_DISTANCE] == 0.2  # template value kept
    assert entry.options[CONF_ENTITIES] == ["cover.new_cover"]
    assert entry.entry_id in hass.data[DOMAIN]  # loaded and running


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
    entry = hass.config_entries.async_get_entry(response["entry_id"])
    assert entry.options[CONF_AZIMUTH] == 90
    assert entry.options[CONF_HEIGHT_WIN] == 2.1  # default


async def test_add_entry_bad_template_raises(
    hass, template_entry, mock_sun_entity
):
    await _setup(hass, template_entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "add_entry",
            {"name": "X", "covers": ["cover.x"], "copy_from": "nope"},
            blocking=True,
        )
