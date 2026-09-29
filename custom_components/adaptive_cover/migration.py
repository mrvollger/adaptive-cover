"""Config entry 1.2 -> 1.3: one cover per window, defaults written down.

Called from ``async_migrate_entry`` (``__init__.py``) for every window
entry (the hub only gets the version bump). The migration:

1. writes every option the entry reads through a code fallback into its
   options (``runtime/shade_config.absent_options``), BEFORE any default
   changes: a later change to a spec default (P5 house defaults) cannot
   move an existing window. A key stored as None stays None;
2. writes the cover as ``cover_entity_id`` next to ``group: [cover]``
   (``group`` stays, so a downgrade keeps working; removed in P8). An
   entry with several covers keeps them in ``group`` and gets a "split"
   repair issue at setup (``window_cover.async_check_split_issue``);
3. sets the entry's unique_id to the cover's entity-registry id, when the
   cover is registered and no other entry holds that id.

Nothing the runtime reads changes: ``ShadeConfig.from_options`` gives the
same result before and after (tests/test_migration_1_3.py checks this on
the live house snapshot).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import _LOGGER, DOMAIN
from .runtime.shade_config import absent_options
from .settings.normalize import normalize_cover, window_cover, window_covers
from .window_cover import cover_registry_id


def options_1_3(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return a window's options as migration 1.3 stores them (pure)."""
    return normalize_cover({**options, **absent_options(options)})


@dataclass(frozen=True)
class Migration13:
    """What migration 1.3 did to one entry."""

    written: dict[str, Any]
    """Option keys the entry did not store before, with their values."""
    changed: dict[str, Any]
    """Option keys the entry stored before and now stores differently."""
    unique_id: str | None
    """The unique_id set (None: left as it was)."""


def async_migrate_1_3(hass: HomeAssistant, entry: ConfigEntry) -> Migration13:
    """Migrate one window entry to 1.3 and bump its minor version."""
    before = dict(entry.options)
    options = options_1_3(before)
    written = {key: value for key, value in options.items() if key not in before}
    changed = {
        key: value
        for key, value in options.items()
        if key in before and before[key] != value
    }
    unique_id = _wanted_unique_id(hass, entry, window_cover(options))
    if unique_id == entry.unique_id:
        unique_id = None  # nothing to set
    update: dict[str, Any] = {"options": options, "minor_version": 3}
    if unique_id is not None:
        update["unique_id"] = unique_id
    hass.config_entries.async_update_entry(entry, **update)
    _LOGGER.info(
        "Migrated %s to 1.3: wrote %s option(s) %s, unique_id %s",
        entry.title,
        len(written),
        sorted(written),
        unique_id or "unchanged",
    )
    return Migration13(written=written, changed=changed, unique_id=unique_id)


def _wanted_unique_id(
    hass: HomeAssistant, entry: ConfigEntry, cover: str | None
) -> str | None:
    """Return the unique_id the window should have: its cover's registry id.

    None when the cover is not registered, or when another entry already
    holds that id (two windows on one cover: the first keeps it).
    """
    registry_id = cover_registry_id(hass, cover)
    if registry_id is None or registry_id == entry.unique_id:
        return registry_id
    holder = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, registry_id)
    if holder is not None:
        _LOGGER.warning(
            "%s and %s both drive %s; only %s keeps it as its unique_id",
            entry.title,
            holder.title,
            cover,
            holder.title,
        )
        return None
    return registry_id


def async_sync_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Keep a window's unique_id on its cover's registry id (at setup).

    The options form can move a window to another cover, and a downgraded
    version edits ``group`` only; the unique_id follows at the next setup.
    An entry with several covers is left alone (the split repair fixes it).
    """
    covers = window_covers(entry.options)
    if len(covers) > 1:
        return
    wanted = _wanted_unique_id(hass, entry, covers[0] if covers else None)
    if wanted != entry.unique_id:
        hass.config_entries.async_update_entry(entry, unique_id=wanted)
