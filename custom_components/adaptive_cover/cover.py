"""Cover platform: only the hub's aggregate cover lives here."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hub import AllShadesCover, is_hub_entry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the aggregate cover for the hub entry."""
    if is_hub_entry(config_entry):
        async_add_entities([AllShadesCover(hass)])
