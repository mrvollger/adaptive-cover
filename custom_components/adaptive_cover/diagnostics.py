"""Adaptive Cover integration diagnostics.

The house entry's download is the house plus every window subentry; a
window device's download is that one window.
"""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN
from .windows import WindowEntry, subentry_windows


def window_diagnostics(hass: HomeAssistant, window: WindowEntry) -> dict[str, Any]:
    """Return one window's diagnostics.

    ``config_data`` is what the subentry stores; ``settings`` is what a
    running window acts on (its resolved layered settings) and
    ``settings_provenance`` the options that come from an area, a floor or
    the window itself; both None for a window that is not running.
    """
    from .house import window_coordinator

    coordinator = window_coordinator(hass, window.window_key)
    subentry = window.subentry
    return {
        "title": "Adaptive Cover Configuration",
        "type": "config_subentry",
        "identifier": window.window_key,
        "config_data": dict(subentry.data) if subentry is not None else {},
        "config_options": window.options if subentry is not None else {},
        "settings": dict(coordinator.options) if coordinator is not None else None,
        "settings_provenance": (
            coordinator.provenance if coordinator is not None else None
        ),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return the house's diagnostics.

    Its data and options, and each window subentry's diagnostics under
    ``windows`` (by window key); ``settings`` is None for the house.
    """
    return {
        "title": "Adaptive Cover Configuration",
        "type": "config_entry",
        "identifier": config_entry.entry_id,
        "config_data": dict(config_entry.data),
        "config_options": dict(config_entry.options),
        "settings": None,
        "settings_provenance": None,
        "windows": {
            window.window_key: window_diagnostics(hass, window)
            for window in subentry_windows(hass, config_entry)
        },
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return a window device's diagnostics (the house device: the house)."""
    keys = {value for domain, value in device.identifiers if domain == DOMAIN}
    for window in subentry_windows(hass, config_entry):
        if window.window_key in keys:
            return window_diagnostics(hass, window)
    return await async_get_config_entry_diagnostics(hass, config_entry)
