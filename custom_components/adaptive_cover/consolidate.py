"""Consolidate the house: window entries become subentries of the house (P7).

The owner starts it by fixing the "Consolidate" repair issue on the house
entry (``repairs.ConsolidateFlow``), after taking a backup. The flow shows
a dry run first (``consolidation_plan``), then moves every enabled window
entry into a ``window`` subentry of the house (``async_consolidate``).

**What stays the same.** A window's key is its old entry_id (windows.py),
so every entity keeps its unique_id and entity_id; the registry rows are
re-parented, not recreated, so names, areas, icons, labels, history,
dashboards and automations keep working. The override store and the Mode
select's restore state are keyed by the window key and entity_id, so an
active hold survives. The subentry stores the entry's data and options
verbatim (ADR 0006), so every window resolves the same settings; the dry
run checks that for every window and refuses to start if one differs.

**Per window** (``async_move_window``):

1. unload the window entry;
2. add its subentry to the house (``window_key`` = the entry_id; unique_id
   = the cover's registry id), unless an interrupted run added it;
3. re-parent its entity rows to the house and the subentry, THEN its
   device (with ``via_device_id`` = the house device). Order matters: a
   device that changes config entry takes the entities still on the old
   one with it (HA removes them);
4. check that nothing is left on the entry;
5. remove the entry. Removing an entry deletes whatever it still owns, so
   this runs only after step 4.

**Resumable.** Every step checks the registry first, so a run that stopped
anywhere (an error, a restart) resumes where it stopped, and a run after
a finished one changes nothing. The subentries themselves record the
progress: a subentry whose window entry still exists is "pending" and the
house does not run it (its entry does, after a restart). A restart can
recreate a device on the pending entry while its original already moved:
the entities then join the moved device and the duplicate goes with the
entry.

**Versions.** The house becomes a 2.x entry before the first window moves
(``config_flow.async_promote_house``), so an older version refuses it
rather than running it without its windows. Before the click, a downgrade
is the rollback; after it, the backup is. A snapshot of the entries, their
registry rows and the override store is written once, to
``.storage/adaptive_cover.v1_snapshot``.

Disabled window entries are left as they are (they drive nothing); the
dry run lists them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigSubentry,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store


from .const import _LOGGER, CONFIG_ENTRY_MINOR_VERSION, DOMAIN
from .runtime.clock import SYSTEM_CLOCK
from .settings.lift import same_value
from .settings.normalize import window_covers
from .settings.shadow import is_lifted
from .windows import (
    WINDOW_SUBENTRY,
    WindowEntry,
    house_entry,
    legacy_window_entries,
    subentry_window_key,
    window_subentry_data,
)

ISSUE_ID: Final = "consolidate_house"
SNAPSHOT_KEY: Final = f"{DOMAIN}.v1_snapshot"
SNAPSHOT_VERSION: Final = 1

_BLOCKING_STATES: Final = frozenset(
    {
        ConfigEntryState.MIGRATION_ERROR,
        ConfigEntryState.SETUP_ERROR,
        ConfigEntryState.FAILED_UNLOAD,
    }
)


class ConsolidationError(HomeAssistantError):
    """The consolidation stopped; what moved so far stays moved (resumable)."""


@dataclass(frozen=True)
class WindowMove:
    """One window entry the consolidation moves."""

    window_key: str
    title: str
    cover: str | None
    entity_ids: tuple[str, ...]
    """Its entities: every one keeps its entity_id."""
    devices: int
    resumed: bool
    """Its subentry exists already (an interrupted run added it)."""


@dataclass(frozen=True)
class ConsolidationPlan:
    """The dry run: what moves, what stays, and what blocks the move."""

    house_entry_id: str
    moves: tuple[WindowMove, ...]
    left_alone: tuple[str, ...]
    """Disabled window entries (titles): left as they are."""
    problems: tuple[str, ...]
    """Why the consolidation cannot start (each a sentence)."""
    mismatches: tuple[str, ...]
    """Windows whose resolved settings would change (it cannot start)."""

    @property
    def ok(self) -> bool:
        """Whether the consolidation can start."""
        return not self.problems and not self.mismatches

    @property
    def entity_count(self) -> int:
        """How many entities move (all keep their entity_id)."""
        return sum(len(move.entity_ids) for move in self.moves)


@dataclass(frozen=True)
class ConsolidationReport:
    """What a finished run did."""

    moved: tuple[str, ...]
    """The window keys moved by this run."""
    entity_count: int
    left_alone: tuple[str, ...]


# ------------------------------------------------------------ lookups


def windows_to_move(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return the enabled window entries, by title (the order they move in)."""
    return sorted(
        legacy_window_entries(hass),
        key=lambda entry: (entry.title.casefold(), entry.entry_id),
    )


def subentry_for(house: ConfigEntry, window_key: str) -> ConfigSubentry | None:
    """Return the house's subentry of this window, if it has one."""
    return next(
        (
            subentry
            for subentry in house.get_subentries_of_type(WINDOW_SUBENTRY)
            if subentry_window_key(subentry) == window_key
        ),
        None,
    )


def _window_rows(hass: HomeAssistant, window_key: str) -> list[er.RegistryEntry]:
    """Every entity row of one window: its unique_id prefix, or its entry."""
    prefix = f"{window_key}_"
    return [
        row
        for row in er.async_get(hass).entities.values()
        if row.config_entry_id == window_key
        or (row.platform == DOMAIN and row.unique_id.startswith(prefix))
    ]


def _window_devices(
    hass: HomeAssistant, house: ConfigEntry, window_key: str
) -> list[dr.DeviceEntry]:
    """Return the window's devices: those on its entry, and its device on the house."""
    dev_reg = dr.async_get(hass)
    devices = list(dr.async_entries_for_config_entry(dev_reg, window_key))
    moved = dev_reg.async_get_device_by_identifier(
        (DOMAIN, window_key), config_entry_id=house.entry_id
    )
    if moved is not None:
        devices.append(moved)
    return devices


# ------------------------------------------------------------ the dry run


def _mismatch(
    hass: HomeAssistant, house: ConfigEntry, entry: ConfigEntry
) -> str | None:
    """Return why a window would act on other settings as a subentry, or None."""
    from .layers import effective_settings

    old = effective_settings(hass, entry)
    new = effective_settings(
        hass,
        WindowEntry.virtual(
            house, entry.entry_id, entry.title, entry.data, entry.options
        ),
    )
    keys = sorted(
        key
        for key in old.options.keys() | new.options.keys()
        if not same_value(old.options.get(key), new.options.get(key))
    )
    if old.provenance != new.provenance:
        keys.append("provenance")
    if not keys:
        return None
    return f"{entry.title}: {', '.join(keys)}"


def consolidation_plan(hass: HomeAssistant, house: ConfigEntry) -> ConsolidationPlan:
    """Return the dry run: nothing is written.

    It blocks when the house has no layered settings yet, when a window
    drives several covers (fix its split repair first), when a window
    entry is not migrated or failed to set up, and when a window would
    resolve other settings as a subentry.
    """
    problems: list[str] = []
    mismatches: list[str] = []
    if not is_lifted(house.options):
        problems.append("The house has no layered settings yet.")
    moves: list[WindowMove] = []
    for entry in windows_to_move(hass):
        covers = window_covers(entry.options)
        if len(covers) > 1:
            problems.append(
                f"{entry.title} drives {len(covers)} covers: fix its split "
                "repair first."
            )
        if entry.minor_version < CONFIG_ENTRY_MINOR_VERSION:
            problems.append(f"{entry.title} is not migrated yet: restart first.")
        if entry.state in _BLOCKING_STATES:
            problems.append(f"{entry.title} failed to load ({entry.state.value}).")
        if not problems and (mismatch := _mismatch(hass, house, entry)) is not None:
            mismatches.append(mismatch)
        moves.append(
            WindowMove(
                window_key=entry.entry_id,
                title=entry.title,
                cover=covers[0] if covers else None,
                entity_ids=tuple(
                    sorted(row.entity_id for row in _window_rows(hass, entry.entry_id))
                ),
                devices=len(_window_devices(hass, house, entry.entry_id)),
                resumed=subentry_for(house, entry.entry_id) is not None,
            )
        )
    left_alone = tuple(
        sorted(
            entry.title
            for entry in legacy_window_entries(hass, include_disabled=True)
            if entry.disabled_by is not None
        )
    )
    return ConsolidationPlan(
        house_entry_id=house.entry_id,
        moves=tuple(moves),
        left_alone=left_alone,
        problems=tuple(problems),
        mismatches=tuple(mismatches),
    )


# ------------------------------------------------------------ the snapshot


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _entry_record(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "version": entry.version,
        "minor_version": entry.minor_version,
        "unique_id": entry.unique_id,
        "disabled_by": entry.disabled_by,
        "data": dict(entry.data),
        "options": dict(entry.options),
        "subentries": [subentry.as_dict() for subentry in entry.subentries.values()],
    }


def _row_record(row: er.RegistryEntry) -> dict[str, Any]:
    return {
        "entity_id": row.entity_id,
        "unique_id": row.unique_id,
        "platform": row.platform,
        "config_entry_id": row.config_entry_id,
        "config_subentry_id": row.config_subentry_id,
        "device_id": row.device_id,
        "area_id": row.area_id,
        "name": row.name,
        "icon": row.icon,
        "disabled_by": row.disabled_by,
        "hidden_by": row.hidden_by,
        "entity_category": row.entity_category,
        "labels": sorted(row.labels),
    }


def _device_record(device: dr.DeviceEntry) -> dict[str, Any]:
    return {
        "id": device.id,
        "identifiers": sorted(list(identifier) for identifier in device.identifiers),
        "name": device.name,
        "name_by_user": device.name_by_user,
        "area_id": device.area_id,
        "config_entry_id": device.config_entry_id,
        "config_subentry_id": device.config_subentry_id,
        "via_device_id": device.via_device_id,
        "disabled_by": device.disabled_by,
        "labels": sorted(device.labels),
    }


async def async_write_snapshot(hass: HomeAssistant, house: ConfigEntry) -> bool:
    """Write the pre-consolidation snapshot once; return whether it was written.

    ``.storage/adaptive_cover.v1_snapshot``: the house and window entries,
    their entity and device rows and the override store. A resumed run
    keeps the first snapshot.
    """
    store: Store[dict[str, Any]] = Store(hass, SNAPSHOT_VERSION, SNAPSHOT_KEY)
    if await store.async_load() is not None:
        return False
    entries = legacy_window_entries(hass, include_disabled=True)
    keys = {entry.entry_id for entry in entries}
    rows = [
        row
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN or row.config_entry_id in keys | {house.entry_id}
    ]
    dev_reg = dr.async_get(hass)
    devices = [
        device
        for entry_id in keys | {house.entry_id}
        for device in dr.async_entries_for_config_entry(dev_reg, entry_id)
    ]
    snapshot = {
        "created_at": SYSTEM_CLOCK.utcnow().isoformat(),
        "house": _entry_record(house),
        "windows": [_entry_record(entry) for entry in entries],
        "entities": [_row_record(row) for row in rows],
        "devices": [_device_record(device) for device in devices],
        "override_store": hass.data.get(f"{DOMAIN}_manual_state", {}),
    }
    await store.async_save(_jsonable(snapshot))
    return True


# ------------------------------------------------------------ the move


@callback
def _async_add_subentry(
    hass: HomeAssistant, house: ConfigEntry, entry: ConfigEntry
) -> ConfigSubentry:
    """Add the window's subentry (its key is the entry_id)."""
    unique_id = entry.unique_id
    taken = {subentry.unique_id for subentry in house.subentries.values()}
    if unique_id is not None and unique_id in taken:
        _LOGGER.warning(
            "%s: another window already holds unique_id %s; moving it without",
            entry.title,
            unique_id,
        )
        unique_id = None
    subentry = ConfigSubentry(
        data=_frozen(window_subentry_data(entry.entry_id, entry.data, entry.options)),
        subentry_type=WINDOW_SUBENTRY,
        title=entry.title,
        unique_id=unique_id,
    )
    hass.config_entries.async_add_subentry(house, subentry)
    return subentry


def _frozen(data: dict[str, Any]) -> Any:
    from types import MappingProxyType

    return MappingProxyType(data)


def _house_device_id(hass: HomeAssistant, house: ConfigEntry) -> str:
    from .hub import hub_device_info

    return (
        dr.async_get(hass)
        .async_get_or_create(config_entry_id=house.entry_id, **hub_device_info())
        .id
    )


@callback
def async_reparent_window(
    hass: HomeAssistant, house: ConfigEntry, subentry_id: str, window_key: str
) -> None:
    """Move a window's entity rows, then its device, to the house subentry.

    Entities first: when a device changes config entry, HA removes the
    entities still on the old one. Rows that moved already are left alone.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    identifier = (DOMAIN, window_key)
    moved = dev_reg.async_get_device_by_identifier(
        identifier, config_entry_id=house.entry_id
    )
    legacy = dev_reg.async_get_device_by_identifier(
        identifier, config_entry_id=window_key
    )
    for row in _window_rows(hass, window_key):
        changes: dict[str, Any] = {}
        if (
            row.config_entry_id != house.entry_id
            or row.config_subentry_id != subentry_id
        ):
            changes["config_entry_id"] = house.entry_id
            changes["config_subentry_id"] = subentry_id
        if moved is not None and row.device_id != moved.id:
            # A restart recreated the device on the entry: join the moved one.
            changes["device_id"] = moved.id
        if changes:
            ent_reg.async_update_entity(row.entity_id, **changes)
    if moved is None and legacy is not None:
        dev_reg.async_update_device(
            legacy.id,
            new_config_entry_id=house.entry_id,
            new_config_subentry_id=subentry_id,
            via_device_id=_house_device_id(hass, house),
        )
    elif moved is not None and moved.config_subentry_id != subentry_id:
        dev_reg.async_update_device(moved.id, new_config_subentry_id=subentry_id)


def unmoved(
    hass: HomeAssistant, house: ConfigEntry, subentry_id: str, window_key: str
) -> list[str]:
    """Return what of a window is not on the house subentry yet (empty: done)."""
    left = [
        row.entity_id
        for row in _window_rows(hass, window_key)
        if row.config_entry_id != house.entry_id
        or row.config_subentry_id != subentry_id
    ]
    dev_reg = dr.async_get(hass)
    moved = dev_reg.async_get_device_by_identifier(
        (DOMAIN, window_key), config_entry_id=house.entry_id
    )
    if moved is not None and moved.config_subentry_id != subentry_id:
        left.append(f"device {moved.name}")
    for device in dr.async_entries_for_config_entry(dev_reg, window_key):
        if er.async_entries_for_device(
            er.async_get(hass), device.id, include_disabled_entities=True
        ):
            left.append(f"device {device.name}")
        elif moved is None and (DOMAIN, window_key) in device.identifiers:
            left.append(f"device {device.name}")
    return left


async def _async_remove_legacy_entry(hass: HomeAssistant, window_key: str) -> None:
    """Remove a moved window's entry (it owns nothing any more)."""
    await hass.config_entries.async_remove(window_key)


async def async_move_window(
    hass: HomeAssistant, house: ConfigEntry, entry: ConfigEntry
) -> str:
    """Move one window entry into a house subentry; return its subentry_id.

    Raises
    ------
    ConsolidationError
        Something of the window did not move; its entry is kept.

    """
    key = entry.entry_id
    if entry.state in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_RETRY):
        if not await hass.config_entries.async_unload(key):
            raise ConsolidationError(f"{entry.title} could not be unloaded")
    subentry = subentry_for(house, key) or _async_add_subentry(hass, house, entry)
    rows_before = {row.entity_id for row in _window_rows(hass, key)}
    async_reparent_window(hass, house, subentry.subentry_id, key)
    ent_reg = er.async_get(hass)
    if lost := sorted(e for e in rows_before if ent_reg.async_get(e) is None):
        # HA removed rows while they moved: stop before the entry goes too.
        raise ConsolidationError(
            f"{entry.title}: {len(lost)} entity row(s) were removed while "
            f"moving ({', '.join(lost[:5])}); its entry is kept"
        )
    if left := unmoved(hass, house, subentry.subentry_id, key):
        raise ConsolidationError(
            f"{entry.title}: {len(left)} registry row(s) did not move "
            f"({', '.join(left[:5])}); its entry is kept"
        )
    await _async_remove_legacy_entry(hass, key)
    _LOGGER.info("Consolidated %s into the house (window key %s)", entry.title, key)
    return subentry.subentry_id


async def async_consolidate(
    hass: HomeAssistant, house: ConfigEntry
) -> ConsolidationReport:
    """Move every enabled window entry into a subentry of the house.

    Raises
    ------
    ConsolidationError
        The dry run found a problem (nothing moved), or a window did not
        move (the windows before it did; run it again to resume).

    """
    from .config_flow import async_promote_house
    from .house import house_runtime

    plan = consolidation_plan(hass, house)
    if not plan.ok:
        raise ConsolidationError(" ".join([*plan.problems, *plan.mismatches]))
    await async_write_snapshot(hass, house)
    async_promote_house(hass, house)
    moved: list[str] = []
    try:
        for move in plan.moves:
            entry = hass.config_entries.async_get_entry(move.window_key)
            if entry is None:
                continue
            await async_move_window(hass, house, entry)
            moved.append(move.window_key)
    finally:
        if (runtime := house_runtime(house)) is not None:
            await runtime.async_sync()
        async_check_consolidate_issue(hass)
    return ConsolidationReport(
        moved=tuple(moved),
        entity_count=plan.entity_count,
        left_alone=plan.left_alone,
    )


# ------------------------------------------------------------ the issue


@callback
def async_check_consolidate_issue(hass: HomeAssistant) -> None:
    """Offer the consolidation while the house has window entries (a repair)."""
    house = house_entry(hass)
    windows = legacy_window_entries(hass)
    if house is None or not windows:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_ID,
        translation_placeholders={"windows": str(len(windows))},
        data={"entry_id": house.entry_id},
    )
