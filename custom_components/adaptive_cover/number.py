"""Number platform: the house's numbers on the hub device (P5 flip).

The seven per-window live tunables are gone: the thresholds, the eye
height, the seat distance and the privacy delay are house settings here
(``house_settings.py``; floors, rooms and windows can still set their own
through ``set_profile`` and the options form), and the overhang is window
geometry (the options form, Reconfigure). A window's old number rows are
removed at its setup (``entity_surface.async_remove_window_numbers``).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the hub's house numbers (windows have none)."""
    from .hub import hub_device_info, is_hub_entry

    if not is_hub_entry(config_entry):
        return
    from .house_settings import house_numbers

    async_add_entities(house_numbers(hass, hub_device_info()))
