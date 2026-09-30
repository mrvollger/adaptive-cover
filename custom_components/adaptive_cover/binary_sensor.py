"""Binary Sensor platform for the Adaptive Cover integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info, override_until
from .entity_surface import apply_surface, window_surface
from .windows import WindowEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the house's windows' binary sensors."""
    from .house import async_setup_house_platform

    await async_setup_house_platform(
        hass, config_entry, Platform.BINARY_SENSOR, window_entities
    )


def window_entities(
    hass: HomeAssistant,
    config_entry: WindowEntry,
    coordinator: AdaptiveDataUpdateCoordinator,
) -> list[Entity]:
    """Return one window's binary sensors."""
    binary_sensor = AdaptiveCoverBinarySensor(
        config_entry,
        config_entry.entry_id,
        "Sun Infront",
        False,
        "sun_motion",
        BinarySensorDeviceClass.MOTION,
        coordinator,
    )
    manual_override = AdaptiveCoverBinarySensor(
        config_entry,
        config_entry.entry_id,
        "Manual Override",
        False,
        "manual_override",
        BinarySensorDeviceClass.RUNNING,
        coordinator,
    )
    return [binary_sensor, manual_override]


class AdaptiveCoverBinarySensor(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], BinarySensorEntity
):
    """representation of a Adaptive Cover binary sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        config_entry: WindowEntry,
        unique_id: str,
        binary_name: str,
        state: bool,
        key: str,
        device_class: BinarySensorDeviceClass,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator=coordinator)
        self._key = key
        self._config_entry = config_entry
        self._name = config_entry.name
        self._binary_name = binary_name
        self._attr_unique_id = f"{unique_id}_{binary_name}"
        apply_surface(self, window_surface("binary_sensor", binary_name))
        self._device_id = unique_id
        self._state = state
        self._attr_device_class = device_class
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.coordinator.data.states[self._key]

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:  # noqa: D102
        if self._key == "manual_override":
            covers = self._config_entry.covers
            until = override_until(self.coordinator, covers)
            return {
                "manual_controlled": self.coordinator.data.states["manual_list"],
                "until": dt_util.as_local(until).isoformat() if until else None,
            }
