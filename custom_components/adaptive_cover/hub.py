"""The "Adaptive Cover All" hub: one device driving every entry.

A singleton config entry (data.is_hub) auto-created on first regular-entry
setup. Its entities fan out over all loaded coordinators:

- cover.adaptive_cover_all: aggregate cover (avg of non-tilt positions;
  open/close/set all - marks each cover manually controlled, so adaptive
  ticks do not walk the command back)
- select "Cover control mode": Manual / Adaptive / Mixed(display-only);
  Adaptive respects existing manual overrides
- button "Reset all manual overrides"

Clean re-implementation of the upstream "All Blinds" concept (no dead
pipeline, no hardcoded language, typed access to coordinators).
"""

from __future__ import annotations

import datetime as dt
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

HUB_ENTRY_NAME = "Adaptive Cover All"
HUB_UNIQUE_ID = "adaptive_cover_hub"
CONF_IS_HUB = "is_hub"

MODE_MANUAL = "Manual"
MODE_ADAPTIVE = "Adaptive"
MODE_MIXED = "Mixed"


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
    """Aggregate cover over every entry's covers.

    Polls: it has no coordinator, the underlying covers move at any time,
    and at boot the hub can load before the regular entries register -
    without polling the state would freeze at 'unknown / 0 covers'.
    """

    _attr_has_entity_name = True
    _attr_should_poll = True
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
        """Return position covers only.

        Tilt entries report slat angle; averaging a slat angle with a
        roller height is a unit crime.
        """
        return [
            (coordinator, entity)
            for coordinator in iter_coordinators(self.hass)
            if getattr(coordinator, "_cover_type", None) != "cover_tilt"
            for entity in getattr(coordinator, "entities", [])
        ]

    def _positions(self) -> list[int]:
        return [
            position
            for _, entity in self._all_cover_entities()
            if (position := get_safe_attr(self.hass, entity, "current_position"))
            is not None
        ]

    @property
    def current_cover_position(self) -> int | None:
        """Average actual position across all non-tilt covers."""
        positions = self._positions()
        if not positions:
            return None
        return round(sum(positions) / len(positions))

    @property
    def is_closed(self) -> bool | None:
        """Closed when every cover is fully closed."""
        positions = self._positions()
        if not positions:
            return None
        return all(position == 0 for position in positions)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Count summary: more honest than one average number."""
        positions = self._positions()
        return {
            "covers": len(positions),
            "open": sum(1 for p in positions if p >= 99),
            "partial": sum(1 for p in positions if 0 < p < 99),
            "closed": sum(1 for p in positions if p == 0),
            "note": "position is the average of all non-tilt covers",
        }

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Send one position to every cover.

        A whole-house gesture is the most deliberate manual act there is:
        each cover is marked manually controlled so the next adaptive tick
        does not silently walk the command back. Undo via the reset-all
        button or per-entry reset.
        """
        position = round(kwargs["position"])
        now = dt.datetime.now(dt.UTC)
        for coordinator, entity in self._all_cover_entities():
            await coordinator.async_set_manual_position(
                entity, position, source="all_covers", reason="whole-house gesture"
            )
            coordinator.manager.mark_manual_control(entity)
            coordinator.manager.manual_control_time[entity] = now
        if self.entity_id:  # skip when not added to hass (bare instance)
            self.async_write_ha_state()

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
    _attr_options = [MODE_MANUAL, MODE_ADAPTIVE, MODE_MIXED]

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the house mode select."""
        self.hass = hass
        self._attr_unique_id = f"{HUB_UNIQUE_ID}_house_mode"
        self._attr_device_info = hub_device_info()

    @property
    def name(self):
        """Name of the entity."""
        return "Cover control mode"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """State the override contract where users will look for it."""
        return {
            "note": (
                "Adaptive resumes control only for covers without an "
                "active manual override"
            )
        }

    @property
    def current_option(self) -> str | None:
        """Manual/Adaptive when unanimous, Mixed otherwise."""
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
        return MODE_MIXED

    async def async_select_option(self, option: str) -> None:
        """Flip every entry's Toggle Control switch."""
        if option == MODE_MIXED:
            return  # display-only state
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
        """Reset overrides everywhere and re-apply positions immediately.

        A button press is a manual command: recovery must not dribble in
        through the per-cover time throttle.
        """
        for coordinator in iter_coordinators(self.hass):
            for entity in list(coordinator.manager.manual_controlled):
                coordinator.manager.reset(entity)
            await coordinator.async_refresh()
            await coordinator.async_force_apply(
                source="reset_all", reason="manual overrides reset"
            )
