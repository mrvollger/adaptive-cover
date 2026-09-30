"""Switch platform: the house's toggles on the hub device.

Climate, manual-move detection and the outside-temperature, lux and
irradiance use-flags (``house_settings.py``). Windows have no switches:
their six switch aliases (hidden since the P5 flip) are gone since v2.1,
and migration 3.1 removes their registry rows (``upgrade.py``). A window's
control state is its Mode select; the toggles are house settings that a
room (and for some, a window) may override.
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
    """Set up the house's switches."""
    from .hub import hub_device_info
    from .house_settings import house_switches

    async_add_entities(house_switches(hass, hub_device_info()))
