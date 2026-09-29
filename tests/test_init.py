"""Tests for integration setup and unload.

"Running" is observed through the window's public surface: a loaded entry
whose Position sensor is live; after unload that sensor is unavailable.
"""

from homeassistant.config_entries import ConfigEntryState

from custom_components.adaptive_cover.const import DOMAIN
from custom_components.adaptive_cover.hub import is_hub_entry

from .window_handle import WindowHandle


def _running_windows(hass):
    """Window entries (hub excluded) that are loaded and serving entities."""
    return {
        entry.entry_id
        for entry in hass.config_entries.async_entries(DOMAIN)
        if not is_hub_entry(entry)
        and entry.state is ConfigEntryState.LOADED
        and WindowHandle.by_key(hass, entry.entry_id).available
    }


async def test_setup_and_unload_vertical(hass, vertical_config_entry, mock_sun_entity):
    """Test setup and unload of a vertical cover entry."""
    window = WindowHandle.by_key(hass, vertical_config_entry.entry_id)
    await hass.config_entries.async_setup(vertical_config_entry.entry_id)
    await hass.async_block_till_done()

    assert vertical_config_entry.state is ConfigEntryState.LOADED
    # The window is running: its Position sensor is live.
    assert window.available
    assert window.target is not None

    # Unload
    await hass.config_entries.async_unload(vertical_config_entry.entry_id)
    await hass.async_block_till_done()

    assert vertical_config_entry.state is ConfigEntryState.NOT_LOADED
    assert not window.available


async def test_setup_and_unload_horizontal(
    hass, horizontal_config_entry, mock_sun_entity
):
    """Test setup and unload of a horizontal cover entry."""
    window = WindowHandle.by_key(hass, horizontal_config_entry.entry_id)
    await hass.config_entries.async_setup(horizontal_config_entry.entry_id)
    await hass.async_block_till_done()

    assert horizontal_config_entry.state is ConfigEntryState.LOADED
    assert window.available

    await hass.config_entries.async_unload(horizontal_config_entry.entry_id)
    await hass.async_block_till_done()

    assert horizontal_config_entry.state is ConfigEntryState.NOT_LOADED
    assert not window.available


async def test_setup_and_unload_tilt(hass, tilt_config_entry, mock_sun_entity):
    """Test setup and unload of a tilt cover entry."""
    window = WindowHandle.by_key(hass, tilt_config_entry.entry_id)
    await hass.config_entries.async_setup(tilt_config_entry.entry_id)
    await hass.async_block_till_done()

    assert tilt_config_entry.state is ConfigEntryState.LOADED
    assert window.available

    await hass.config_entries.async_unload(tilt_config_entry.entry_id)
    await hass.async_block_till_done()

    assert tilt_config_entry.state is ConfigEntryState.NOT_LOADED
    assert not window.available


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
    # Exactly these two windows run (the auto-created hub is not a window).
    assert _running_windows(hass) == {
        vertical_config_entry.entry_id,
        tilt_config_entry.entry_id,
    }
