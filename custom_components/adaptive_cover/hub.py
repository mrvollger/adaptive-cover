"""The "Adaptive Cover All" hub: one device driving every entry.

A singleton config entry (data.is_hub) auto-created on first regular-entry
setup. Its entities fan out over all loaded coordinators:

- cover.adaptive_cover_all: aggregate cover (avg of non-tilt positions;
  open/close/set all - marks each cover manually controlled, so adaptive
  ticks do not walk the command back)
- select "Cover control mode": Auto / Hold / Off, and a display-only Mixed
  when the windows differ; picking one sets every window's Mode (P5 flip).
  The ``adaptive_cover.hold`` service on it holds every window
- button "Return all shades to auto" (unique_id keeps the reset_all slug)

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
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN
from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_surface import HUB_SURFACE, HUB_UNIQUE_ID, apply_surface
from .helpers import get_safe_attr
from .runtime.mode import MODE_OPTIONS, Mode

HUB_ENTRY_NAME = "Adaptive Cover All"
CONF_IS_HUB = "is_hub"

MODE_MIXED = "mixed"
"""The house select's display-only option: the windows' Modes differ."""


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
        apply_surface(self, HUB_SURFACE[("cover", "cover")])
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
        targets = self._all_cover_entities()
        if targets:
            # One latch time for the whole gesture, read before any command.
            now = targets[0][0].clock.utcnow()
            for coordinator, entity in targets:
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
    """Auto / Hold / Off for the whole house: sets every window's Mode.

    Polls: it has no coordinator, and the windows' Modes can change at any
    time. The options are translation keys (``strings.json``).
    """

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_icon = "mdi:home-automation"
    _attr_options = [*MODE_OPTIONS, MODE_MIXED]

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the house mode select."""
        self.hass = hass
        self._attr_unique_id = f"{HUB_UNIQUE_ID}_house_mode"
        apply_surface(self, HUB_SURFACE[("select", "house_mode")])
        self._attr_device_info = hub_device_info()

    @property
    def current_option(self) -> str | None:
        """The windows' Mode when they agree, Mixed otherwise."""
        modes = {
            mode
            for coordinator in iter_coordinators(self.hass)
            if (mode := coordinator.modes.mode) is not None
        }
        if not modes:
            return None
        if len(modes) == 1:
            return next(iter(modes)).value
        return MODE_MIXED

    async def async_select_option(self, option: str) -> None:
        """Set every window's Mode (Mixed is display-only)."""
        if option == MODE_MIXED:
            return
        mode = Mode(option)
        for coordinator in iter_coordinators(self.hass):
            await coordinator.modes.select(mode)
        self.async_write_ha_state()

    async def async_hold(
        self, duration: dt.timedelta | None = None, position: int | None = None
    ) -> None:
        """``adaptive_cover.hold`` on the house: hold every window."""
        for coordinator in iter_coordinators(self.hass):
            await coordinator.modes.hold(duration, position)
        self.async_write_ha_state()


class ResetAllOverridesButton(ButtonEntity):
    """Clear manual override on every cover of every entry."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:restore"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reset-all button."""
        self.hass = hass
        # Pressing this moves covers back to their adaptive positions, so
        # the label (translation key) says "return", not "reset"; the
        # unique_id keeps the old reset_all slug.
        self._attr_unique_id = f"{HUB_UNIQUE_ID}_reset_all"
        apply_surface(self, HUB_SURFACE[("button", "reset_all")])
        self._attr_device_info = hub_device_info()

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
