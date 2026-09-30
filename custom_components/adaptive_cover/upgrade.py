"""Upgrading the house: migrations 2.1 -> 3.1 (P8) and 3.1 -> 3.2, and the nag.

Since v2.1 the house entry is the only config entry that runs; its
windows are its ``window`` subentries (ADR 0001, ADR 0007). v2.1 has no
window-entry runtime.

**A 1.x house upgrades at its first start** (ADR 0008). While the house
is below 3.x and window entries are left (the live house on v1.19.x, or
a consolidation v2.0.x stopped part way), the house's migration moves
them into the house first (``consolidate.async_upgrade_house``), then
runs migration 2.1 -> 3.1 below. The window entries do not set up; if
the upgrade stops, the ``upgrade_stopped`` repair says why and nothing is
removed.

**The nag** (ADR 0007) stays for what the upgrade cannot take: enabled
window entries next to a house that is 3.x already (an old entry enabled
again), or with no house entry at all. Each of those entries fails to set
up with the ``consolidate_first`` message and the ``consolidate_first``
repair issue says what to do; nothing is written. Disabled window entries
drive nothing and do not count.

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
left, and when a window cannot be read (it never ran on v2.0, so it has
no layered settings of its own; or it drives several covers): the house
then stays 2.1 and fails to set up, and v2.0.x still runs it.

**Migration 3.1 -> 3.2** (one Climate switch, ``async_migrate_house_3_2``;
a 2.1 house takes it right after 3.1):

1. every window whose ``climate_mode`` resolved to False (its 3.1
   precedence: its own value, its area, its floor, the house, the default
   False) stores ``ignore_climate: True`` in its one-time settings; a
   window it resolved to True stores nothing new. ``climate_mode`` leaves
   the window's overrides;
2. ``climate_mode`` leaves the house, floor and area profiles;
3. the house becomes 3.2.

A window then runs climate control while the Climate switch
(``climate_on``) is on, a temperature source resolves for it and it does
not opt out (``runtime/shade_config.climate_capable``): exactly the windows
that ran it on 3.1, except one with no temperature source at all. A window
subentry that is not a 3.1 record is left as it is (it fails to set up, as
on 3.1). Nothing is refused: the rollback is the Home Assistant backup.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .const import (
    _LOGGER,
    CONF_CLIMATE_MODE,
    CONF_IGNORE_CLIMATE,
    DOMAIN,
    HOUSE_3_1_MINOR_VERSION,
    HOUSE_ENTRY_MINOR_VERSION,
    HOUSE_ENTRY_VERSION,
    V2_0_HOUSE_VERSION,
)
from .runtime.clock import SYSTEM_CLOCK
from .settings.resolve import Placement, WindowOverrides
from .settings.shadow import AREAS, FLOORS, HOUSE, TEMPERATURE_UNIT
from .settings.window_record import (
    RecordError,
    WindowRecord,
    is_v2_0,
    record_from_v2_0,
)
from .windows import (
    WINDOW_SUBENTRY,
    WindowEntry,
    house_entry,
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
    """Return the enabled window entries the upgrade cannot move (the nag).

    Those of a house that is 3.x already, or of no (enabled) house. A
    house below 3.x moves its window entries itself at its first start.
    """
    house = house_entry(hass)
    if house is not None and house.disabled_by is None and not is_current_house(house):
        return []
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
    if windows := legacy_window_entries(hass):
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
        minor_version=HOUSE_3_1_MINOR_VERSION,
    )
    _LOGGER.info(
        "Migrated the house to %s.%s: %s window(s) rewritten, %s switch alias "
        "and number row(s) removed",
        HOUSE_ENTRY_VERSION,
        HOUSE_3_1_MINOR_VERSION,
        len(records),
        len(removed),
    )


# ------------------------------------------------------------ 3.1 -> 3.2


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast("Mapping[str, Any]", value)
    return {}


def climate_mode_3_1(
    overrides: WindowOverrides, placement: Placement, hub: Mapping[str, Any]
) -> bool:
    """Return what a 3.1 window's ``climate_mode`` resolved to (pure).

    Its 3.1 precedence: the window's own value (legacy, then values), its
    area, its floor, the house, the spec default False. A stored None was
    off, as the runtime read it.
    """
    layers = (
        overrides.legacy,
        overrides.values,
        _mapping(_mapping(hub.get(AREAS)).get(placement.area_id or "")),
        _mapping(_mapping(hub.get(FLOORS)).get(placement.floor_id or "")),
        _mapping(hub.get(HOUSE)),
    )
    for layer in layers:
        if CONF_CLIMATE_MODE in layer:
            return bool(layer[CONF_CLIMATE_MODE])
    return False


def _without_climate_mode(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key != CONF_CLIMATE_MODE}


def record_3_2(record: WindowRecord, climate_mode: bool) -> WindowRecord:
    """Return a 3.1 window record as 3.2 stores it (pure).

    ``climate_mode`` (what it resolved to) False becomes the window's
    ``ignore_climate`` opt-out; ``climate_mode`` leaves its overrides.
    """
    geometry = dict(record.geometry)
    if not climate_mode:
        geometry[CONF_IGNORE_CLIMATE] = True
    return record.with_changes(
        geometry=geometry,
        overrides=WindowOverrides(
            values=_without_climate_mode(record.overrides.values),
            legacy=_without_climate_mode(record.overrides.legacy),
        ),
    )


def house_options_3_2(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return the house options without ``climate_mode`` in any profile (pure).

    A floor or area profile left empty goes (the rooms inherit, as ever).
    """
    migrated = dict(options)
    if HOUSE in options:
        migrated[HOUSE] = _without_climate_mode(_mapping(options[HOUSE]))
    for bucket in (FLOORS, AREAS):
        if bucket not in options:
            continue
        kept: dict[str, Any] = {}
        for key, profile in _mapping(options[bucket]).items():
            values = _without_climate_mode(_mapping(profile))
            if values:
                kept[key] = values
        migrated[bucket] = kept
    return migrated


@callback
def async_migrate_house_3_2(hass: HomeAssistant, house: ConfigEntry) -> None:
    """Migrate the house from 3.1 to 3.2 (see the module docstring)."""
    from .layers import window_placement

    opted_out: list[str] = []
    for subentry in house.get_subentries_of_type(WINDOW_SUBENTRY):
        try:
            record = WindowRecord.from_data(subentry.data)
        except RecordError:
            continue  # not a window record: it fails to set up, as on 3.1
        placement = window_placement(hass, WindowEntry(house, subentry.subentry_id))
        climate_mode = climate_mode_3_1(record.overrides, placement, house.options)
        if not climate_mode:
            opted_out.append(subentry.title)
        migrated = record_3_2(record, climate_mode).as_data()
        if migrated != record.as_data():
            hass.config_entries.async_update_subentry(house, subentry, data=migrated)
    hass.config_entries.async_update_entry(
        house,
        options=house_options_3_2(house.options),
        version=HOUSE_ENTRY_VERSION,
        minor_version=HOUSE_ENTRY_MINOR_VERSION,
    )
    _LOGGER.info(
        "Migrated the house to %s.%s (one Climate switch): %s window(s) opt out "
        "of climate control (their climate_mode was off): %s",
        HOUSE_ENTRY_VERSION,
        HOUSE_ENTRY_MINOR_VERSION,
        len(opted_out),
        ", ".join(sorted(opted_out)) or "none",
    )


async def async_migrate(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """``async_migrate_entry``: the house moves its window entries in, then 2.1 -> 3.1 -> 3.2.

    A house below 3.x with enabled window entries runs the whole upgrade
    (``consolidate.async_upgrade_house``: 1.x schema, consolidation, then
    migration 3.1); a 2.1 house without them runs migration 3.1. A 3.1
    house (whichever way it got there) then runs migration 3.2. A window
    entry is left as it is (the house moves it). Always True: a house the
    upgrade could not move stays at its version and its setup says why. A
    newer major version is refused by Home Assistant before this runs; a
    newer minor loads as is.
    """
    from .hub import is_hub_entry

    if not is_hub_entry(entry):
        return True
    if entry.version < HOUSE_ENTRY_VERSION and (windows := legacy_window_entries(hass)):
        from .consolidate import async_upgrade_house

        await async_upgrade_house(hass, entry, windows)
    elif entry.version == V2_0_HOUSE_VERSION:
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
    if (
        entry.version == HOUSE_ENTRY_VERSION
        and entry.minor_version < HOUSE_ENTRY_MINOR_VERSION
    ):
        async_migrate_house_3_2(hass, entry)
    return True


def is_current_house(entry: ConfigEntry) -> bool:
    """Whether the house entry is in the shape this version runs (3.x)."""
    return entry.version == HOUSE_ENTRY_VERSION
