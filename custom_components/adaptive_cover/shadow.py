"""The layered settings store: the lift, adoption and toggle reads (P5).

v1.18.0 (the shadow release) wrote the layered model (house / floor /
area profiles and sparse window overrides) next to the legacy flat
options. Since the flip (``layers.py``) the runtime acts on it; this module
keeps the store complete. The pure part is ``settings/shadow.py``.

**Migration 1.4 (the lift).** ``async_migrate_hub_1_4`` runs from
``async_migrate_entry`` for the hub entry. It lifts every enabled window
(``settings/lift.py``) and stores the house, floor and area profiles in
the hub's options and each window's sparse ``overrides`` in the window's
options. The legacy flat keys are not touched. The lift reads:

- each window's options as migration 1.3 stores them
  (``migration.options_1_3``; windows may still be at 1.1 or 1.2 when
  the hub migrates), so ``legacy_flat`` is exact;
- its placement: the window device's area, else its cover's area (the
  area the device copies at setup); the floor is that area's floor;
- the states of the switches P5 drops (``read_toggles``, below).

The lift is deterministic (windows in entry_id order) and idempotent:
running it again on the same house writes the same options. A house
without windows is not lifted.

**A house that was never lifted lifts itself** (``async_ensure_lifted``):
a hub created at 1.4 or later (a new install, or one made by v1.18.0 /
v1.19.0) is lifted when it sets up, and when a window sets up while the
hub is still not lifted. Nothing changes for the windows: the lift is
exact, so they act on the same values.

**Switch states at migration time.** When the hub migrates, the window
switches are usually not set up yet (config entries set up concurrently,
and HA migrates an entry before it sets it up). Their restored state is
nevertheless known: HA loads the restore-state cache before any
integration sets up, and a switch restores from exactly that record
(``RestoreEntity.async_get_last_state`` reads
``restore_state.async_get(hass).last_states``). So ``read_toggles`` takes,
per switch, the first of:

1. the switch's initial state when the window's options do not create
   the switch (its value then changes nothing; it is what the switch
   would start with);
2. the initial state when the switch is not in the entity registry (a
   window that never ran: the switch will start there);
3. what the runtime uses without the switch when its entity is disabled;
4. the live state, when the switch is up (``on`` / ``off``);
5. the restore cache: ``on`` restores on, any other stored state off
   (the switch's own rule);
6. the initial state when nothing was stored.

The same reader gives a window that is not lifted yet its toggles
(``layers.effective_options``).

**Adoption.** ``async_setup_window`` (window setup, before its
coordinator) records the window, lifts the house if needed, and adopts a
window without ``overrides`` of its own (added after the lift, or a copy
of another window; ``settings.shadow.adopt``): every value it does not
inherit becomes a window override.

**The settings_differ repair is retired** (P5 flip): with the runtime on
the layers there is no second set of values to compare. Setup deletes an
issue left over from v1.18.x / v1.19.x.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import restore_state

from .const import _LOGGER, DOMAIN
from .entity_surface import cover_area_id
from .migration import options_1_3
from .settings.lift import LegacyWindow, Lifted
from .settings.normalize import window_covers
from .settings.resolve import Placement, SettingsError
from .settings.shadow import (
    OVERRIDES,
    TOGGLE_SWITCHES,
    ToggleSwitch,
    adopt,
    hub_options,
    is_lifted,
    legacy_values,
    lift_house,
    overrides_option,
    stored_overrides,
    without_overrides,
)

SHADOW_DATA: Final = f"{DOMAIN}_shadow"
DIFF_ISSUE: Final = "settings_differ"
"""The retired v1.18.x repair issue (deleted at setup)."""


def diff_issue_id(entry_id: str) -> str:
    """Return the retired ``settings_differ`` repair issue id of one window."""
    return f"{DIFF_ISSUE}_{entry_id}"


@dataclass
class _Window:
    """What the store keeps for one set-up window."""

    options: dict[str, Any]
    """The options (with ``overrides``) the window's runtime was set up with."""
    data: dict[str, Any]
    title: str


def _windows(hass: HomeAssistant) -> dict[str, _Window]:
    return hass.data.setdefault(SHADOW_DATA, {})


def _is_hub(entry: ConfigEntry) -> bool:
    from .hub import is_hub_entry

    return is_hub_entry(entry)


def _hub(hass: HomeAssistant) -> ConfigEntry | None:
    return next(
        (e for e in hass.config_entries.async_entries(DOMAIN) if _is_hub(e)), None
    )


def lifted_hub(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the hub entry when it stores lifted layers."""
    hub = _hub(hass)
    return hub if hub is not None and is_lifted(hub.options) else None


def window_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return the enabled window entries (the hub is not a window)."""
    return [
        entry
        for entry in hass.config_entries.async_entries(
            DOMAIN, include_ignore=False, include_disabled=False
        )
        if not _is_hub(entry)
    ]


def runtime_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return a window's options as the runtime reads them (1.3 shape)."""
    return options_1_3(without_overrides(entry.options))


# ------------------------------------------------------------ inputs


def _switch_state(
    hass: HomeAssistant,
    entry_id: str,
    switch: ToggleSwitch,
    options: Mapping[str, Any],
) -> bool:
    """Return one toggle's switch state (rules 1-6 in the module docstring)."""
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
    """Return the states of a window's dropped switches, by toggle key."""
    return {
        switch.key: _switch_state(hass, entry_id, switch, options)
        for switch in TOGGLE_SWITCHES
    }


@callback
def window_placement(hass: HomeAssistant, entry: ConfigEntry) -> Placement:
    """Return the window's area (its device's, else its cover's) and floor."""
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), config_entry_id=entry.entry_id
    )
    area_id = device.area_id if device is not None else None
    if area_id is None:
        area_id = cover_area_id(hass, window_covers(entry.options))
    area = ar.async_get(hass).async_get_area(area_id) if area_id else None
    if area is None:
        return Placement()
    return Placement(area_id=area.id, floor_id=area.floor_id)


def _legacy(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    options = runtime_options(entry)
    return legacy_values(
        options,
        read_toggles(hass, entry.entry_id, options),
        temperature_unit=hass.config.units.temperature_unit,
    )


# ------------------------------------------------------------ the lift


@callback
def async_lift_house(hass: HomeAssistant, hub: ConfigEntry) -> Lifted | None:
    """Lift every enabled window into the hub's layers; store both sides.

    Returns the lift (None: no windows, nothing stored).
    """
    windows = window_entries(hass)
    if not windows:
        return None
    unit = hass.config.units.temperature_unit
    lifted = lift_house(
        [
            LegacyWindow(
                window_key=entry.entry_id,
                options=_legacy(hass, entry),
                area_id=window_placement(hass, entry).area_id,
            )
            for entry in windows
        ],
        {area.id: area.floor_id for area in ar.async_get(hass).async_list_areas()},
        [floor.floor_id for floor in fr.async_get(hass).async_list_floors()],
        temperature_unit=unit,
    )
    hass.config_entries.async_update_entry(
        hub, options={**hub.options, **hub_options(lifted)}
    )
    for entry in windows:
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                OVERRIDES: overrides_option(
                    entry.entry_id, lifted.overrides[entry.entry_id]
                ),
            },
        )
    _LOGGER.info(
        "Lifted %s window(s) into the layered settings: %s floor and %s area "
        "profile(s), %s window(s) with overrides, %s with legacy values",
        len(windows),
        len(lifted.floors),
        len(lifted.areas),
        sum(1 for o in lifted.overrides.values() if o.values),
        sum(1 for o in lifted.overrides.values() if o.legacy),
    )
    return lifted


@callback
def async_ensure_lifted(hass: HomeAssistant) -> None:
    """Lift the house if its hub exists and was never lifted (a new install).

    A lift that fails leaves the house un-lifted (logged); the windows keep
    acting on their legacy options.
    """
    hub = _hub(hass)
    if hub is None or is_lifted(hub.options):
        return
    try:
        async_lift_house(hass, hub)
    except (SettingsError, ValueError, TypeError):
        _LOGGER.exception("Could not lift the windows into the layered settings")


@callback
def async_migrate_hub_1_4(hass: HomeAssistant, hub: ConfigEntry) -> None:
    """Migrate the hub to 1.4: store the lifted layers, then bump the version.

    A house that is already lifted (a window lifted it while the hub was
    disabled) is left alone: a second lift would rebuild the layers from
    the legacy keys and lose every edit made since the flip. A lift that
    fails leaves the hub un-lifted (logged); its windows keep acting on
    their legacy options.
    """
    async_ensure_lifted(hass)
    hass.config_entries.async_update_entry(hub, minor_version=4)


# ------------------------------------------------------------ adoption


@callback
def async_setup_window(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Record a window at setup, before its coordinator reads the layers.

    Lifts the house if it never was, adopts the window if it has no
    overrides of its own, and deletes a retired ``settings_differ`` issue.
    """
    ir.async_delete_issue(hass, DOMAIN, diff_issue_id(entry.entry_id))
    async_ensure_lifted(hass)
    async_adopt_window(hass, entry)
    _windows(hass)[entry.entry_id] = _Window(
        options=dict(entry.options), data=dict(entry.data), title=entry.title
    )


@callback
def async_adopt_window(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Give a window without its own ``overrides`` the ones it needs.

    Every value it does not inherit becomes a window override (or a legacy
    value where no window may override it), so it acts as before.
    """
    hub = lifted_hub(hass)
    if hub is None or stored_overrides(entry.entry_id, entry.options) is not None:
        return
    try:
        overrides = adopt(
            entry.entry_id,
            _legacy(hass, entry),
            hub.options,
            window_placement(hass, entry),
        )
    except (SettingsError, KeyError, TypeError) as err:
        _LOGGER.warning("%s: cannot join the layered settings: %s", entry.title, err)
        return
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            OVERRIDES: overrides_option(entry.entry_id, overrides),
        },
    )
    if (record := _windows(hass).get(entry.entry_id)) is not None:
        record.options = dict(entry.options)
    _LOGGER.info(
        "%s joined the layered settings: overrides %s, legacy values %s",
        entry.title,
        sorted(overrides.values),
        sorted(overrides.legacy),
    )


def only_overrides_changed(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return whether an entry update left everything the runtime reads alone.

    True when the window's data, title and options (``overrides`` aside)
    are the ones it was set up with: the update wrote only ``overrides``
    (the lift, an adoption or a recurring edit), which the runtime reads
    on every refresh, so it needs no reload (the update listener refreshes
    it instead).
    """
    record = _windows(hass).get(entry.entry_id)
    if record is None or dict(entry.data) != record.data or entry.title != record.title:
        return False
    if without_overrides(entry.options) != without_overrides(record.options):
        return False
    record.options = dict(entry.options)
    return True


@callback
def async_unload_window(hass: HomeAssistant, entry_id: str) -> None:
    """Forget an unloaded window."""
    _windows(hass).pop(entry_id, None)
