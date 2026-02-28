"""Tests for integration setup and unload."""

from homeassistant.config_entries import ConfigEntryState

from custom_components.adaptive_cover.const import DOMAIN


async def test_setup_and_unload_vertical(hass, vertical_config_entry, mock_sun_entity):
    """Test setup and unload of a vertical cover entry."""
    await hass.config_entries.async_setup(vertical_config_entry.entry_id)
    await hass.async_block_till_done()

    assert vertical_config_entry.state is ConfigEntryState.LOADED
    assert DOMAIN in hass.data
    assert vertical_config_entry.entry_id in hass.data[DOMAIN]

    # Verify coordinator was created
    coordinator = hass.data[DOMAIN][vertical_config_entry.entry_id]
    assert coordinator is not None

    # Unload
    await hass.config_entries.async_unload(vertical_config_entry.entry_id)
    await hass.async_block_till_done()

    assert vertical_config_entry.state is ConfigEntryState.NOT_LOADED
    assert vertical_config_entry.entry_id not in hass.data[DOMAIN]


async def test_setup_and_unload_horizontal(
    hass, horizontal_config_entry, mock_sun_entity
):
    """Test setup and unload of a horizontal cover entry."""
    await hass.config_entries.async_setup(horizontal_config_entry.entry_id)
    await hass.async_block_till_done()

    assert horizontal_config_entry.state is ConfigEntryState.LOADED
    assert horizontal_config_entry.entry_id in hass.data[DOMAIN]

    await hass.config_entries.async_unload(horizontal_config_entry.entry_id)
    await hass.async_block_till_done()

    assert horizontal_config_entry.state is ConfigEntryState.NOT_LOADED
    assert horizontal_config_entry.entry_id not in hass.data[DOMAIN]


async def test_setup_and_unload_tilt(hass, tilt_config_entry, mock_sun_entity):
    """Test setup and unload of a tilt cover entry."""
    await hass.config_entries.async_setup(tilt_config_entry.entry_id)
    await hass.async_block_till_done()

    assert tilt_config_entry.state is ConfigEntryState.LOADED
    assert tilt_config_entry.entry_id in hass.data[DOMAIN]

    await hass.config_entries.async_unload(tilt_config_entry.entry_id)
    await hass.async_block_till_done()

    assert tilt_config_entry.state is ConfigEntryState.NOT_LOADED
    assert tilt_config_entry.entry_id not in hass.data[DOMAIN]


async def test_multiple_entries(
    hass, vertical_config_entry, tilt_config_entry, mock_sun_entity
):
    """Test that multiple entries can coexist."""
    # Setting up the first entry loads the integration, which also sets up
    # all other pending entries for the domain.
    await hass.config_entries.async_setup(vertical_config_entry.entry_id)
    await hass.async_block_till_done()

    assert vertical_config_entry.state is ConfigEntryState.LOADED
    assert tilt_config_entry.state is ConfigEntryState.LOADED
    assert vertical_config_entry.entry_id in hass.data[DOMAIN]
    assert tilt_config_entry.entry_id in hass.data[DOMAIN]
    assert len(hass.data[DOMAIN]) == 2
