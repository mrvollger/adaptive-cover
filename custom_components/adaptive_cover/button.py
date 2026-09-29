"""Button platform for the Adaptive Cover integration."""

from __future__ import annotations


from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import _LOGGER, CONF_ENTITIES
from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info
from .entity_surface import apply_surface, window_surface


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform (regular entry or hub)."""
    from .hub import ResetAllOverridesButton, is_hub_entry

    if is_hub_entry(config_entry):
        async_add_entities([ResetAllOverridesButton(hass)])
        return
    coordinator: AdaptiveDataUpdateCoordinator = config_entry.runtime_data

    reset_manual = AdaptiveCoverButton(
        config_entry,
        config_entry.entry_id,
        "Reset Manual Override",
        coordinator,
    )

    buttons = []

    entities = config_entry.options.get(CONF_ENTITIES, [])
    if len(entities) >= 1:
        buttons = [reset_manual]

    async_add_entities(buttons)


class AdaptiveCoverButton(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], ButtonEntity
):
    """Representation of a adaptive cover button."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:cog-refresh-outline"

    def __init__(
        self,
        config_entry,
        unique_id: str,
        button_name: str,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize the button.

        button_name is baked into the unique_id and must never change for
        existing entities. The name the user sees comes from the
        translation key ("Return to auto": pressing this button moves
        covers back to the adaptive position, so it must not say "reset").
        """
        super().__init__(coordinator=coordinator)
        self._name = config_entry.data["name"]
        self._attr_unique_id = f"{unique_id}_{button_name}"
        apply_surface(self, window_surface("button", button_name))
        self._device_id = unique_id
        self._button_name = button_name
        self._entities = config_entry.options.get(CONF_ENTITIES, [])
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    async def async_press(self) -> None:
        """Handle the button press: the window's Mode becomes auto.

        A hold ends: each held cover is sent the adaptive position and its
        override cleared at once (the press does not wait for the cover to
        land; its travel is ours, so the landing is never read as a manual
        move). A window that was off comes back on (runtime/mode.py).
        """
        _LOGGER.debug("Return to auto: %s", self._entities)
        await self.coordinator.modes.auto()
