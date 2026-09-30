"""Upgrading a v1.19.x house straight to v2.1, at the first start (ADR 0008).

The live house runs v1.19.x: one window config entry per window (1.x) and
the hub entry holding the lifted house, floor and area layers. v2.1 runs
only the house entry with its ``window`` subentries (ADR 0007). At the
first start of v2.1 the house's migration (``upgrade.async_migrate``)
calls ``async_upgrade_house``: it moves the windows into the house with no
click, then runs migration 2.1 -> 3.1 (``upgrade.async_migrate_house``).
One release, one restart (owner decision 2026-09-30).

**Phases** (each logged at INFO):

1. **1.x schema.** The window entries and the hub are brought to 1.5 with
   the steps v1.19.x runs itself, so a stop after this phase leaves a
   house v1.19.x runs: 1.3 writes a window's fallback options and its
   cover's registry id; the lift stores the house, floor and area layers
   (switch states included) when the hub holds none; 1.5 hides the switch
   aliases. An entry older than 1.2 stops the upgrade (install v1.19.x
   first).
2. **Plan** (nothing written). For every enabled window entry: the window
   record it becomes (``settings/window_record.py``), what it acts on in
   v1.19.x (its flat options and its switch states) and what the record
   resolves to under the house layers. A window whose stored overrides no
   longer give what it acts on (v1.19.x writes an edit to the flat option
   only) is adopted again against the layers, so it keeps acting on the
   same values. A window that drives several covers, a house without
   layers, or a window that still resolves other values stops the upgrade.
3. **Snapshot.** ``.storage/adaptive_cover.v1_snapshot``: the entries,
   their entity and device rows and the override store, written once.
4. **Move** (per window): add its subentry (the 3.1 record; its key is
   the old entry_id), move its entity rows to the house and the subentry,
   THEN its device: a device that changes config entry takes the entities
   still on the old one with it (Home Assistant removes them). What moved
   already is left alone, so a start after a crash resumes here.
5. **Verify** (nothing removed yet): every entity row still exists and
   sits on the house and the window's subentry, nothing is left on the
   window entry, the device hangs off the house device, and the window
   resolves through the v2.1 read path to exactly the planned values and
   provenance.
6. **Commit.** The house becomes 2.1 (from here v1.19.x refuses it), the
   window entries are removed (last), then migration 2.1 -> 3.1 runs.

A persistent notification says what was done.

**Failure.** Nothing is removed and no version changes before phase 5
passes. When a phase fails or raises, the moves are undone (rows back
on their window entries, devices back, the subentries removed), so
v1.19.x finds the house as it left it, and the ``upgrade_stopped`` repair
says why. If
the undo cannot restore a row (Home Assistant removed it), the repair
says to restore the backup taken before the update. A crash (a restart
part way) undoes nothing: the next start resumes where it stopped.

Disabled window entries are left as they are (they drive nothing).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import restore_state
from homeassistant.helpers.storage import Store

from .const import (
    _LOGGER,
    CONF_CLIMATE_MODE,
    CONF_CLIMATE_ON,
    CONF_ENTITIES,
    CONF_IRRADIANCE_ENTITY,
    CONF_LUX_ENTITY,
    CONF_MANUAL_DETECTION,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_SENSOR_TYPE,
    CONF_USE_IRRADIANCE,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    V2_0_HOUSE_VERSION,
    SensorType,
)
from .entity_surface import cover_area_id
from .runtime.clock import SYSTEM_CLOCK
from .runtime.shade_config import absent_options
from .settings.lift import LegacyWindow
from .settings.normalize import normalize_cover, window_cover, window_covers
from .settings.resolve import Placement, SettingsError, WindowOverrides
from .settings.shadow import (
    HOUSE,
    adopt,
    compare,
    differing_keys,
    hub_options,
    legacy_values,
    lift_house,
)
from .settings.window_record import (
    LEGACY,
    OVERRIDES,
    VALUES,
    WINDOW_KEY,
    RecordError,
    WindowRecord,
    is_v2_0,
    record_from_options,
    record_from_v2_0,
    v2_0_overrides,
)
from .window_cover import cover_registry_id
from .windows import WINDOW_SUBENTRY, WindowEntry, subentry_window_key

SNAPSHOT_KEY: Final = f"{DOMAIN}.v1_snapshot"
SNAPSHOT_VERSION: Final = 1
STOPPED_ISSUE: Final = "upgrade_stopped"
"""The repair issue of an upgrade that stopped (nothing removed)."""
NOTIFICATION_ID: Final = f"{DOMAIN}_upgraded"
OLDEST_MINOR: Final = 2
"""The oldest 1.x minor version the upgrade brings to 1.5 itself."""
LATEST_1X_MINOR: Final = 5

SWITCH_ALIASES: Final = (
    "Toggle Control",
    "Manual Override",
    "Climate Mode",
    "Outside Temperature",
    "Lux",
    "Irradiance",
)
"""The unique_id suffixes of a window's switches (hidden aliases since 1.5)."""


class UpgradeStopped(Exception):
    """The upgrade stopped; nothing was removed (the message says why)."""

    def __init__(self, reason: str, *, restore_backup: bool = False) -> None:
        """Record why, and whether only the backup brings the house back."""
        super().__init__(reason)
        self.reason = reason
        self.restore_backup = restore_backup


# ------------------------------------------------------------ switch states


def _climate(options: Mapping[str, Any]) -> bool:
    return bool(options.get(CONF_CLIMATE_MODE))


@dataclass(frozen=True)
class ToggleSwitch:
    """The v1.19.x switch behind one toggle, and when a window has it."""

    key: str
    """The toggle (a ``settings.shadow.TOGGLE_OPTS`` key)."""
    switch_name: str
    """The switch's unique_id suffix: ``f"{entry_id}_{switch_name}"``."""
    initial: bool
    """The switch's state when it has nothing to restore."""
    without_switch: bool
    """What v1.19.x uses when the switch entity is disabled."""
    created: Callable[[Mapping[str, Any]], bool]
    """Whether a window with these options has the switch."""


TOGGLE_SWITCHES: Final[tuple[ToggleSwitch, ...]] = (
    ToggleSwitch(
        CONF_CLIMATE_ON, "Climate Mode", True, without_switch=True, created=_climate
    ),
    ToggleSwitch(
        CONF_USE_OUTSIDE_TEMP,
        "Outside Temperature",
        False,
        without_switch=False,
        created=lambda options: (
            _climate(options)
            and bool(
                options.get(CONF_WEATHER_ENTITY) or options.get(CONF_OUTSIDETEMP_ENTITY)
            )
        ),
    ),
    ToggleSwitch(
        CONF_USE_LUX,
        "Lux",
        True,
        without_switch=False,
        created=lambda options: (
            _climate(options) and bool(options.get(CONF_LUX_ENTITY))
        ),
    ),
    ToggleSwitch(
        CONF_USE_IRRADIANCE,
        "Irradiance",
        True,
        without_switch=False,
        created=lambda options: (
            _climate(options) and bool(options.get(CONF_IRRADIANCE_ENTITY))
        ),
    ),
    ToggleSwitch(
        CONF_MANUAL_DETECTION,
        "Manual Override",
        True,
        without_switch=False,
        created=lambda options: len(options.get(CONF_ENTITIES) or []) >= 1,
    ),
)


def _switch_state(
    hass: HomeAssistant, entry_id: str, switch: ToggleSwitch, options: Mapping[str, Any]
) -> bool:
    """Return one switch's state as v1.19.x runs it (it restores from the cache)."""
    if not switch.created(options):
        return switch.initial
    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{entry_id}_{switch.switch_name}"
    )
    if entity_id is None:
        return switch.initial
    row = ent_reg.async_get(entity_id)
    if row is not None and row.disabled_by is not None:
        return switch.without_switch
    state = hass.states.get(entity_id)
    if state is not None and state.state in (STATE_ON, STATE_OFF):
        return state.state == STATE_ON
    stored = restore_state.async_get(hass).last_states.get(entity_id)
    if stored is None:
        return switch.initial
    return stored.state.state == STATE_ON


@callback
def read_toggles(
    hass: HomeAssistant, entry_id: str, options: Mapping[str, Any]
) -> dict[str, bool]:
    """Return a window's toggles from its v1.19.x switches, by toggle key."""
    return {
        switch.key: _switch_state(hass, entry_id, switch, options)
        for switch in TOGGLE_SWITCHES
    }


# ------------------------------------------------------------ 1.x reads


def _plain(values: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(values))


def legacy_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return a window entry's options as v1.19.x reads them (the 1.3 shape)."""
    flat = {key: value for key, value in options.items() if key != OVERRIDES}
    return normalize_cover({**flat, **absent_options(flat)})


def _overrides_option(window_key: str, overrides: WindowOverrides) -> dict[str, Any]:
    return {
        WINDOW_KEY: window_key,
        VALUES: _plain(overrides.values),
        LEGACY: _plain(overrides.legacy),
    }


def is_lifted(options: Mapping[str, Any]) -> bool:
    """Whether the hub's options hold the lifted layers."""
    return isinstance(options.get(HOUSE), Mapping)


def _window_device(
    hass: HomeAssistant, house: ConfigEntry, window_key: str
) -> dr.DeviceEntry | None:
    """Return the window's device: on its entry, or already moved to the house."""
    dev_reg = dr.async_get(hass)
    identifier = (DOMAIN, window_key)
    return dev_reg.async_get_device_by_identifier(
        identifier, config_entry_id=window_key
    ) or dev_reg.async_get_device_by_identifier(
        identifier, config_entry_id=house.entry_id
    )


def legacy_placement(
    hass: HomeAssistant, house: ConfigEntry, window_key: str, options: Mapping[str, Any]
) -> Placement:
    """Return the window's area (its device's, else its cover's) and floor."""
    device = _window_device(hass, house, window_key)
    area_id = device.area_id if device is not None else None
    if area_id is None:
        area_id = cover_area_id(hass, window_covers(options))
    area = ar.async_get(hass).async_get_area(area_id) if area_id else None
    if area is None:
        return Placement()
    return Placement(area_id=area.id, floor_id=area.floor_id)


def _legacy(
    hass: HomeAssistant, house: ConfigEntry, entry: ConfigEntry
) -> tuple[dict[str, Any], dict[str, Any], Placement]:
    """Return a window entry's options, what it acts on in v1.19.x, its placement."""
    options = legacy_options(entry.options)
    acts_on = legacy_values(
        options,
        read_toggles(hass, entry.entry_id, options),
        temperature_unit=hass.config.units.temperature_unit,
    )
    return options, acts_on, legacy_placement(hass, house, entry.entry_id, options)


def _window_rows(hass: HomeAssistant, window_key: str) -> list[er.RegistryEntry]:
    """Every entity row of one window: its entry's, or its unique_id prefix."""
    prefix = f"{window_key}_"
    return [
        row
        for row in er.async_get(hass).entities.values()
        if row.config_entry_id == window_key
        or (row.platform == DOMAIN and row.unique_id.startswith(prefix))
    ]


# ------------------------------------------------------------ phase 1: 1.x


def _wanted_unique_id(
    hass: HomeAssistant, entry: ConfigEntry, cover: str | None
) -> str | None:
    """Return the cover's registry id, unless another entry holds it."""
    registry_id = cover_registry_id(hass, cover)
    if registry_id is None or registry_id == entry.unique_id:
        return registry_id
    holder = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, registry_id)
    return None if holder is not None else registry_id


@callback
def _async_migrate_window_1_3(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """1.3: write the fallback options and the cover as cover_entity_id."""
    options = legacy_options(entry.options)
    if OVERRIDES in entry.options:
        options[OVERRIDES] = entry.options[OVERRIDES]
    update: dict[str, Any] = {"options": options, "minor_version": 3}
    unique_id = _wanted_unique_id(hass, entry, window_cover(options))
    if unique_id is not None and unique_id != entry.unique_id:
        update["unique_id"] = unique_id
    hass.config_entries.async_update_entry(entry, **update)


@callback
def _async_lift(
    hass: HomeAssistant, house: ConfigEntry, windows: list[ConfigEntry]
) -> None:
    """Lift the windows into the hub's layers (as v1.19.x's migration 1.4 does)."""
    unit = hass.config.units.temperature_unit
    legacy: list[LegacyWindow] = []
    for entry in windows:
        _options, acts_on, placement = _legacy(hass, house, entry)
        legacy.append(
            LegacyWindow(
                window_key=entry.entry_id, options=acts_on, area_id=placement.area_id
            )
        )
    lifted = lift_house(
        legacy,
        {area.id: area.floor_id for area in ar.async_get(hass).async_list_areas()},
        [floor.floor_id for floor in fr.async_get(hass).async_list_floors()],
        temperature_unit=unit,
    )
    hass.config_entries.async_update_entry(
        house, options={**house.options, **hub_options(lifted)}
    )
    for entry in windows:
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                OVERRIDES: _overrides_option(
                    entry.entry_id, lifted.overrides[entry.entry_id]
                ),
            },
        )


@callback
def _async_hide_aliases(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """1.5: the window's switches become hidden aliases."""
    ent_reg = er.async_get(hass)
    for row in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        suffix = row.unique_id.removeprefix(f"{entry.entry_id}_")
        if (
            row.platform == DOMAIN
            and row.domain == Platform.SWITCH
            and suffix in SWITCH_ALIASES
            and row.hidden_by is None
        ):
            ent_reg.async_update_entity(
                row.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
            )


@callback
def async_bring_to_1_5(
    hass: HomeAssistant, house: ConfigEntry, windows: list[ConfigEntry]
) -> None:
    """Bring the window entries and the hub to 1.5 (what v1.19.x would write).

    Raises
    ------
    UpgradeStopped
        An entry is older than 1.2; nothing was written.

    """
    legacy = [entry for entry in (house, *windows) if entry.version == 1]
    if too_old := sorted(e.title for e in legacy if e.minor_version < OLDEST_MINOR):
        raise UpgradeStopped(
            f"{', '.join(too_old)}: stored by an Adaptive Cover older than "
            "1.2. Install v1.19.x, start it once, then update again."
        )
    migrated: list[str] = []
    for entry in windows:
        if entry.minor_version < 3:
            _async_migrate_window_1_3(hass, entry)
            migrated.append(f"{entry.title} 1.3")
    if house.version == 1 and not is_lifted(house.options):
        _async_lift(hass, house, windows)
        migrated.append(f"{house.title} lifted")
    for entry in legacy:
        if entry.minor_version < LATEST_1X_MINOR:
            if entry is not house:
                _async_hide_aliases(hass, entry)
            hass.config_entries.async_update_entry(entry, minor_version=LATEST_1X_MINOR)
            migrated.append(f"{entry.title} 1.{LATEST_1X_MINOR}")
    _LOGGER.info(
        "Upgrade phase 1 (1.x schema): %s",
        ", ".join(migrated) if migrated else "every entry is at 1.5 already",
    )


# ------------------------------------------------------------ phase 2: plan


@dataclass(frozen=True)
class WindowPlan:
    """One window entry the upgrade moves into the house."""

    window_key: str
    title: str
    unique_id: str | None
    record: WindowRecord
    """What its subentry stores (3.1)."""
    acts_on: Mapping[str, Any]
    """Every option as v1.19.x acts on it (its flat options, its switches)."""
    provenance: Mapping[str, str]
    """Where its values come from under the house layers (the Position attribute)."""
    readopted: bool
    """Its stored overrides did not give what it acts on: adopted again."""
    entity_ids: tuple[str, ...]


@dataclass(frozen=True)
class UpgradePlan:
    """What the upgrade moves, what it leaves alone, and what stops it."""

    windows: tuple[WindowPlan, ...]
    left_alone: tuple[str, ...]
    """Disabled window entries (titles)."""
    problems: tuple[str, ...]


def _plan_window(
    hass: HomeAssistant, house: ConfigEntry, entry: ConfigEntry
) -> WindowPlan | str:
    """Plan one window (nothing written); a string says why it cannot move."""
    key = entry.entry_id
    options, acts_on, placement = _legacy(hass, house, entry)
    covers = window_covers(options)
    if len(covers) > 1:
        return f"{entry.title} drives {len(covers)} covers: split it on v1.19.x first."
    overrides = v2_0_overrides(key, entry.options)
    try:
        readopted = overrides is None or bool(
            compare(key, acts_on, house.options, overrides, placement).differing
        )
        if readopted or overrides is None:
            overrides = adopt(key, acts_on, house.options, placement)
        check = compare(key, acts_on, house.options, overrides, placement)
        record = record_from_options(
            str(entry.data.get("name") or ""),
            str(entry.data.get(CONF_SENSOR_TYPE) or SensorType.BLIND),
            options,
            overrides=overrides,
            window_key=key,
        )
    except (SettingsError, RecordError, KeyError, TypeError, ValueError) as err:
        return f"{entry.title}: its settings cannot be read ({err})."
    if check.differing:
        return f"{entry.title} would act on other values: {', '.join(check.differing)}."
    return WindowPlan(
        window_key=key,
        title=entry.title,
        unique_id=entry.unique_id,
        record=record,
        acts_on=acts_on,
        provenance=dict(check.provenance),
        readopted=readopted,
        entity_ids=tuple(sorted(row.entity_id for row in _window_rows(hass, key))),
    )


def upgrade_plan(
    hass: HomeAssistant, house: ConfigEntry, windows: list[ConfigEntry]
) -> UpgradePlan:
    """Return the dry run: every window's record and what it acts on (nothing written)."""
    from .windows import legacy_window_entries

    left_alone = tuple(
        sorted(
            entry.title
            for entry in legacy_window_entries(hass, include_disabled=True)
            if entry.disabled_by is not None
        )
    )
    if not is_lifted(house.options):
        return UpgradePlan((), left_alone, ("The house has no layered settings.",))
    plans: list[WindowPlan] = []
    problems: list[str] = []
    moving = {entry.entry_id for entry in windows}
    for subentry in house.get_subentries_of_type(WINDOW_SUBENTRY):
        # A window v2.0.x moved already: migration 3.1 must read it too.
        if subentry_window_key(subentry) in moving or not is_v2_0(subentry.data):
            continue
        try:
            record_from_v2_0(subentry.data, subentry.subentry_id)
        except RecordError as err:
            problems.append(f"{subentry.title}: {err}.")
    for entry in sorted(windows, key=lambda e: (e.title.casefold(), e.entry_id)):
        planned = _plan_window(hass, house, entry)
        if isinstance(planned, str):
            problems.append(planned)
        else:
            plans.append(planned)
    return UpgradePlan(tuple(plans), left_alone, tuple(problems))


# ------------------------------------------------------------ phase 3: snapshot


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
        "domain": row.domain,
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
    """Write the pre-upgrade snapshot once; return whether it was written."""
    from .windows import legacy_window_entries

    store: Store[dict[str, Any]] = Store(hass, SNAPSHOT_VERSION, SNAPSHOT_KEY)
    if await store.async_load() is not None:
        return False
    entries = legacy_window_entries(hass, include_disabled=True)
    ids = {entry.entry_id for entry in entries} | {house.entry_id}
    dev_reg = dr.async_get(hass)
    snapshot = {
        "created_at": SYSTEM_CLOCK.utcnow().isoformat(),
        "house": _entry_record(house),
        "windows": [_entry_record(entry) for entry in entries],
        "entities": [
            _row_record(row)
            for row in er.async_get(hass).entities.values()
            if row.platform == DOMAIN or row.config_entry_id in ids
        ],
        "devices": [
            _device_record(device)
            for entry_id in sorted(ids)
            for device in dr.async_entries_for_config_entry(dev_reg, entry_id)
        ],
        "override_store": hass.data.get(f"{DOMAIN}_manual_state", {}),
    }
    await store.async_save(_jsonable(snapshot))
    return True


# ------------------------------------------------------------ phase 4: move


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


def _house_device_id(hass: HomeAssistant, house: ConfigEntry) -> str:
    from .hub import hub_device_info

    return (
        dr.async_get(hass)
        .async_get_or_create(config_entry_id=house.entry_id, **hub_device_info())
        .id
    )


@callback
def _async_add_subentry(
    hass: HomeAssistant, house: ConfigEntry, plan: WindowPlan
) -> ConfigSubentry:
    """Add (or bring up to date) the window's subentry, keyed by its old entry_id."""
    data = plan.record.as_data()
    if (subentry := subentry_for(house, plan.window_key)) is not None:
        if dict(subentry.data) != data:
            hass.config_entries.async_update_subentry(house, subentry, data=data)
        return subentry
    unique_id = plan.unique_id
    taken = {subentry.unique_id for subentry in house.subentries.values()}
    if unique_id is not None and unique_id in taken:
        unique_id = None
    subentry = ConfigSubentry(
        data=MappingProxyType(data),
        subentry_type=WINDOW_SUBENTRY,
        title=plan.title,
        unique_id=unique_id,
    )
    hass.config_entries.async_add_subentry(house, subentry)
    return subentry


@callback
def async_reparent_window(
    hass: HomeAssistant, house: ConfigEntry, subentry_id: str, window_key: str
) -> None:
    """Move a window's entity rows, THEN its device, to the house subentry.

    Entities first: when a device changes config entry, Home Assistant
    removes the entities still on the old one. What moved is left alone.
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
            # A start after a crash: join the device that moved already.
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
    """Return what of a window is not on its house subentry yet (empty: moved)."""
    left = [
        row.entity_id
        for row in _window_rows(hass, window_key)
        if row.config_entry_id != house.entry_id
        or row.config_subentry_id != subentry_id
    ]
    dev_reg = dr.async_get(hass)
    left.extend(
        f"device {device.name}"
        for device in dr.async_entries_for_config_entry(dev_reg, window_key)
    )
    moved = dev_reg.async_get_device_by_identifier(
        (DOMAIN, window_key), config_entry_id=house.entry_id
    )
    if moved is not None and (
        moved.config_subentry_id != subentry_id
        or moved.via_device_id != _house_device_id(hass, house)
    ):
        left.append(f"device {moved.name}")
    return left


def _lost(hass: HomeAssistant, entity_ids: tuple[str, ...] | set[str]) -> list[str]:
    ent_reg = er.async_get(hass)
    return sorted(
        entity_id for entity_id in entity_ids if not ent_reg.async_get(entity_id)
    )


@callback
def async_move_window(hass: HomeAssistant, house: ConfigEntry, plan: WindowPlan) -> str:
    """Move one window into its house subentry; return the subentry_id.

    Raises
    ------
    UpgradeStopped
        A row was removed while moving (only the backup restores it).

    """
    subentry = _async_add_subentry(hass, house, plan)
    rows_before = {row.entity_id for row in _window_rows(hass, plan.window_key)}
    async_reparent_window(hass, house, subentry.subentry_id, plan.window_key)
    if lost := _lost(hass, rows_before):
        raise UpgradeStopped(
            f"{plan.title}: {len(lost)} entity row(s) were removed while moving "
            f"({', '.join(lost[:5])})",
            restore_backup=True,
        )
    return subentry.subentry_id


# ------------------------------------------------------------ phase 5: verify


def verify_window(
    hass: HomeAssistant, house: ConfigEntry, plan: WindowPlan, subentry_id: str
) -> list[str]:
    """Return what is wrong with one moved window (empty: it moved intact)."""
    from .layers import effective_settings

    problems = [
        f"{plan.title}: {entity_id} is gone"
        for entity_id in _lost(hass, plan.entity_ids)
    ]
    if left := unmoved(hass, house, subentry_id, plan.window_key):
        problems.append(f"{plan.title}: not moved: {', '.join(left[:5])}")
    try:
        effective = effective_settings(hass, WindowEntry(house, subentry_id))
    except (SettingsError, RecordError, KeyError, TypeError, ValueError) as err:
        return [*problems, f"{plan.title}: cannot be read in the house ({err})"]
    if differing := differing_keys(effective.options, plan.acts_on):
        problems.append(
            f"{plan.title} would act on other values: {', '.join(differing)}"
        )
    if effective.provenance != dict(plan.provenance):
        problems.append(f"{plan.title}: its provenance would change")
    return problems


# ------------------------------------------------------------ the undo


async def async_undo(
    hass: HomeAssistant, house: ConfigEntry, plans: tuple[WindowPlan, ...]
) -> list[str]:
    """Put every planned window back on its entry; return what could not be.

    Rows first, then the device, then the subentry goes (removing a
    subentry removes what is still on it).
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    problems: list[str] = []
    for plan in plans:
        key = plan.window_key
        if hass.config_entries.async_get_entry(key) is None:
            problems.append(f"{plan.title}: its window entry is gone")
            continue
        for row in _window_rows(hass, key):
            if row.config_entry_id != key or row.config_subentry_id is not None:
                ent_reg.async_update_entity(
                    row.entity_id, config_entry_id=key, config_subentry_id=None
                )
        moved = dev_reg.async_get_device_by_identifier(
            (DOMAIN, key), config_entry_id=house.entry_id
        )
        if moved is not None:
            dev_reg.async_update_device(
                moved.id,
                new_config_entry_id=key,
                new_config_subentry_id=None,
                via_device_id=None,
            )
        if (subentry := subentry_for(house, key)) is not None:
            hass.config_entries.async_remove_subentry(house, subentry.subentry_id)
        if lost := _lost(hass, plan.entity_ids):
            problems.append(
                f"{plan.title}: {', '.join(lost[:5])} could not be restored"
            )
        elif stray := [
            row.entity_id
            for row in _window_rows(hass, key)
            if row.config_entry_id != key
        ]:
            problems.append(f"{plan.title}: {', '.join(stray[:5])} stayed in the house")
    return problems


# ------------------------------------------------------------ the whole upgrade


@dataclass(frozen=True)
class UpgradeReport:
    """What a finished upgrade did."""

    windows: tuple[str, ...]
    """The titles of the windows moved into the house."""
    entity_count: int
    readopted: tuple[str, ...]
    left_alone: tuple[str, ...]


def _notify(hass: HomeAssistant, report: UpgradeReport) -> None:
    lines = [
        f"Adaptive Cover upgraded your {len(report.windows)} windows into one "
        f"house entry. Nothing changed: all {report.entity_count} entities kept "
        "their entity ids, names, areas and devices, and every window acts on "
        "the same settings, in the same Mode.",
        f"A snapshot of what was there is in `.storage/{SNAPSHOT_KEY}`.",
    ]
    if report.readopted:
        lines.append(
            "These windows kept the settings they acted on, which differed from "
            f"their house settings: {', '.join(report.readopted)}."
        )
    if report.left_alone:
        lines.append(
            "Disabled window entries were left as they are (you can delete "
            f"them): {', '.join(report.left_alone)}."
        )
    persistent_notification.async_create(
        hass,
        "\n\n".join(lines),
        title="Adaptive Cover 2.1: windows moved into the house",
        notification_id=NOTIFICATION_ID,
    )


@callback
def _async_raise_stopped(hass: HomeAssistant, stop: UpgradeStopped) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        STOPPED_ISSUE,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=(
            f"{STOPPED_ISSUE}_restore_backup" if stop.restore_backup else STOPPED_ISSUE
        ),
        translation_placeholders={"reason": stop.reason, "snapshot": SNAPSHOT_KEY},
    )


async def _async_consolidate(
    hass: HomeAssistant, house: ConfigEntry, windows: list[ConfigEntry]
) -> UpgradeReport:
    """Phases 1-6 (see the module docstring); raises ``UpgradeStopped``."""
    async_bring_to_1_5(hass, house, windows)
    plan = upgrade_plan(hass, house, windows)
    if plan.problems:
        raise UpgradeStopped(" ".join(plan.problems))
    _LOGGER.info(
        "Upgrade phase 2 (plan): %s window(s) move into the house, %s entities; "
        "%s adopted again; left alone: %s",
        len(plan.windows),
        sum(len(window.entity_ids) for window in plan.windows),
        [window.title for window in plan.windows if window.readopted],
        list(plan.left_alone),
    )
    for window in plan.windows:
        if window.readopted:
            _LOGGER.warning(
                "%s: its stored house settings differed from what it acts on; "
                "it keeps what it acts on",
                window.title,
            )
    written = await async_write_snapshot(hass, house)
    _LOGGER.info(
        "Upgrade phase 3 (snapshot): .storage/%s %s",
        SNAPSHOT_KEY,
        "written" if written else "kept from the first try",
    )
    moved: dict[str, str] = {}
    try:
        for window in plan.windows:
            moved[window.window_key] = async_move_window(hass, house, window)
        _LOGGER.info("Upgrade phase 4 (move): %s window(s) in the house", len(moved))
        problems = [
            problem
            for window in plan.windows
            for problem in verify_window(hass, house, window, moved[window.window_key])
        ]
        if problems:
            raise UpgradeStopped(" ".join(problems))
    except Exception as err:
        # Any failure while moving is undone (a crash, which runs no code,
        # resumes at the next start instead).
        stop = (
            err
            if isinstance(err, UpgradeStopped)
            else UpgradeStopped(f"Unexpected error while moving: {err!r}.")
        )
        left = await async_undo(hass, house, plan.windows)
        if left:
            raise UpgradeStopped(
                f"{stop.reason} The undo left: {' '.join(left)}", restore_backup=True
            ) from err
        if stop is err:
            raise
        raise stop from err
    _LOGGER.info("Upgrade phase 5 (verify): every window moved intact")
    hass.config_entries.async_update_entry(
        house, version=V2_0_HOUSE_VERSION, minor_version=1
    )
    for window in plan.windows:
        if hass.config_entries.async_get_entry(window.window_key) is not None:
            await hass.config_entries.async_remove(window.window_key)
    _LOGGER.info(
        "Upgrade phase 6 (commit): the house is 2.1; %s window entries removed",
        len(plan.windows),
    )
    return UpgradeReport(
        windows=tuple(window.title for window in plan.windows),
        entity_count=sum(len(window.entity_ids) for window in plan.windows),
        readopted=tuple(window.title for window in plan.windows if window.readopted),
        left_alone=plan.left_alone,
    )


async def async_upgrade_house(
    hass: HomeAssistant, house: ConfigEntry, windows: list[ConfigEntry]
) -> bool:
    """Move the window entries into the house, then migrate it to 3.1.

    Returns whether the house is now 3.1. A stop raises the
    ``upgrade_stopped`` repair (and logs why); the house keeps its version.
    """
    from .upgrade import MigrationRefused, async_migrate_house

    _LOGGER.info(
        "Upgrading the house from %s.%s: %s window entries move into it",
        house.version,
        house.minor_version,
        len(windows),
    )
    try:
        report = await _async_consolidate(hass, house, windows)
        await async_migrate_house(hass, house)
    except UpgradeStopped as stop:
        _LOGGER.error("The upgrade stopped; nothing was removed: %s", stop.reason)
        _async_raise_stopped(hass, stop)
        return False
    except MigrationRefused as err:
        stop = UpgradeStopped(str(err))
        _LOGGER.error("The upgrade stopped at migration 3.1: %s", err)
        _async_raise_stopped(hass, stop)
        return False
    ir.async_delete_issue(hass, DOMAIN, STOPPED_ISSUE)
    _notify(hass, report)
    _LOGGER.info(
        "Upgraded %s windows into the house (%s.%s)",
        len(report.windows),
        house.version,
        house.minor_version,
    )
    return True
