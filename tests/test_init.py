"""Tests for integration setup and unload.

"Running" is observed through the window's public surface: a window of the
loaded house whose Position sensor is live; after unload that sensor is
unavailable. Since v2.1 the house entry is the only entry that runs; a 1.x
window entry refuses to set up (tests/test_upgrade_2_1.py has the rest).
"""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import CONF_SENSOR_TYPE, DOMAIN

from .conftest import TILT_WINDOW, VERTICAL_WINDOW
from .house_model import Window, mock_house
from .window_handle import WindowHandle, window_configs


def _running_windows(hass):
    """Windows of the house that are serving entities."""
    return {
        key for key in window_configs(hass) if WindowHandle.by_key(hass, key).available
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


async def test_multiple_entries(hass, mock_sun_entity):
    """Several windows run side by side in the one house entry."""
    windows = [
        Window(name=data["name"], options=options, sensor_type=data[CONF_SENSOR_TYPE])
        for data, options in (VERTICAL_WINDOW, TILT_WINDOW)
    ]
    house = mock_house(hass, windows)
    await hass.config_entries.async_setup(house.entry_id)
    await hass.async_block_till_done()

    assert house.state is ConfigEntryState.LOADED
    # Exactly these two windows run (the house device is not a window).
    assert _running_windows(hass) == {window.key for window in windows}


async def test_a_1x_window_entry_refuses_to_set_up(hass, mock_sun_entity):
    """A window entry from 1.x does not run: consolidate on v2.0.x first."""
    data, options = VERTICAL_WINDOW
    legacy = MockConfigEntry(
        domain=DOMAIN, data=data, options=options, version=1, minor_version=5
    )
    legacy.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(legacy.entry_id)
    await hass.async_block_till_done()

    assert legacy.state is ConfigEntryState.SETUP_ERROR
    assert "not in the house yet" in (legacy.reason or "")
    # Nothing written: v2.0.x finds the entry as it was.
    assert (legacy.version, legacy.minor_version) == (1, 5)
    assert dict(legacy.options) == options
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "consolidate_first")
    assert issue is not None
    assert issue.translation_placeholders["count"] == "1"
