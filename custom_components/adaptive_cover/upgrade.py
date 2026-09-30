"""Upgrading to v2.1 (P8): the house's migration 2.1 -> 3.1, and the nag.

Since v2.1 the house entry is the only config entry that runs; its
windows are its ``window`` subentries (ADR 0001, ADR 0007). v2.1 has
neither the window-entry runtime of 1.x nor the consolidation that moves
window entries into the house (v2.0.x has both).

**Needs consolidation.** A house that still has enabled window entries (a
1.x house, or a consolidation that stopped part way) cannot run on v2.1.
Every entry of such a house (the window entries and the house) fails to
set up with the ``consolidate_first`` message, and the ``consolidate_first``
repair issue says what to do: install v2.0.x, fix its "Consolidate the
house" repair, then update again. Nothing is written, so v2.0.x finds
every entry as it left it. Disabled window entries drive nothing and do
not count; one that is enabled again fails the same way.

**Migration 2.1 -> 3.1** (a consolidated house, ``async_migrate_house``):

1. a snapshot, written once, of what the migration changes:
   ``.storage/adaptive_cover.v2_0_snapshot`` (the house entry with its
   subentries, and the registry rows it removes). The rollback is the
   Home Assistant backup; the snapshot shows what was there;
2. every window subentry is rewritten to the 3.1 record
   (``settings/window_record.py``): its name, cover, cover type, one-time
   settings and overrides. The copies of the recurring settings, the
   ``group`` list and ``mode`` go: the window resolves them from the
   layers, so it acts on exactly what it acted on before;
3. the per-window switch aliases (hidden since the P5 flip) and any
   leftover window number rows are removed from the entity registry;
4. the house options keep only the layers (``house``, ``floors``,
   ``areas``, ``temperature_unit``): the hub's leftover geometry and its
   ``group``, which listed the hub's own cover, go;
5. the house becomes 3.1. The major bump makes v2.0.x refuse the house
   instead of running windows it can no longer read.

The migration is refused, with nothing written, while window entries are
left (the nag), and when a window cannot be read (it never ran on v2.0,
so it has no layered settings of its own; or it drives several covers):
the house then stays 2.1 and fails to set up, and v2.0.x still runs it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .const import (
    _LOGGER,
    DOMAIN,
    HOUSE_ENTRY_MINOR_VERSION,
    HOUSE_ENTRY_VERSION,
    V2_0_HOUSE_VERSION,
)
from .runtime.clock import SYSTEM_CLOCK
from .settings.shadow import AREAS, FLOORS, HOUSE, TEMPERATURE_UNIT
from .settings.window_record import RecordError, is_v2_0, record_from_v2_0
from .windows import (
    WINDOW_SUBENTRY,
    legacy_window_entries,
    subentry_window_key,
)

ISSUE_ID: Final = "consolidate_first"
"""The repair issue of a house that still has window entries."""
SNAPSHOT_KEY: Final = f"{DOMAIN}.v2_0_snapshot"
SNAPSHOT_VERSION: Final = 1

HOUSE_OPTION_KEYS: Final = frozenset({HOUSE, FLOORS, AREAS, TEMPERATURE_UNIT})
"""What the house options keep: the layered settings."""

SWITCH_ALIASES: Final = (
    "Toggle Control",
    "Manual Override",
    "Climate Mode",
    "Outside Temperature",
    "Lux",
    "Irradiance",
)
"""The unique_id suffixes of the per-window switch aliases (removed)."""
NUMBER_PREFIX: Final = "number_"
"""The unique_id suffix prefix of the window numbers the P5 flip retired."""


class MigrationRefused(Exception):
    """The house cannot migrate now (the message says why); nothing was written."""


# ------------------------------------------------------------ the nag


def needs_consolidation(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return the enabled window entries a house must consolidate first."""
    return legacy_window_entries(hass)


@callback
def async_check_consolidate_issue(hass: HomeAssistant) -> bool:
    """Raise (or clear) the ``consolidate_first`` issue; return whether it is up."""
    windows = needs_consolidation(hass)
    if not windows:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        return False
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_ID,
        translation_placeholders={
            "count": str(len(windows)),
            "windows": ", ".join(sorted(entry.title for entry in windows)),
        },
    )
    return True


def consolidate_first_error(hass: HomeAssistant) -> ConfigEntryError:
    """Return the setup error of an entry of a house that needs consolidation."""
    windows = needs_consolidation(hass)
    return ConfigEntryError(
        translation_domain=DOMAIN,
        translation_key=ISSUE_ID,
        translation_placeholders={"count": str(len(windows))},
    )


# ------------------------------------------------------------ the migration


def _is_alias_row(row: er.RegistryEntry, keys: set[str]) -> bool:
    """Whether ``row`` is a window's switch alias or retired number."""
    if row.platform != DOMAIN:
        return False
    for key in keys:
        suffix = row.unique_id.removeprefix(f"{key}_")
        if suffix == row.unique_id:
            continue
        if row.domain == "switch" and suffix in SWITCH_ALIASES:
            return True
        if row.domain == "number" and suffix.startswith(NUMBER_PREFIX):
            return True
    return False


def house_options_3_1(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return the house options without the hub's leftovers (pure)."""
    return {key: value for key, value in options.items() if key in HOUSE_OPTION_KEYS}


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _row_record(row: er.RegistryEntry) -> dict[str, Any]:
    return {
        "entity_id": row.entity_id,
        "unique_id": row.unique_id,
        "domain": row.domain,
        "config_entry_id": row.config_entry_id,
        "config_subentry_id": row.config_subentry_id,
        "device_id": row.device_id,
        "name": row.name,
        "disabled_by": row.disabled_by,
        "hidden_by": row.hidden_by,
    }


async def _async_write_snapshot(
    hass: HomeAssistant, house: ConfigEntry, removed: list[er.RegistryEntry]
) -> None:
    """Write the pre-migration snapshot once (a retried migration keeps it)."""
    store: Store[dict[str, Any]] = Store(hass, SNAPSHOT_VERSION, SNAPSHOT_KEY)
    if await store.async_load() is not None:
        return
    await store.async_save(
        _jsonable(
            {
                "created_at": SYSTEM_CLOCK.utcnow().isoformat(),
                "house": {
                    "entry_id": house.entry_id,
                    "version": house.version,
                    "minor_version": house.minor_version,
                    "data": dict(house.data),
                    "options": dict(house.options),
                    "subentries": [
                        subentry.as_dict() for subentry in house.subentries.values()
                    ],
                },
                "removed_entities": [_row_record(row) for row in removed],
            }
        )
    )


async def async_migrate_house(hass: HomeAssistant, house: ConfigEntry) -> None:
    """Migrate a consolidated house from 2.1 to 3.1 (see the module docstring).

    Raises
    ------
    MigrationRefused
        Window entries are left, or a window cannot be read; nothing was
        written.

    """
    if windows := needs_consolidation(hass):
        raise MigrationRefused(
            f"{len(windows)} window entries are not consolidated yet"
        )
    records = {}
    for subentry in house.get_subentries_of_type(WINDOW_SUBENTRY):
        if not is_v2_0(subentry.data):
            continue  # already rewritten (a migration retried after a crash)
        try:
            records[subentry.subentry_id] = record_from_v2_0(
                subentry.data, subentry.subentry_id
            )
        except RecordError as err:
            raise MigrationRefused(f"window {subentry.title!r}: {err}") from err
    keys = {
        subentry_window_key(subentry)
        for subentry in house.get_subentries_of_type(WINDOW_SUBENTRY)
    }
    ent_reg = er.async_get(hass)
    removed = [
        row for row in list(ent_reg.entities.values()) if _is_alias_row(row, keys)
    ]
    await _async_write_snapshot(hass, house, removed)
    for subentry_id, record in records.items():
        hass.config_entries.async_update_subentry(
            house, house.subentries[subentry_id], data=record.as_data()
        )
    for row in removed:
        ent_reg.async_remove(row.entity_id)
    hass.config_entries.async_update_entry(
        house,
        options=house_options_3_1(house.options),
        version=HOUSE_ENTRY_VERSION,
        minor_version=HOUSE_ENTRY_MINOR_VERSION,
    )
    _LOGGER.info(
        "Migrated the house to %s.%s: %s window(s) rewritten, %s switch alias "
        "and number row(s) removed",
        HOUSE_ENTRY_VERSION,
        HOUSE_ENTRY_MINOR_VERSION,
        len(records),
        len(removed),
    )


async def async_migrate(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """``async_migrate_entry``: the house 2.1 -> 3.1; everything else waits.

    A window entry (1.x), a 1.x house and a house that must consolidate
    first are left exactly as they are (True: their setup then fails with
    the ``consolidate_first`` message). A newer major version is refused
    by Home Assistant before this runs; a newer minor loads as is.
    """
    from .hub import is_hub_entry

    if not is_hub_entry(entry) or entry.version < V2_0_HOUSE_VERSION:
        return True
    if entry.version == V2_0_HOUSE_VERSION:
        try:
            await async_migrate_house(hass, entry)
        except MigrationRefused as err:
            _LOGGER.error(
                "The house stays at %s.%s (Adaptive Cover v2.0.x still runs it): %s",
                entry.version,
                entry.minor_version,
                err,
            )
    return True


def is_current_house(entry: ConfigEntry) -> bool:
    """Whether the house entry is in the shape this version runs (3.x)."""
    return entry.version == HOUSE_ENTRY_VERSION
