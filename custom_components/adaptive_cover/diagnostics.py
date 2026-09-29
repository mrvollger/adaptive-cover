"""Adaptive Cover integration diagnostics."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return config entry diagnostics.

    ``settings`` is what a loaded window acts on (P5 flip: its resolved
    layered settings) and ``settings_provenance`` the options that come
    from an area, a floor or the window itself; both None for the hub and
    for a window that is not loaded.
    """
    from .coordinator import AdaptiveDataUpdateCoordinator

    coordinator = getattr(config_entry, "runtime_data", None)
    loaded = isinstance(coordinator, AdaptiveDataUpdateCoordinator)
    return {
        "title": "Adaptive Cover Configuration",
        "type": "config_entry",
        "identifier": config_entry.entry_id,
        "config_data": config_entry.data,
        "config_options": config_entry.options,
        "settings": dict(coordinator.options) if loaded else None,
        "settings_provenance": coordinator.provenance if loaded else None,
    }
