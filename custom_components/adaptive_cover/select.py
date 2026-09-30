"""Select platform: the window's Mode, ``auto`` / ``hold`` / ``off`` (P5 flip).

- ``auto``: the window follows the sun (and climate, where the house or
  the room has it on).
- ``hold``: a manual override with an expiry. A detected manual move sets
  it for the override duration; picking it holds the covers where they
  are for that duration. The ``adaptive_cover.hold`` entity service holds
  for a given duration, optionally after commanding a position, and can
  target areas and floors.
- ``off``: no moves and no manual-move detection.

The select is the source of truth for the window's control state: it
restores its own state (a hold with its end, the ``until`` attribute;
runtime/mode.py ``restored_mode``). The options are translation keys;
``strings.json`` names them.

The hub's house select lives in hub.py and shares this platform.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info
from .entity_surface import apply_surface, window_surface
from .runtime.mode import MODE_OPTIONS, Mode, restored_mode
from .windows import WindowEntry

ATTR_UNTIL = "until"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the house's Mode select and each window's."""
    from .house import async_setup_house_platform
    from .hub import HouseModeSelect

    async_add_entities([HouseModeSelect(hass)])
    await async_setup_house_platform(
        hass, config_entry, Platform.SELECT, window_entities
    )


def window_entities(
    hass: HomeAssistant,
    config_entry: WindowEntry,
    coordinator: AdaptiveDataUpdateCoordinator,
) -> list[Entity]:
    """Return one window's Mode select."""
    return [AdaptiveCoverModeSelect(config_entry, coordinator)]


def _parse_until(value: Any) -> dt.datetime | None:
    """Parse a stored ``until`` attribute (ISO, local) to aware UTC."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None or parsed.tzinfo is None:
        return None
    return dt_util.as_utc(parsed)


def iso_local(value: dt.datetime | None) -> str | None:
    """Local-time ISO string, or None."""
    return dt_util.as_local(value).isoformat() if value is not None else None


class AdaptiveCoverModeSelect(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], SelectEntity, RestoreEntity
):
    """The window's Mode: auto / hold / off."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:sun-compass"
    _attr_options = MODE_OPTIONS

    def __init__(
        self,
        config_entry: WindowEntry,
        coordinator: AdaptiveDataUpdateCoordinator,
    ) -> None:
        """Initialize the mode select."""
        super().__init__(coordinator=coordinator)
        self._config_entry = config_entry
        self._name = config_entry.name
        self._attr_unique_id = f"{config_entry.entry_id}_mode_select"
        apply_surface(self, window_surface("select", "mode_select"))
        self._device_id = config_entry.entry_id
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @property
    def current_option(self) -> str | None:
        """The window's Mode (unknown until it is restored)."""
        mode = self.coordinator.modes.mode
        return mode.value if mode is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """``until``: when the hold ends (local ISO time); None unless held."""
        modes = self.coordinator.modes
        until = modes.until if modes.mode is Mode.HOLD else None
        return {ATTR_UNTIL: iso_local(until)}

    async def async_added_to_hass(self) -> None:
        """Restore the Mode (auto when there is nothing to restore)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        restored = restored_mode(
            last.state if last is not None else None,
            _parse_until(last.attributes.get(ATTR_UNTIL)) if last is not None else None,
            self.coordinator.clock.utcnow(),
        )
        self.coordinator.logger.debug("Mode restores as %s", restored)
        await self.coordinator.modes.restore(restored)

    async def async_select_option(self, option: str) -> None:
        """Apply the picked Mode."""
        await self.coordinator.modes.select(Mode(option))
        self.async_write_ha_state()

    async def async_hold(
        self, duration: dt.timedelta | None = None, position: int | None = None
    ) -> None:
        """``adaptive_cover.hold``: hold (after moving to ``position``)."""
        await self.coordinator.modes.hold(duration, position)
        self.async_write_ha_state()
