"""Sensor platform for Adaptive Cover integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info, window_attributes
from .entity_surface import apply_surface, window_surface
from .windows import WindowEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the house's windows' sensors."""
    from .house import async_setup_house_platform

    await async_setup_house_platform(
        hass, config_entry, Platform.SENSOR, window_entities
    )


def window_entities(
    hass: HomeAssistant,
    config_entry: WindowEntry,
    coordinator: AdaptiveDataUpdateCoordinator,
) -> list[Entity]:
    """Return one window's sensors."""
    name = config_entry.name

    sensor = AdaptiveCoverSensorEntity(
        config_entry.entry_id, hass, config_entry, name, coordinator
    )
    start = AdaptiveCoverTimeSensorEntity(
        config_entry.entry_id,
        hass,
        config_entry,
        name,
        "Start Sun",
        "start",
        "mdi:sun-clock-outline",
        coordinator,
    )
    end = AdaptiveCoverTimeSensorEntity(
        config_entry.entry_id,
        hass,
        config_entry,
        name,
        "End Sun",
        "end",
        "mdi:sun-clock",
        coordinator,
    )
    control = AdaptiveCoverControlSensorEntity(
        config_entry.entry_id, hass, config_entry, name, coordinator
    )
    next_change = AdaptiveCoverNextChangeSensorEntity(
        config_entry.entry_id, hass, config_entry, name, coordinator
    )
    last_change = AdaptiveCoverLastChangeSensorEntity(
        config_entry.entry_id, hass, config_entry, name, coordinator
    )
    return [sensor, start, end, control, next_change, last_change]


class AdaptiveCoverSensorEntity(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], SensorEntity
):
    """Adaptive Cover Sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:sun-compass"
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        unique_id: str,
        hass,
        config_entry,
        name: str,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize adaptive_cover Sensor."""
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.data = self.coordinator.data
        self._sensor_name = "Cover Position"
        self._attr_unique_id = f"{unique_id}_{self._sensor_name}"
        apply_surface(self, window_surface("sensor", self._sensor_name))
        self.hass = hass
        self.config_entry = config_entry
        self._name = name
        self._device_id = unique_id
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.data = self.coordinator.data
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Handle when entity is added."""
        return self.data.states["state"]

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Coordinator attributes plus the window identity (additive)."""
        return {
            **self.data.attributes,
            **window_attributes(self.config_entry, self.coordinator),
        }


class AdaptiveCoverTimeSensorEntity(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], SensorEntity
):
    """Adaptive Cover Time Sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        unique_id: str,
        hass,
        config_entry,
        name: str,
        sensor_name: str,
        key: str,
        icon: str,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize adaptive_cover Sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_icon = icon
        self.key = key
        self.coordinator = coordinator
        self.data = self.coordinator.data
        self._attr_unique_id = f"{unique_id}_{sensor_name}"
        self._device_id = unique_id
        self.hass = hass
        self.config_entry = config_entry
        self._name = name
        self._cover_type = self.config_entry.cover_type
        self._sensor_name = sensor_name
        apply_surface(self, window_surface("sensor", sensor_name))
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.data = self.coordinator.data
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Handle when entity is added."""
        return self.data.states[self.key]


class AdaptiveCoverControlSensorEntity(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], SensorEntity
):
    """Adaptive Cover Control method Sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        unique_id: str,
        hass,
        config_entry,
        name: str,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize adaptive_cover Sensor."""
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.data = self.coordinator.data
        self._sensor_name = "Control Method"
        self._attr_unique_id = f"{unique_id}_{self._sensor_name}"
        apply_surface(self, window_surface("sensor", self._sensor_name))
        self._device_id = unique_id
        self.id = unique_id
        self.hass = hass
        self.config_entry = config_entry
        self._name = name
        self._cover_type = self.config_entry.cover_type
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.data = self.coordinator.data
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Handle when entity is added."""
        return self.data.states["control"]


class AdaptiveCoverNextChangeSensorEntity(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], SensorEntity
):
    """Sensor showing the next predicted cover state change."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:crystal-ball"

    def __init__(
        self,
        unique_id: str,
        hass,
        config_entry,
        name: str,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize adaptive_cover Next Change Sensor."""
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.data = self.coordinator.data
        self._sensor_name = "Next State Change"
        self._attr_unique_id = f"{unique_id}_{self._sensor_name}"
        apply_surface(self, window_surface("sensor", self._sensor_name))
        self._device_id = unique_id
        self.hass = hass
        self.config_entry = config_entry
        self._name = name
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.data = self.coordinator.data
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Return formatted string describing the next change."""
        event = self.data.states.get("next_change_event")
        time = self.data.states.get("next_change_time")
        pos = self.data.states.get("next_change_position")
        if event and time and pos is not None:
            local_time = dt_util.as_local(time)
            time_str = local_time.strftime("%H:%M")
            return f"{event} at {time_str} \u2192 {int(pos)}%"
        return "No changes expected"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return extra attributes."""
        time = self.data.states.get("next_change_time")
        local_time = dt_util.as_local(time) if time else None
        return {
            "event": self.data.states.get("next_change_event"),
            "expected_time": local_time.isoformat() if local_time else None,
            "expected_position": self.data.states.get("next_change_position"),
            "current_reason": self.data.states.get("state_reason"),
        }


class AdaptiveCoverLastChangeSensorEntity(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], SensorEntity
):
    """Sensor showing the last cover state change reason."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:history"

    def __init__(
        self,
        unique_id: str,
        hass,
        config_entry,
        name: str,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize adaptive_cover Last Change Sensor."""
        super().__init__(coordinator=coordinator)
        self.coordinator = coordinator
        self.data = self.coordinator.data
        self._sensor_name = "Last State Change"
        self._attr_unique_id = f"{unique_id}_{self._sensor_name}"
        apply_surface(self, window_surface("sensor", self._sensor_name))
        self._device_id = unique_id
        self.hass = hass
        self.config_entry = config_entry
        self._name = name
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.data = self.coordinator.data
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Return formatted string describing the last change."""
        old = self.data.states.get("last_change_old")
        new = self.data.states.get("last_change_new")
        reason = self.data.states.get("last_change_reason")
        if old is not None and new is not None:
            return f"{old}% \u2192 {new}%: {reason}"
        return "No changes recorded"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return extra attributes."""
        time = self.data.states.get("last_change_time")
        local_time = dt_util.as_local(time) if time else None
        return {
            "old_position": self.data.states.get("last_change_old"),
            "new_position": self.data.states.get("last_change_new"),
            "changed_at": local_time.isoformat() if local_time else None,
            "reason": self.data.states.get("last_change_reason"),
        }
