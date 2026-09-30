"""Adaptive Cover integration diagnostics.

A window entry's download is its window. The house entry's download is
the house plus every window subentry (P7); a window device's download is
that one window, wherever it is stored.
"""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN
from .windows import WindowEntry, as_window, subentry_windows


def window_diagnostics(hass: HomeAssistant, window: WindowEntry) -> dict[str, Any]:
    """Return one window's diagnostics.

    ``settings`` is what a loaded window acts on (P5 flip: its resolved
    layered settings) and ``settings_provenance`` the options that come
    from an area, a floor or the window itself; both None for a window
    that is not loaded.
    """
    from .coordinator import AdaptiveDataUpdateCoordinator

    coordinator = hass.data.get(DOMAIN, {}).get(window.window_key)
    loaded = isinstance(coordinator, AdaptiveDataUpdateCoordinator)
    return {
        "title": "Adaptive Cover Configuration",
        "type": "config_subentry" if window.is_subentry else "config_entry",
        "identifier": window.window_key,
        "config_data": dict(window.data),
        "config_options": dict(window.options),
        "settings": dict(coordinator.options) if loaded else None,
        "settings_provenance": coordinator.provenance if loaded else None,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return config entry diagnostics.

    A window entry: its window (``window_diagnostics``). The house entry:
    its data and options, and each window subentry's diagnostics under
    ``windows`` (by window key); ``settings`` is None for the house.
    """
    from .hub import is_hub_entry

    if not is_hub_entry(config_entry):
        return window_diagnostics(hass, as_window(config_entry))
    return {
        "title": "Adaptive Cover Configuration",
        "type": "config_entry",
        "identifier": config_entry.entry_id,
        "config_data": config_entry.data,
        "config_options": config_entry.options,
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
    for window in [as_window(config_entry), *subentry_windows(hass, config_entry)]:
        if window.window_key in keys and not _is_house(config_entry, window):
            return window_diagnostics(hass, window)
    return await async_get_config_entry_diagnostics(hass, config_entry)


def _is_house(config_entry: ConfigEntry, window: WindowEntry) -> bool:
    from .hub import is_hub_entry

    return is_hub_entry(config_entry) and not window.is_subentry
