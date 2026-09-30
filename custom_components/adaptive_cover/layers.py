"""The layered settings at runtime (ADR 0003).

A window acts on its **resolved** settings: each recurring option comes
from the first of the window's own override, its area, its floor, the
house and the spec default (``settings/resolve.py``); each one-time option
from the window's own ``geometry``. The house, floor and area profiles
live in the house entry's options (``house``, ``floors``, ``areas``,
``temperature_unit``); each window's sparse ``overrides`` in its subentry
(``settings/window_record.py``).

**Reads.** ``effective_options`` is what the runtime reads, as one flat
dict with every option key (and the five toggle keys: ``climate_on``,
``use_outside_temp``, ``use_lux``, ``use_irradiance``,
``manual_detection``). It is computed on every refresh, so a change to any
layer (the house, the window's overrides, the window's area) reaches the
window at its next refresh.

**Writes.** ``window_record_after`` / ``async_write_window`` store a
window's edits: one-time keys in its geometry (the cover as its cover),
recurring keys in its ``overrides``, sparsely: a value equal to what the
window would inherit, or ``None`` (a cleared field), removes the override.
A recurring key a window may override (``overridable_at`` has the window)
goes to ``values``; any other goes to ``legacy``, which ``resolve`` also
reads first (the lift's bucket for the same thing: a per-window value no
allowed level can hold). ``async_set_profile`` stores the house, a floor's
or an area's values, checked against the levels the spec allows.

**New windows.** ``new_window_record`` gives a new window the overrides it
needs to act on the values it was created with (the form's or the
service's): every value it does not inherit becomes a window override
(``settings.shadow.adopt``). ``initial_house_options`` is the house of a
fresh install: its first window, lifted.

**Propagation.** ``async_settings_changed`` tells every window (or some)
to re-read its settings and act on them now, without a reload. A window
whose change needs new entities or listeners (``SETUP_KEYS``) rebuilds
itself (the coordinator compares them on each refresh).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    _LOGGER,
    CONF_COVER_ENTITY,
    CONF_END_ENTITY,
    CONF_ENTITIES,
    CONF_IGNORE_CLIMATE,
    CONF_IRRADIANCE_ENTITY,
    CONF_LUX_ENTITY,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_PRESENCE_ENTITY,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)
from .entity_surface import cover_area_id
from .runtime.shade_config import absent_options
from .settings.lift import LegacyWindow, same_value
from .settings.resolve import (
    Placement,
    WindowOverrides,
    allowed_levels,
    resolve,
    resolve_with_provenance,
    spec_by_key,
)
from .settings.schema import may_be_empty
from .settings.shadow import (
    AREAS,
    FLOORS,
    HOUSE,
    SHADOW_SPEC,
    adopt,
    hub_options,
    legacy_values,
    lift_house,
    provenance_summary,
    stored_profiles,
)
from .settings.spec import OPTS_BY_KEY, Level, Opt, Scope
from .settings.window_record import GEOMETRY_KEYS, WindowRecord, record_from_options
from .windows import WindowEntry, async_update_window, house_entry, window_device

SIGNAL_SETTINGS_CHANGED: Final = f"{DOMAIN}_settings_changed"
"""Dispatcher signal: a layer changed (the house entities re-read it)."""

SPEC: Final[Mapping[str, Opt]] = spec_by_key(SHADOW_SPEC)

# Options a window reads only when it sets up: the entities it listens to
# and the ones that decide which entities it has, or whether it can run
# climate control (the temperature sources and ignore_climate). A change
# rebuilds it.
SETUP_KEYS: Final = (
    CONF_IGNORE_CLIMATE,
    CONF_TEMP_ENTITY,
    CONF_PRESENCE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_END_ENTITY,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_LUX_ENTITY,
    CONF_IRRADIANCE_ENTITY,
)

# The window placeholder key a record is adopted under before its
# subentry (and so its key) exists; nothing stores it.
_NEW_WINDOW: Final = "new-window"


class Where(StrEnum):
    """Where a window stores its value of an option."""

    OPTIONS = "options"
    """One-time (and internal) options: the window's geometry."""
    VALUES = "values"
    """A recurring option the spec lets a window override."""
    LEGACY = "legacy"
    """A recurring option no window may override: a per-window exception."""


def where(key: str) -> Where:
    """Return where a window stores ``key`` (see ``Where``)."""
    opt = SPEC[key]
    if opt.scope is not Scope.RECURRING:
        return Where.OPTIONS
    if Level.WINDOW in opt.overridable_at:
        return Where.VALUES
    return Where.LEGACY


def _unit(hass: HomeAssistant) -> str:
    return hass.config.units.temperature_unit


def _placement(hass: HomeAssistant, area_id: str | None) -> Placement:
    area = ar.async_get(hass).async_get_area(area_id) if area_id else None
    if area is None:
        return Placement()
    return Placement(area_id=area.id, floor_id=area.floor_id)


@callback
def window_placement(hass: HomeAssistant, window: WindowEntry) -> Placement:
    """Return the window's area (its device's, else its cover's) and floor."""
    device = window_device(hass, window)
    area_id = device.area_id if device is not None else None
    if area_id is None:
        area_id = cover_area_id(hass, window.covers)
    return _placement(hass, area_id)


def runtime_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return one-time options as the runtime reads them (fallbacks written)."""
    return {**options, **absent_options(options)}


def _setup_values(hass: HomeAssistant, options: Mapping[str, Any]) -> dict[str, Any]:
    """Return every option as ``options`` hold it (``stored_profiles`` takes the setup)."""
    return legacy_values(options, {}, temperature_unit=_unit(hass))


@dataclass(frozen=True)
class Effective:
    """What a window acts on, and where its values come from."""

    options: dict[str, Any]
    """Every option key (and the toggle keys), resolved."""
    provenance: dict[str, str]
    """The Position attribute: options from an area, a floor, a window
    override or a legacy value (``provenance_summary``)."""
    sources: dict[str, str]
    """Where every option comes from (``window``, ``legacy``, ``area``,
    ``floor``, ``house``, ``default``)."""


def effective_settings(hass: HomeAssistant, window: WindowEntry) -> Effective:
    """Return what the window acts on, resolved, with the provenance.

    Raises
    ------
    SettingsError
        A stored layer holds a value where the spec does not allow it.

    """
    options = runtime_options(window.options)
    resolution = resolve_with_provenance(
        window.window_key,
        stored_profiles(
            window.window_key,
            window.config_entry.options,
            window.overrides,
            _setup_values(hass, options),
            window_placement(hass, window),
        ),
        SHADOW_SPEC,
    )
    return Effective(
        {**options, **resolution.values},
        provenance_summary(resolution, SHADOW_SPEC),
        {key: source.value for key, source in resolution.provenance.items()},
    )


def effective_options(hass: HomeAssistant, window: WindowEntry) -> dict[str, Any]:
    """Return what the window acts on: every option key, resolved."""
    return effective_settings(hass, window).options


def inherited_values(hass: HomeAssistant, window: WindowEntry) -> dict[str, Any]:
    """Return what the window would get without its own recurring values."""
    options = runtime_options(window.options)
    return resolve(
        window.window_key,
        stored_profiles(
            window.window_key,
            window.config_entry.options,
            WindowOverrides(),
            _setup_values(hass, options),
            window_placement(hass, window),
        ),
        SHADOW_SPEC,
    )


def window_overrides(window: WindowEntry) -> WindowOverrides:
    """Return the window's stored overrides."""
    return window.overrides


def window_record_after(
    hass: HomeAssistant, window: WindowEntry, changes: Mapping[str, Any]
) -> WindowRecord:
    """Return the window's record with ``changes`` stored (nothing written).

    One-time keys go to the geometry (the cover keys to the cover).
    Recurring keys go to the window's overrides, sparsely: ``None`` or a
    value equal to what the window inherits removes the override.
    """
    record = window.record
    inherited = inherited_values(hass, window)
    geometry = dict(record.geometry)
    cover = record.cover
    values = dict(record.overrides.values)
    legacy = dict(record.overrides.legacy)
    for key, value in changes.items():
        if key == CONF_COVER_ENTITY:
            cover = value or None
            continue
        if key == CONF_ENTITIES:
            cover = value[0] if value else None
            continue
        place = where(key) if key in SPEC else Where.OPTIONS
        if place is Where.OPTIONS:
            if key in GEOMETRY_KEYS:
                geometry[key] = value
            continue
        values.pop(key, None)
        legacy.pop(key, None)
        if value is None or same_value(value, inherited[key]):
            continue  # inherit
        (values if place is Where.VALUES else legacy)[key] = value
    return record.with_changes(
        cover=cover,
        geometry=geometry,
        overrides=WindowOverrides(values=values, legacy=legacy),
    )


@callback
def async_write_window(
    hass: HomeAssistant, window: WindowEntry, changes: Mapping[str, Any]
) -> None:
    """Store a window's edits (see ``window_record_after``)."""
    async_update_window(hass, window, window_record_after(hass, window, changes))


def copied_options(hass: HomeAssistant, source: WindowEntry) -> dict[str, Any]:
    """Return the options a copy of ``source`` starts from: what it acts on."""
    return {
        key: value
        for key, value in effective_options(hass, source).items()
        if key in OPTS_BY_KEY
    }


def new_window_values(hass: HomeAssistant) -> dict[str, Any]:
    """Return the house's recurring values: what a new window starts from."""
    house = house_entry(hass)
    if house is None:
        return {}
    return {
        key: value
        for key, value in profile_values(house.options, Level.HOUSE, None).items()
        if key in OPTS_BY_KEY
    }


def _areas_and_floors(hass: HomeAssistant) -> tuple[dict[str, str | None], list[str]]:
    return (
        {area.id: area.floor_id for area in ar.async_get(hass).async_list_areas()},
        [floor.floor_id for floor in fr.async_get(hass).async_list_floors()],
    )


def new_window_record(
    hass: HomeAssistant,
    house: ConfigEntry,
    name: str,
    cover_type: str,
    options: Mapping[str, Any],
) -> WindowRecord:
    """Return a new window's record: its geometry and the overrides it needs.

    ``options`` are the flat values the window is created with (a form's
    or a service's, recurring ones included). Every recurring value the
    window would not inherit at its cover's area becomes a window override
    (a legacy value where no window may override it), so it acts on the
    values it was created with.
    """
    record = record_from_options(name, cover_type, options)
    placement = _placement(hass, cover_area_id(hass, record.covers))
    legacy = _setup_values(hass, runtime_options(options))
    overrides = adopt(_NEW_WINDOW, legacy, house.options, placement)
    return record.with_changes(overrides=overrides)


def initial_house_options(
    hass: HomeAssistant, cover_type: str, options: Mapping[str, Any]
) -> tuple[dict[str, Any], WindowOverrides]:
    """Return a fresh install's house options and its first window's overrides.

    The first window is lifted (``settings/lift.py``): the house gets its
    recurring values, so a later change of a spec default cannot move it.
    """
    record = record_from_options("", cover_type, options)
    areas, floors = _areas_and_floors(hass)
    lifted = lift_house(
        [
            LegacyWindow(
                window_key=_NEW_WINDOW,
                options=_setup_values(hass, runtime_options(options)),
                area_id=cover_area_id(hass, record.covers),
            )
        ],
        areas,
        floors,
        temperature_unit=_unit(hass),
    )
    return hub_options(lifted), lifted.overrides[_NEW_WINDOW]


# ------------------------------------------------------------ profiles


class ProfileError(ValueError):
    """A profile write the spec or the registries do not allow."""


def check_scope(hass: HomeAssistant, level: Level, scope_id: str | None) -> None:
    """Raise ``ProfileError`` unless ``scope_id`` names a profile of ``level``.

    The house takes no id; a floor or an area needs one that HA's
    registries know.
    """
    if level is Level.HOUSE:
        if scope_id is not None:
            raise ProfileError("the house takes no id")
        return
    if not scope_id:
        raise ProfileError(f"a {level} needs its id")
    if level is Level.FLOOR:
        if fr.async_get(hass).async_get_floor(scope_id) is None:
            raise ProfileError(f"no floor {scope_id!r}")
    elif level is Level.AREA:
        if ar.async_get(hass).async_get_area(scope_id) is None:
            raise ProfileError(f"no area {scope_id!r}")
    else:
        raise ProfileError(f"profiles are house, floor or area, not {level}")


def check_profile_keys(level: Level, keys: Iterable[str]) -> None:
    """Raise ``ProfileError`` for keys the spec does not let ``level`` store."""
    wrong = sorted(
        key
        for key in keys
        if key not in SPEC
        or SPEC[key].scope is not Scope.RECURRING
        or level not in allowed_levels(SPEC[key])
    )
    if wrong:
        raise ProfileError(
            f"not settable on a {level}: {', '.join(wrong)} (the spec's "
            "home and overridable_at levels decide)"
        )


def profile_values(
    hub_options: Mapping[str, Any], level: Level, scope_id: str | None
) -> dict[str, Any]:
    """Return what one profile stores (sparse for a floor or an area)."""
    if level is Level.HOUSE:
        return dict(hub_options.get(HOUSE) or {})
    bucket = FLOORS if level is Level.FLOOR else AREAS
    return dict((hub_options.get(bucket) or {}).get(scope_id or "", {}))


@callback
def async_set_profile(
    hass: HomeAssistant,
    level: Level,
    scope_id: str | None,
    changes: Mapping[str, Any],
) -> list[str]:
    """Store house, floor or area values; return the keys stored differently.

    A floor or area value ``None`` removes it (the rooms inherit again); a
    house value is stored as given. Every window re-reads its settings.

    Raises
    ------
    ProfileError
        There is no house, the floor or area does not exist, or a key
        cannot be stored at ``level``.

    """
    house = house_entry(hass)
    if house is None:
        raise ProfileError("there is no house entry")
    check_scope(hass, level, scope_id)
    check_profile_keys(level, changes)
    if level is Level.HOUSE:
        empty = sorted(
            key
            for key, value in changes.items()
            if value is None and not may_be_empty(SPEC[key])
        )
        if empty:
            raise ProfileError(f"the house needs a value for: {', '.join(empty)}")
    current = profile_values(house.options, level, scope_id)
    stored = dict(current)
    for key, value in changes.items():
        if value is None and level is not Level.HOUSE:
            stored.pop(key, None)
        else:
            stored[key] = value
    changed = sorted(
        key
        for key in changes
        if (key in stored) != (key in current)
        or (key in stored and not same_value(stored[key], current[key]))
    )
    if not changed:
        return []
    options = dict(house.options)
    if level is Level.HOUSE:
        options[HOUSE] = stored
    else:
        bucket = FLOORS if level is Level.FLOOR else AREAS
        profiles = dict(options.get(bucket) or {})
        if stored:
            profiles[scope_id or ""] = stored
        else:
            profiles.pop(scope_id or "", None)
        options[bucket] = profiles
    hass.config_entries.async_update_entry(house, options=options)
    _LOGGER.info("%s profile %s: set %s", level, scope_id or "", changed)
    return changed


async def async_settings_changed(
    hass: HomeAssistant, window_keys: Iterable[str] | None = None
) -> None:
    """Let windows (default: all) act on their settings now, without a reload."""
    from .house import window_coordinators

    wanted = set(window_keys) if window_keys is not None else None
    async_dispatcher_send(hass, SIGNAL_SETTINGS_CHANGED)
    for window_key, coordinator in window_coordinators(hass).items():
        if wanted is not None and window_key not in wanted:
            continue
        await coordinator.async_settings_changed()
