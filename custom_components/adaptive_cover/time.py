"""Time platform: the house's times of day on the hub device (P5 flip).

The end time and the quiet hours' start and end (``house_settings.py``);
windows have no time entities.
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
    """Set up the hub's house times (windows have none)."""
    from .hub import hub_device_info, is_hub_entry

    if not is_hub_entry(config_entry):
        return
    from .house_settings import house_times

    async_add_entities(house_times(hass, hub_device_info()))
