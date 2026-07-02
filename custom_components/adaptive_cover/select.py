"""Select platform: one legible mode control instead of a pile of toggles.

Modes (persona-reviewed wording):
- "Manual"         - automation off; the shades stay wherever they are
- "Sun tracking"   - basic solar-geometry positioning
- "Sun + climate"  - adds temperature/presence/weather logic

The select drives the existing Toggle Control / Climate Mode switches via
their services, so the switches (kept for compatibility and existing
automations) always stay in sync.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CLIMATE_MODE, DOMAIN
from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info

MODE_MANUAL = "Manual"
MODE_SUN = "Sun tracking"
MODE_CLIMATE = "Sun + climate"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the mode select for one config entry."""
    coordinator: AdaptiveDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    async_add_entities([AdaptiveCoverModeSelect(config_entry, coordinator)])


class AdaptiveCoverModeSelect(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], SelectEntity
):
    """Single mode control mirroring the control/climate switches."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:sun-compass"

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize the mode select."""
        super().__init__(coordinator=coordinator)
        self._config_entry = config_entry
        self._has_climate = bool(config_entry.options.get(CONF_CLIMATE_MODE))
        self._attr_options = (
            [MODE_MANUAL, MODE_SUN, MODE_CLIMATE]
            if self._has_climate
            else [MODE_MANUAL, MODE_SUN]
        )
        self._name = config_entry.data["name"]
        self._attr_unique_id = f"{config_entry.entry_id}_mode_select"
        self._device_id = config_entry.entry_id
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @property
    def name(self):
        """Name of the entity."""
        return "Mode"

    @property
    def current_option(self) -> str:
        """Derive the mode from the coordinator's toggles."""
        if not self.coordinator.control_toggle:
            return MODE_MANUAL
        if self._has_climate and self.coordinator.switch_mode:
            return MODE_CLIMATE
        return MODE_SUN

    def _switch_entity_id(self, switch_name: str) -> str | None:
        registry = er.async_get(self.hass)
        return registry.async_get_entity_id(
            "switch", DOMAIN, f"{self._device_id}_{switch_name}"
        )

    async def _set_switch(self, switch_name: str, on: bool) -> None:
        entity_id = self._switch_entity_id(switch_name)
        if entity_id is None:
            return
        await self.hass.services.async_call(
            "switch",
            "turn_on" if on else "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def async_select_option(self, option: str) -> None:
        """Apply the mode by driving the underlying switches."""
        if option == MODE_MANUAL:
            await self._set_switch("Toggle Control", False)
        else:
            if self._has_climate:
                await self._set_switch("Climate Mode", option == MODE_CLIMATE)
            await self._set_switch("Toggle Control", True)
        self.async_write_ha_state()
