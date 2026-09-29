"""The layered settings store (P5): the pure part.

The P5 shadow release (v1.18.0) stored the layered model next to the
legacy flat options; since the flip the runtime acts on it
(``../layers.py``). ``../shadow.py`` does the Home Assistant side of the
store (registries, restore state, the lift at migration and at setup);
this module holds everything that is a function of its inputs:

- **Toggles.** The per-window switches P5 drops become recurring
  settings (``TOGGLE_OPTS``; plan: "Climate on/off", the outside temp /
  lux / irradiance "use-flags", "Manual-move detection"). They are not in
  ``spec.OPTS``, so no window form shows them; ``SHADOW_SPEC`` is the
  spec the lift, the stored profiles and the runtime resolve with.
  ``TOGGLE_SWITCHES`` says which switch feeds each toggle and when a
  window has that switch (the same conditions as ``switch.py``).
- **Legacy values.** ``legacy_values`` is what a window acts on today:
  its options (after migration 1.3 every fallback is written) plus its
  switch states.
- **Storage.** The hub entry's options get ``house``, ``floors``,
  ``areas`` and ``temperature_unit`` (``hub_options``); each window entry's
  options get ``overrides`` = ``{"window_key", "values", "legacy"}``
  (``overrides_option``). A window's one-time settings are not copied: in
  v1.18.0 they stay in the flat options, and ``stored_profiles`` reads them
  from there. ``overrides`` names the window it was lifted for, so a copy
  (``add_entry`` with ``copy_from``, a split) is not mistaken for the new
  window's own.
- **Comparison.** ``compare`` resolves one window from the stored layers
  and lists every option whose value differs from ``legacy_values``
  (the lift's equality: 30 == 30.0, True != 1). The v1.18.x repair issue
  used it; now it checks that a lift or an adoption is exact.
- **Adoption.** A window that has no ``overrides`` of its own (created
  after the lift) is lifted alone against the stored layers
  (``adopt``): every value it does not inherit becomes a window override
  where the spec allows one, else a ``legacy`` value, as in the lift.
- **Provenance.** ``provenance_summary`` keeps the Position sensor's
  ``provenance`` attribute small: only options that do not come from the
  house (or the spec default) and are not one-time window settings, i.e.
  the area, floor, window-override and legacy values.

Pure: no Home Assistant imports and no clock reads.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from ..const import (
    CONF_CLIMATE_MODE,
    CONF_CLIMATE_ON,
    CONF_ENTITIES,
    CONF_IRRADIANCE_ENTITY,
    CONF_LUX_ENTITY,
    CONF_MANUAL_DETECTION,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_USE_IRRADIANCE,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
    CONF_WEATHER_ENTITY,
)
from .lift import LegacyWindow, Lifted, legacy_flat, lift, same_value
from .resolve import (
    AreaProfile,
    FloorProfile,
    HouseProfile,
    Placement,
    Profiles,
    Resolution,
    Source,
    WindowOverrides,
    resolve,
    resolve_with_provenance,
    spec_by_key,
)
from .spec import OPTS, Group, Kind, Level, Opt, Scope

# ------------------------------------------------------------ toggles

# fmt: off
TOGGLE_OPTS: Final[tuple[Opt, ...]] = (
    # The "Climate Mode" switch: climate control on or off (with the
    # climate_mode option; the switch exists only when that option is on).
    Opt(CONF_CLIMATE_ON, Kind.INTERNAL, Group.NONE, Scope.RECURRING,
        Level.HOUSE, (Level.AREA,), default=True),
    # The "Outside Temperature" switch: the season follows the outside
    # temperature instead of the indoor one.
    Opt(CONF_USE_OUTSIDE_TEMP, Kind.INTERNAL, Group.NONE, Scope.RECURRING,
        Level.HOUSE, default=False),
    # The "Lux" and "Irradiance" switches: dim light counts as not sunny.
    Opt(CONF_USE_LUX, Kind.INTERNAL, Group.NONE, Scope.RECURRING,
        Level.HOUSE, default=True),
    Opt(CONF_USE_IRRADIANCE, Kind.INTERNAL, Group.NONE, Scope.RECURRING,
        Level.HOUSE, default=True),
    # The "Manual Override" switch: manual-move detection.
    Opt(CONF_MANUAL_DETECTION, Kind.INTERNAL, Group.NONE, Scope.RECURRING,
        Level.HOUSE, (Level.AREA,), default=True),
)
# fmt: on
TOGGLE_KEYS: Final = tuple(opt.key for opt in TOGGLE_OPTS)
SHADOW_SPEC: Final[tuple[Opt, ...]] = (*OPTS, *TOGGLE_OPTS)
_OPTION_KEYS: Final = frozenset(opt.key for opt in OPTS)


def _climate(options: Mapping[str, Any]) -> bool:
    return bool(options.get(CONF_CLIMATE_MODE))


@dataclass(frozen=True)
class ToggleSwitch:
    """The switch behind one toggle, and when a window has it (``switch.py``)."""

    key: str
    """The toggle (a ``TOGGLE_OPTS`` key)."""
    switch_name: str
    """The switch's unique_id suffix: ``f"{entry_id}_{switch_name}"``."""
    initial: bool
    """The switch's state when it has nothing to restore (``switch.py``)."""
    without_switch: bool
    """What the runtime uses when the switch is not added (a disabled entity)."""
    created: Callable[[Mapping[str, Any]], bool]
    """Whether a window with these options gets the switch."""


TOGGLE_SWITCHES: Final[tuple[ToggleSwitch, ...]] = (
    ToggleSwitch(
        CONF_CLIMATE_ON,
        "Climate Mode",
        initial=True,
        # ControlState.climate starts from the climate_mode option.
        without_switch=True,
        created=_climate,
    ),
    ToggleSwitch(
        CONF_USE_OUTSIDE_TEMP,
        "Outside Temperature",
        initial=False,
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
        initial=True,
        without_switch=False,
        created=lambda options: (
            _climate(options) and bool(options.get(CONF_LUX_ENTITY))
        ),
    ),
    ToggleSwitch(
        CONF_USE_IRRADIANCE,
        "Irradiance",
        initial=True,
        without_switch=False,
        created=lambda options: (
            _climate(options) and bool(options.get(CONF_IRRADIANCE_ENTITY))
        ),
    ),
    ToggleSwitch(
        CONF_MANUAL_DETECTION,
        "Manual Override",
        initial=True,
        # ControlState.manual stays None, which turns detection off.
        without_switch=False,
        created=lambda options: len(options.get(CONF_ENTITIES) or []) >= 1,
    ),
)


# ------------------------------------------------------------ legacy values


def legacy_values(
    options: Mapping[str, Any],
    toggles: Mapping[str, bool],
    *,
    temperature_unit: str | None = None,
) -> dict[str, Any]:
    """Return every ``SHADOW_SPEC`` option as a window acts on it today.

    ``options`` are the window's options as the runtime reads them (after
    migration 1.3 every fallback is written); keys that are not options
    (``overrides``, identity keys) are left out. ``toggles`` are its switch
    states; a missing one gets its spec default (the switch's initial state).
    """
    stored = {key: value for key, value in options.items() if key in _OPTION_KEYS}
    stored.update({key: toggles[key] for key in TOGGLE_KEYS if key in toggles})
    return legacy_flat(stored, spec=SHADOW_SPEC, temperature_unit=temperature_unit)


def lift_house(
    windows: Iterable[LegacyWindow],
    areas: Mapping[str, str | None],
    floors: Sequence[str],
    *,
    temperature_unit: str | None = None,
) -> Lifted:
    """Lift the windows' ``legacy_values`` into house / floor / area profiles."""
    return lift(
        windows, areas, floors, temperature_unit=temperature_unit, spec=SHADOW_SPEC
    )


# ------------------------------------------------------------ storage

HOUSE: Final = "house"
FLOORS: Final = "floors"
AREAS: Final = "areas"
TEMPERATURE_UNIT: Final = "temperature_unit"
OVERRIDES: Final = "overrides"
WINDOW_KEY: Final = "window_key"
VALUES: Final = "values"
LEGACY: Final = "legacy"


def _plain(values: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(values))


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast("Mapping[str, Any]", value)
    return {}


def hub_options(lifted: Lifted) -> dict[str, Any]:
    """Return the hub entry's options keys that store the lifted layers."""
    return {
        HOUSE: _plain(lifted.house.values),
        TEMPERATURE_UNIT: lifted.house.temperature_unit,
        FLOORS: {key: _plain(p.values) for key, p in lifted.floors.items()},
        AREAS: {key: _plain(p.values) for key, p in lifted.areas.items()},
    }


def is_lifted(hub: Mapping[str, Any]) -> bool:
    """Return whether the hub's options hold lifted layers."""
    return isinstance(hub.get(HOUSE), Mapping)


def overrides_option(window_key: str, overrides: WindowOverrides) -> dict[str, Any]:
    """Return a window's ``overrides`` option (its one-time setup is not copied)."""
    return {
        WINDOW_KEY: window_key,
        VALUES: _plain(overrides.values),
        LEGACY: _plain(overrides.legacy),
    }


def stored_overrides(
    window_key: str, options: Mapping[str, Any]
) -> WindowOverrides | None:
    """Return the overrides a window stores for itself (None: not lifted)."""
    raw = _mapping(options.get(OVERRIDES))
    if raw.get(WINDOW_KEY) != window_key:
        return None
    return WindowOverrides(
        values=_mapping(raw.get(VALUES)), legacy=_mapping(raw.get(LEGACY))
    )


def without_overrides(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``options`` without the ``overrides`` key."""
    return {key: value for key, value in options.items() if key != OVERRIDES}


def stored_profiles(
    window_key: str,
    hub: Mapping[str, Any],
    overrides: WindowOverrides,
    legacy: Mapping[str, Any],
    placement: Placement,
    spec: Sequence[Opt] = SHADOW_SPEC,
) -> Profiles:
    """Return what ``resolve`` reads for one window.

    The layers come from the hub's options, the window's recurring values
    from ``overrides``, and its one-time settings from ``legacy`` (they
    stay in the flat options until the window becomes a subentry).
    """
    unit = hub.get(TEMPERATURE_UNIT)
    setup = {opt.key: legacy[opt.key] for opt in spec if opt.home is Level.WINDOW}
    return Profiles(
        house=HouseProfile(
            _mapping(hub.get(HOUSE)),
            temperature_unit=unit if isinstance(unit, str) else None,
        ),
        floors={
            str(key): FloorProfile(_mapping(values))
            for key, values in _mapping(hub.get(FLOORS)).items()
        },
        areas={
            str(key): AreaProfile(_mapping(values))
            for key, values in _mapping(hub.get(AREAS)).items()
        },
        windows={
            window_key: WindowOverrides(
                setup=setup, values=overrides.values, legacy=overrides.legacy
            )
        },
        placement={window_key: placement},
    )


# ------------------------------------------------------------ comparison


def adopt(
    window_key: str,
    legacy: Mapping[str, Any],
    hub: Mapping[str, Any],
    placement: Placement,
    spec: Sequence[Opt] = SHADOW_SPEC,
) -> WindowOverrides:
    """Lift one window alone against the stored layers.

    Every value the window does not inherit becomes a window override
    where the spec lets a window override it, else a ``legacy`` value
    (the lift's window rule), so the window resolves to ``legacy``.
    """
    inherited = resolve(
        window_key,
        stored_profiles(window_key, hub, WindowOverrides(), legacy, placement, spec),
        spec,
    )
    values: dict[str, Any] = {}
    kept: dict[str, Any] = {}
    for opt in spec:
        if opt.home is Level.WINDOW or same_value(legacy[opt.key], inherited[opt.key]):
            continue
        if Level.WINDOW in opt.overridable_at:
            values[opt.key] = legacy[opt.key]
        else:
            kept[opt.key] = legacy[opt.key]
    return WindowOverrides(values=values, legacy=kept)


def differing_keys(
    resolved: Mapping[str, Any],
    legacy: Mapping[str, Any],
    spec: Sequence[Opt] = SHADOW_SPEC,
) -> tuple[str, ...]:
    """Return the options (in spec order) whose resolved value is not the legacy one."""
    return tuple(
        opt.key for opt in spec if not same_value(resolved[opt.key], legacy[opt.key])
    )


_SHOWN_SOURCES: Final = frozenset({Source.AREA, Source.FLOOR, Source.LEGACY})


def provenance_summary(
    resolution: Resolution, spec: Sequence[Opt] = SHADOW_SPEC
) -> dict[str, str]:
    """Return the provenance worth showing: every non-house, non-default source.

    Left out: options from the house or the spec default (the common case)
    and one-time window settings (always the window's own).
    """
    by_key = spec_by_key(spec)
    return {
        key: source.value
        for key, source in resolution.provenance.items()
        if source in _SHOWN_SOURCES
        or (source is Source.WINDOW and by_key[key].home is not Level.WINDOW)
    }


@dataclass(frozen=True)
class ShadowCheck:
    """One window's comparison of the layered settings with its legacy values."""

    resolved: Mapping[str, Any]
    """The window's options resolved from the stored layers."""
    differing: tuple[str, ...]
    """Options whose resolved value is not the one the window acts on today."""
    provenance: Mapping[str, str]
    """``provenance_summary`` of the resolution."""


def compare(
    window_key: str,
    legacy: Mapping[str, Any],
    hub: Mapping[str, Any],
    overrides: WindowOverrides,
    placement: Placement,
    spec: Sequence[Opt] = SHADOW_SPEC,
) -> ShadowCheck:
    """Resolve one window from the stored layers and compare with ``legacy``.

    Raises
    ------
    SettingsError
        The stored layers hold a value where the spec does not allow it.

    """
    resolution = resolve_with_provenance(
        window_key,
        stored_profiles(window_key, hub, overrides, legacy, placement, spec),
        spec,
    )
    return ShadowCheck(
        resolved=resolution.values,
        differing=differing_keys(resolution.values, legacy, spec),
        provenance=provenance_summary(resolution, spec),
    )
