"""The single-page sectioned options flow."""

from __future__ import annotations

from homeassistant import data_entry_flow

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DISTANCE,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_MAX_ELEVATION,
    CONF_PRIVACY_MODE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_LOW,
)


async def _open_options(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return await hass.config_entries.options.async_init(entry.entry_id)


def _section_names(result):
    return [str(marker) for marker in result["data_schema"].schema]


async def test_init_is_single_form_not_menu(
    hass, vertical_config_entry, mock_sun_entity
):
    result = await _open_options(hass, vertical_config_entry)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_sections_for_basic_vertical(
    hass, vertical_config_entry, mock_sun_entity
):
    result = await _open_options(hass, vertical_config_entry)
    names = _section_names(result)
    assert names == ["covers_geometry", "sun_behavior", "automation_timing"]


async def test_climate_section_present_when_enabled(
    hass, vertical_config_entry, mock_sun_entity
):
    hass.config_entries.async_update_entry(
        vertical_config_entry,
        options={
            **vertical_config_entry.options,
            CONF_CLIMATE_MODE: True,
            CONF_TEMP_ENTITY: "sensor.indoor",
        },
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(
        vertical_config_entry.entry_id
    )
    assert "climate" in _section_names(result)


async def test_submit_flattens_sections_and_preserves_rest(
    hass, vertical_config_entry, mock_sun_entity
):
    result = await _open_options(hass, vertical_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "covers_geometry": {
                CONF_HEIGHT_WIN: 2.44,
                CONF_DISTANCE: 0.5,
                CONF_EYE_HEIGHT: 1.2,
            },
            "sun_behavior": {},
            "automation_timing": {CONF_PRIVACY_MODE: True},
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    options = vertical_config_entry.options
    # Flat keys, no section nesting
    assert options[CONF_HEIGHT_WIN] == 2.44
    assert options[CONF_EYE_HEIGHT] == 1.2
    assert options[CONF_PRIVACY_MODE] is True
    assert "covers_geometry" not in options
    # Untouched pre-existing option preserved
    assert options["set_azimuth"] == 180


async def test_absent_nullable_field_clears_setting(
    hass, vertical_config_entry, mock_sun_entity
):
    hass.config_entries.async_update_entry(
        vertical_config_entry,
        options={**vertical_config_entry.options, CONF_MAX_ELEVATION: 50},
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(
        vertical_config_entry.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "covers_geometry": {CONF_HEIGHT_WIN: 2.1, CONF_DISTANCE: 0.5},
            "sun_behavior": {},  # max_elevation omitted -> cleared
            "automation_timing": {},
        },
    )
    await hass.async_block_till_done()
    assert vertical_config_entry.options[CONF_MAX_ELEVATION] is None


async def test_elevation_validation_error(
    hass, vertical_config_entry, mock_sun_entity
):
    result = await _open_options(hass, vertical_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "covers_geometry": {},
            "sun_behavior": {"min_elevation": 40, "max_elevation": 20},
            "automation_timing": {},
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]


async def test_temp_low_editable_in_climate_section(
    hass, vertical_config_entry, mock_sun_entity
):
    hass.config_entries.async_update_entry(
        vertical_config_entry,
        options={
            **vertical_config_entry.options,
            CONF_CLIMATE_MODE: True,
            CONF_TEMP_ENTITY: "sensor.indoor",
            CONF_TEMP_LOW: 21,
        },
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(
        vertical_config_entry.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "covers_geometry": {},
            "sun_behavior": {},
            "automation_timing": {},
            "climate": {CONF_TEMP_ENTITY: "sensor.indoor", CONF_TEMP_LOW: 19},
        },
    )
    await hass.async_block_till_done()
    assert vertical_config_entry.options[CONF_TEMP_LOW] == 19
