"""The adaptive_cover.change_settings service: persistent scripted tuning."""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

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

COVER = "cover.test_cover"


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SE test shades",
        data={"name": "Family room test", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.0,
            CONF_DISTANCE: 0.1,
            CONF_ENTITIES: [COVER],
            CONF_DELTA_TIME: 0,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry):
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_change_settings_persists_and_reloads(
    hass, entry, mock_sun_entity
):
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

    assert entry.options[CONF_OVERHANG_DEPTH] == 1.2
    assert entry.options[CONF_OVERHANG_HEIGHT] == 2.6
    assert entry.options[CONF_PRIVACY_MODE] is True
    assert response["changed"] == sorted(
        [CONF_OVERHANG_DEPTH, CONF_OVERHANG_HEIGHT, CONF_EYE_HEIGHT,
         CONF_PRIVACY_MODE]
    )
    # Reload picked it up: the cover adapter now has the overhang
    coordinator = hass.data[DOMAIN][entry.entry_id]
    cover_data = coordinator.get_blind_data(coordinator.config_entry.options)
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
        assert entry.options[CONF_EYE_HEIGHT] == 1.0


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
