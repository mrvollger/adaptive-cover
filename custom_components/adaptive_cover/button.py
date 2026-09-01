"""Button platform for the Adaptive Cover integration."""

from __future__ import annotations

import asyncio
import datetime as dt

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import _LOGGER, CONF_ENTITIES, DOMAIN
from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info


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
    coordinator: AdaptiveDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    reset_manual = AdaptiveCoverButton(
        config_entry,
        config_entry.entry_id,
        "Reset Manual Override",
        coordinator,
        display_name="Return to Auto",
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
        display_name: str | None = None,
    ) -> None:
        """Initialize the button.

        button_name is baked into the unique_id and must never change for
        existing entities; display_name is what the user sees and is free
        to evolve (pressing this button moves covers back to the adaptive
        position, so the label must say "resume", not "reset").
        """
        super().__init__(coordinator=coordinator)
        self._name = config_entry.data["name"]
        self._attr_unique_id = f"{unique_id}_{button_name}"
        self._device_id = unique_id
        self._button_name = button_name
        self._display_name = display_name or button_name
        self._entities = config_entry.options.get(CONF_ENTITIES, [])
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @property
    def name(self):
        """Name of the entity."""
        return self._display_name

    async def async_press(self) -> None:
        """Handle the button press."""
        coordinator = self.coordinator
        for entity in self._entities:
            if coordinator.manager.is_cover_manual(entity):
                _LOGGER.debug("Resetting manual override for: %s", entity)
                await coordinator.async_set_position(entity, coordinator.state)
                # Wait for the cover to report arrival, but never past the
                # coordinator's travel-time bound: a jammed motor or a
                # dropped position report must not stall the reset of this
                # cover (or the ones after it) forever.
                while coordinator.wait_for_target.get(entity):
                    sent_at = coordinator.target_call_time.get(entity)
                    if (
                        sent_at is None
                        or dt.datetime.now(dt.UTC) - sent_at
                        > coordinator.TARGET_TIMEOUT
                    ):
                        _LOGGER.warning(
                            "%s never confirmed reaching its target; "
                            "clearing wait and resetting override anyway",
                            entity,
                        )
                        coordinator.wait_for_target[entity] = False
                        break
                    await asyncio.sleep(1)
                coordinator.manager.reset(entity)
            else:
                _LOGGER.debug(
                    "Resetting manual override for %s is not needed since it is already auto-controlled",
                    entity,
                )
        await self.coordinator.async_refresh()
