"""The layered settings at runtime (P5 flip; ADR 0003).

Since the flip a window acts on its **resolved** settings: each recurring
option comes from the first of the window's own override, its area, its
floor, the house and the spec default (``settings/resolve.py``); each
one-time option from the window's own options. The stored layers are the
ones the P5 shadow release lifted (``shadow.py``): the house, floor and
area profiles in the hub entry's options, and each window's sparse
``overrides`` (``{window_key, values, legacy}``) in its own options.

**Reads.** ``effective_options`` is what the runtime reads, as one flat
dict with every option key (and the five toggle keys that replaced the
per-window switches: ``climate_on``, ``use_outside_temp``, ``use_lux``,
``use_irradiance``, ``manual_detection``). It is computed on every
refresh, so a change to any layer (the hub, the window's overrides, the
window's area) reaches the window at its next refresh. Until the house is
lifted (no hub entry yet, or a lift that failed) a window acts on its
legacy flat options and switch states, exactly as before the flip.

**Writes.** ``async_write_window`` stores a window's edits: one-time keys
in its options (as before), recurring keys in its ``overrides`` -- sparse:
a value equal to what the window would inherit, or ``None`` (a cleared
field), removes the override. A recurring key a window may override
(``overridable_at`` has the window) goes to ``values``; any other goes to
``legacy``, which ``resolve`` also reads first (the lift's bucket for the
same thing: a per-window value no allowed level can hold).
``async_set_profile`` stores the house, a floor's or an area's values,
checked against the levels the spec allows.

**Propagation.** ``async_settings_changed`` tells every window (or some)
to re-read its settings and act on them now, without a reload. A window
whose change needs new entities or listeners (``SETUP_KEYS``) reloads
itself (the coordinator compares them on each refresh).

**Rollback.** The legacy flat keys are never deleted and, after the flip,
no longer read or written: a downgrade to v1.18.x reads them again, i.e.
the settings as they were at the lift. Edits made after the flip live only
in the layers and do not reach a downgraded install.
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
    CONF_CLIMATE_MODE,
    CONF_END_ENTITY,
    CONF_IRRADIANCE_ENTITY,
    CONF_LUX_ENTITY,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_PRESENCE_ENTITY,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)
from .settings.lift import same_value
from .settings.resolve import (
    SettingsError,
    WindowOverrides,
    allowed_levels,
    resolve,
    resolve_with_provenance,
    spec_by_key,
)
from .settings.shadow import (
    AREAS,
    FLOORS,
    HOUSE,
    OVERRIDES,
    SHADOW_SPEC,
    legacy_values,
    overrides_option,
    provenance_summary,
    stored_overrides,
    stored_profiles,
)
from .settings.spec import OPTS_BY_KEY, Level, Opt, Scope
from .shadow import lifted_hub, read_toggles, runtime_options, window_placement

SIGNAL_SETTINGS_CHANGED: Final = f"{DOMAIN}_settings_changed"
"""Dispatcher signal: a layer changed (the house entities re-read it)."""

SPEC: Final[Mapping[str, Opt]] = spec_by_key(SHADOW_SPEC)

# Options a window reads only when it sets up: the entities it listens to
# and the ones that decide which entities it has. A change reloads it.
SETUP_KEYS: Final = (
    CONF_CLIMATE_MODE,
    CONF_TEMP_ENTITY,
    CONF_PRESENCE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_END_ENTITY,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_LUX_ENTITY,
    CONF_IRRADIANCE_ENTITY,
)


class Where(StrEnum):
    """Where a window stores its value of an option."""

    OPTIONS = "options"
    """One-time (and internal) options: the window's own entry options."""
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


def _setup_values(hass: HomeAssistant, options: Mapping[str, Any]) -> dict[str, Any]:
    """Return the window's legacy values (``stored_profiles`` takes its setup)."""
    return legacy_values(options, {}, temperature_unit=_unit(hass))


def _legacy_effective(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return what a window acts on before the house is lifted (pre-flip reads)."""
    options = runtime_options(entry)
    return {
        **options,
        **legacy_values(
            options,
            read_toggles(hass, entry.entry_id, options),
            temperature_unit=_unit(hass),
        ),
    }


@dataclass(frozen=True)
class Effective:
    """What a window acts on, and where its values come from."""

    options: dict[str, Any]
    """Every option key (and the toggle keys), resolved."""
    provenance: dict[str, str] | None
    """The Position attribute: options from an area, a floor, a window
    override or a legacy value (``provenance_summary``); None before the
    house is lifted."""


def effective_settings(hass: HomeAssistant, entry: ConfigEntry) -> Effective:
    """Return what the window acts on, resolved, with the provenance.

    Before the house is lifted, or when a stored layer is invalid (logged),
    the legacy flat options and the switch states.
    """
    hub = lifted_hub(hass)
    overrides = (
        stored_overrides(entry.entry_id, entry.options) if hub is not None else None
    )
    if hub is None or overrides is None:
        return Effective(_legacy_effective(hass, entry), None)
    options = runtime_options(entry)
    try:
        resolution = resolve_with_provenance(
            entry.entry_id,
            stored_profiles(
                entry.entry_id,
                hub.options,
                overrides,
                _setup_values(hass, options),
                window_placement(hass, entry),
            ),
            SHADOW_SPEC,
        )
    except (SettingsError, KeyError, TypeError) as err:
        _LOGGER.error(
            "%s: the layered settings are invalid (%s); acting on the legacy "
            "options until they are fixed",
            entry.title,
            err,
        )
        return Effective(_legacy_effective(hass, entry), None)
    return Effective(
        {**options, **resolution.values}, provenance_summary(resolution, SHADOW_SPEC)
    )


def effective_options(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return what the window acts on: every option key, resolved."""
    return effective_settings(hass, entry).options


def inherited_values(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return what the window would get without its own recurring values."""
    hub = lifted_hub(hass)
    if hub is None:
        return _legacy_effective(hass, entry)
    options = runtime_options(entry)
    return resolve(
        entry.entry_id,
        stored_profiles(
            entry.entry_id,
            hub.options,
            WindowOverrides(),
            _setup_values(hass, options),
            window_placement(hass, entry),
        ),
        SHADOW_SPEC,
    )


def is_layered(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return whether the window acts on the layers (lifted, with its overrides)."""
    return (
        lifted_hub(hass) is not None
        and stored_overrides(entry.entry_id, entry.options) is not None
    )


def window_overrides(entry: ConfigEntry) -> WindowOverrides:
    """Return the window's stored overrides (empty when it has none)."""
    return stored_overrides(entry.entry_id, entry.options) or WindowOverrides()


def window_options_after(
    hass: HomeAssistant, entry: ConfigEntry, changes: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the window's options with ``changes`` stored (nothing written).

    One-time keys go to the options. Recurring keys go to the window's
    overrides, sparsely: ``None`` or a value equal to what the window
    inherits removes the override. Before the house is lifted every key
    goes to the options, as before the flip; so it does while the stored
    layers are invalid (the window then acts on its legacy options). The
    legacy flat keys of recurring options are left as they are (a
    downgrade reads them).
    """
    options = dict(entry.options)
    if not is_layered(hass, entry):
        options.update(changes)
        return options
    try:
        inherited = inherited_values(hass, entry)
    except (SettingsError, KeyError, TypeError):
        options.update(changes)
        return options
    stored = window_overrides(entry)
    values = dict(stored.values)
    legacy = dict(stored.legacy)
    for key, value in changes.items():
        place = where(key) if key in SPEC else Where.OPTIONS
        if place is Where.OPTIONS:
            options[key] = value
            continue
        values.pop(key, None)
        legacy.pop(key, None)
        if value is None or same_value(value, inherited[key]):
            continue  # inherit
        (values if place is Where.VALUES else legacy)[key] = value
    options[OVERRIDES] = overrides_option(
        entry.entry_id, WindowOverrides(values=values, legacy=legacy)
    )
    return options


@callback
def async_write_window(
    hass: HomeAssistant, entry: ConfigEntry, changes: Mapping[str, Any]
) -> None:
    """Store a window's edits (see ``window_options_after``)."""
    hass.config_entries.async_update_entry(
        entry, options=window_options_after(hass, entry, changes)
    )


def copied_options(hass: HomeAssistant, source: ConfigEntry) -> dict[str, Any]:
    """Return the options a copy of ``source`` starts from: what it acts on."""
    return {
        key: value
        for key, value in effective_options(hass, source).items()
        if key in OPTS_BY_KEY
    }


def new_window_values(hass: HomeAssistant) -> dict[str, Any]:
    """Return the house's recurring values: what a new window starts from."""
    hub = lifted_hub(hass)
    if hub is None:
        return {}
    return {
        key: value
        for key, value in profile_values(hub.options, Level.HOUSE, None).items()
        if key in OPTS_BY_KEY
    }


# ------------------------------------------------------------ profiles


class ProfileError(ValueError):
    """A profile write the spec or the registries do not allow."""


def _check_scope(hass: HomeAssistant, level: Level, scope_id: str | None) -> None:
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
        The house is not lifted, the floor or area does not exist, or a key
        cannot be stored at ``level``.

    """
    hub = lifted_hub(hass)
    if hub is None:
        raise ProfileError("the house has no layered settings yet")
    _check_scope(hass, level, scope_id)
    check_profile_keys(level, changes)
    current = profile_values(hub.options, level, scope_id)
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
    options = dict(hub.options)
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
    hass.config_entries.async_update_entry(hub, options=options)
    _LOGGER.info("%s profile %s: set %s", level, scope_id or "", changed)
    return changed


async def async_settings_changed(
    hass: HomeAssistant, entry_ids: Iterable[str] | None = None
) -> None:
    """Let windows (default: all) act on their settings now, without a reload."""
    from .coordinator import AdaptiveDataUpdateCoordinator

    wanted = set(entry_ids) if entry_ids is not None else None
    async_dispatcher_send(hass, SIGNAL_SETTINGS_CHANGED)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if wanted is not None and entry.entry_id not in wanted:
            continue
        coordinator = getattr(entry, "runtime_data", None)
        if isinstance(coordinator, AdaptiveDataUpdateCoordinator):
            await coordinator.async_settings_changed()
