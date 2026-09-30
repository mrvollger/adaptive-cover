"""Shared entity helpers for the Adaptive Cover integration."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .windows import WindowEntry

if TYPE_CHECKING:
    from .coordinator import AdaptiveDataUpdateCoordinator


def adaptive_cover_device_info(window: WindowEntry) -> DeviceInfo:
    """Return the shared device info for all entities of one window.

    One service device per window (identifier: the window key), named
    after the window, so entities render as "<window name> <role>". A
    window subentry's device hangs off the house device (``via_device_id``).
    """
    info = DeviceInfo(
        identifiers={(DOMAIN, window.window_key)},
        name=window.name,
        entry_type=DeviceEntryType.SERVICE,
    )
    if window.via_device_id is not None:
        info["via_device_id"] = window.via_device_id
    return info


def _local_iso(value: dt.datetime | None) -> str | None:
    """Local-time ISO string, or None."""
    return dt_util.as_local(value).isoformat() if value is not None else None


def override_until(
    coordinator: AdaptiveDataUpdateCoordinator, covers: list[str]
) -> dt.datetime | None:
    """When the entry's manual override ends, or None if no cover is held.

    Uses the same rule as the override expiry itself
    (``OverrideTracker.expires_at``: latch time + override duration, or a
    requested hold's own end). With several covers it is the latest
    expiry. The day rollover at local midnight can end a detected override
    earlier.
    """
    manager = coordinator.manager
    expiries = [
        expiry for cover in covers if (expiry := manager.expires_at(cover)) is not None
    ]
    return max(expiries, default=None)


def window_attributes(
    config_entry: WindowEntry, coordinator: AdaptiveDataUpdateCoordinator
) -> dict[str, Any]:
    """Identity and schedule attributes for the Position sensor (P1).

    - window_key: the window key (the card binding key): a migrated
      window's old entry_id, a new window's subentry_id (windows.py).
    - cover_entity: the cover this window drives (None without one).
    - cover_type: cover_blind / cover_awning / cover_tilt.
    - override_until: local ISO time the manual override ends, or None.
    - next_move: {time, position} from the next-change computation, or None.
    - provenance (P5): where the window's settings come from, for the
      options that do not come from the house or the spec default and are
      not one-time window settings ({option: "area" | "floor" | "window" |
      "legacy"}; layers.py).
    """
    covers = config_entry.covers
    states = coordinator.data.states
    next_time = states.get("next_change_time")
    next_position = states.get("next_change_position")
    attributes: dict[str, Any] = {
        "window_key": config_entry.entry_id,
        "cover_entity": covers[0] if covers else None,
        "cover_type": config_entry.cover_type,
        "override_until": _local_iso(override_until(coordinator, covers)),
        "next_move": {
            "time": _local_iso(next_time),
            "position": int(next_position) if next_position is not None else None,
        }
        if next_time is not None
        else None,
        "provenance": coordinator.provenance,
    }
    return attributes
