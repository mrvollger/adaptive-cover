"""The "All Shades" hub: one device that drives every Adaptive Cover entry.

A singleton config entry (data.is_hub) auto-created on first regular-entry
setup. Its entities fan out over all loaded coordinators:

- cover.all_shades: aggregate cover (average position; open/close/set all)
- select "House mode": Manual / Adaptive across every entry
- button "Reset all manual overrides"

Clean re-implementation of the upstream "All Blinds" concept (no dead
pipeline, no hardcoded language, typed access to coordinators).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN
from .coordinator import AdaptiveDataUpdateCoordinator
from .helpers import get_safe_attr

HUB_ENTRY_NAME = "All Shades"
HUB_UNIQUE_ID = "adaptive_cover_hub"
CONF_IS_HUB = "is_hub"

MODE_MANUAL = "Manual"
MODE_ADAPTIVE = "Adaptive"


def is_hub_entry(entry) -> bool:
    """Check whether a config entry is the singleton hub."""
    return bool(entry.data.get(CONF_IS_HUB))


def iter_coordinators(hass: HomeAssistant) -> list[AdaptiveDataUpdateCoordinator]:
    """All loaded regular-entry coordinators."""
    return [
        coordinator
        for coordinator in hass.data.get(DOMAIN, {}).values()
        if isinstance(coordinator, AdaptiveDataUpdateCoordinator)
    ]


def hub_device_info() -> DeviceInfo:
    """Shared device for all hub entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, HUB_UNIQUE_ID)},
        name=HUB_ENTRY_NAME,
        entry_type=DeviceEntryType.SERVICE,
    )


class AllShadesCover(CoverEntity):
    """Aggregate cover over every entry's covers."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = None  # main feature: takes the device name
    _attr_device_class = CoverDeviceClass.SHADE
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the aggregate cover."""
        self.hass = hass
        self._attr_unique_id = f"{HUB_UNIQUE_ID}_cover"
        self._attr_device_info = hub_device_info()

    def _all_cover_entities(self) -> list[tuple[AdaptiveDataUpdateCoordinator, str]]:
        return [
            (coordinator, entity)
            for coordinator in iter_coordinators(self.hass)
            for entity in getattr(coordinator, "entities", [])
        ]

    @property
    def current_cover_position(self) -> int | None:
        """Average actual position across all covers."""
        positions = [
            position
            for _, entity in self._all_cover_entities()
            if (position := get_safe_attr(self.hass, entity, "current_position"))
            is not None
        ]
        if not positions:
            return None
        return round(sum(positions) / len(positions))

    @property
    def is_closed(self) -> bool | None:
        """Closed when every cover is fully closed."""
        position = self.current_cover_position
        if position is None:
            return None
        return position == 0

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Send one position to every cover (integration-initiated)."""
        position = round(kwargs["position"])
        for coordinator, entity in self._all_cover_entities():
            await coordinator.async_set_manual_position(entity, position)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open all covers."""
        await self.async_set_cover_position(position=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close all covers."""
        await self.async_set_cover_position(position=0)


class HouseModeSelect(SelectEntity):
    """Manual / Adaptive for the whole house, via each entry's switches.

    Polls: it has no coordinator, and the underlying per-entry toggles
    can change at any time.
    """

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_icon = "mdi:home-automation"
    _attr_options = [MODE_MANUAL, MODE_ADAPTIVE]

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the house mode select."""
        self.hass = hass
        self._attr_unique_id = f"{HUB_UNIQUE_ID}_house_mode"
        self._attr_device_info = hub_device_info()

    @property
    def name(self):
        """Name of the entity."""
        return "House mode"

    @property
    def current_option(self) -> str | None:
        """Manual/Adaptive when unanimous, unknown when mixed."""
        toggles = [
            bool(coordinator.control_toggle)
            for coordinator in iter_coordinators(self.hass)
        ]
        if not toggles:
            return None
        if all(toggles):
            return MODE_ADAPTIVE
        if not any(toggles):
            return MODE_MANUAL
        return None

    async def async_select_option(self, option: str) -> None:
        """Flip every entry's Toggle Control switch."""
        registry = er.async_get(self.hass)
        turn_on = option == MODE_ADAPTIVE
        for entry_id in list(self.hass.data.get(DOMAIN, {})):
            coordinator = self.hass.data[DOMAIN].get(entry_id)
            if not isinstance(coordinator, AdaptiveDataUpdateCoordinator):
                continue
            switch_id = registry.async_get_entity_id(
                "switch", DOMAIN, f"{entry_id}_Toggle Control"
            )
            if switch_id:
                await self.hass.services.async_call(
                    "switch",
                    "turn_on" if turn_on else "turn_off",
                    {"entity_id": switch_id},
                    blocking=True,
                )
        self.async_write_ha_state()


class ResetAllOverridesButton(ButtonEntity):
    """Clear manual override on every cover of every entry."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:restore"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reset-all button."""
        self.hass = hass
        self._attr_unique_id = f"{HUB_UNIQUE_ID}_reset_all"
        self._attr_device_info = hub_device_info()

    @property
    def name(self):
        """Name of the entity."""
        return "Reset all manual overrides"

    async def async_press(self) -> None:
        """Reset overrides everywhere and refresh."""
        for coordinator in iter_coordinators(self.hass):
            for entity in list(coordinator.manager.manual_controlled):
                coordinator.manager.reset(entity)
            await coordinator.async_refresh()
