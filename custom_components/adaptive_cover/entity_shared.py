"""Shared entity helpers for the Adaptive Cover integration."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import dt as dt_util

from .const import CONF_ENTITIES, CONF_SENSOR_TYPE, DOMAIN

if TYPE_CHECKING:
    from .coordinator import AdaptiveDataUpdateCoordinator


def adaptive_cover_device_info(config_entry: ConfigEntry) -> DeviceInfo:
    """Return the shared device info for all entities of a config entry.

    One service device per config entry, named after the user's entry name,
    so entities render as "<entry name> <role>".
    """
    return DeviceInfo(
        identifiers={(DOMAIN, config_entry.entry_id)},
        name=config_entry.data["name"],
        entry_type=DeviceEntryType.SERVICE,
    )


def _local_iso(value: dt.datetime | None) -> str | None:
    """Local-time ISO string, or None."""
    return dt_util.as_local(value).isoformat() if value is not None else None


def override_until(
    coordinator: AdaptiveDataUpdateCoordinator, covers: list[str]
) -> dt.datetime | None:
    """When the entry's manual override ends, or None if no cover is held.

    Uses the same rule as the override expiry itself (latch time + override
    duration). With several covers it is the latest expiry. The day
    rollover at local midnight can end an override earlier.
    """
    manager = coordinator.manager
    expiries = [
        latched_at + manager.reset_duration
        for cover in covers
        if manager.is_cover_manual(cover)
        and (latched_at := manager.manual_control_time.get(cover)) is not None
    ]
    return max(expiries, default=None)


def window_attributes(
    config_entry: ConfigEntry, coordinator: AdaptiveDataUpdateCoordinator
) -> dict[str, Any]:
    """Identity and schedule attributes for the Position sensor (P1).

    - window_key: the entry_id (the card binding key; stays valid when the
      entry later becomes a window subentry).
    - cover_entity: the cover this window drives. An entry with several
      covers also gets cover_entities (the full list); cover_entity is the
      first.
    - cover_type: cover_blind / cover_awning / cover_tilt.
    - override_until: local ISO time the manual override ends, or None.
    - next_move: {time, position} from the next-change computation, or None.
    - provenance (P5 shadow): where the layered settings take each option
      from, for the options that do not come from the house or the spec
      default and are not one-time window settings ({option: "area" |
      "floor" | "window" | "legacy"}); None until the house is lifted
      (shadow.py).
    """
    from .shadow import provenance

    covers = list(config_entry.options.get(CONF_ENTITIES) or [])
    states = coordinator.data.states
    next_time = states.get("next_change_time")
    next_position = states.get("next_change_position")
    attributes: dict[str, Any] = {
        "window_key": config_entry.entry_id,
        "cover_entity": covers[0] if covers else None,
        "cover_type": config_entry.data.get(CONF_SENSOR_TYPE),
        "override_until": _local_iso(override_until(coordinator, covers)),
        "next_move": {
            "time": _local_iso(next_time),
            "position": int(next_position) if next_position is not None else None,
        }
        if next_time is not None
        else None,
        "provenance": provenance(coordinator.hass, config_entry.entry_id),
    }
    if len(covers) > 1:
        attributes["cover_entities"] = covers
    return attributes
