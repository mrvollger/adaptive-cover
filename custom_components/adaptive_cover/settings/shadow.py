"""The layered settings store: the pure part (P5).

The runtime acts on the layered settings (``../layers.py``): the house,
floor and area profiles in the house entry's options and each window's
sparse overrides in its subentry (``window_record.py``). This module holds
everything about the store that is a function of its inputs. (The name is
the P5 shadow release's, which first wrote this store.)

- **Toggles.** The per-window switches P5 dropped are recurring settings
  (``TOGGLE_OPTS``; plan: "Climate on/off", the outside temp / lux /
  irradiance "use-flags", "Manual-move detection"). They are not in
  ``spec.OPTS``, so no window form shows them; ``SHADOW_SPEC`` is the spec
  the lift, the stored profiles and the runtime resolve with.
- **Flat values.** ``legacy_values`` is every option as a window's flat
  options hold it (a missing key gets its spec default).
- **Storage.** The house entry's options hold ``house``, ``floors``,
  ``areas`` and ``temperature_unit`` (``hub_options``); ``stored_profiles``
  is what ``resolve`` reads for one window.
- **Comparison.** ``compare`` resolves one window from the stored layers
  and lists every option whose value differs from its flat values (the
  lift's equality: 30 == 30.0, True != 1): it checks that a lift or an
  adoption is exact.
- **Adoption.** A new window is lifted alone against the stored layers
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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from ..const import (
    CONF_CLIMATE_MODE,
    CONF_CLIMATE_ON,
    CONF_MANUAL_DETECTION,
    CONF_USE_IRRADIANCE,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
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
    # The house's Climate switch: climate control on or off (3.2: the one
    # climate setting; a window runs it when a temperature source resolves
    # for it and it does not opt out with ignore_climate).
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


# ------------------------------------------------------------ legacy values


def legacy_values(
    options: Mapping[str, Any],
    toggles: Mapping[str, bool],
    *,
    temperature_unit: str | None = None,
) -> dict[str, Any]:
    """Return every ``SHADOW_SPEC`` option as flat ``options`` hold it.

    ``options`` are a window's flat options as the runtime reads them
    (fallbacks written); keys that are not options are left out.
    ``toggles`` are toggle values; a missing one gets its spec default.
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


def _plain(values: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(values))


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast("Mapping[str, Any]", value)
    return {}


RETIRED: Final = frozenset({CONF_CLIMATE_MODE})
"""Keys a stored layer can still hold from before house 3.2, read as absent.

Migration 3.2 removes ``climate_mode`` (upgrade.py); the upgrade from
v1.19.x plans and verifies the windows before it runs (consolidate.py),
while the house layers and the moved windows' overrides still hold it.
"""


def _current(values: Any) -> dict[str, Any]:
    return {key: value for key, value in _mapping(values).items() if key not in RETIRED}


def hub_options(lifted: Lifted) -> dict[str, Any]:
    """Return the hub entry's options keys that store the lifted layers."""
    return {
        HOUSE: _plain(lifted.house.values),
        TEMPERATURE_UNIT: lifted.house.temperature_unit,
        FLOORS: {key: _plain(p.values) for key, p in lifted.floors.items()},
        AREAS: {key: _plain(p.values) for key, p in lifted.areas.items()},
    }


def stored_profiles(
    window_key: str,
    hub: Mapping[str, Any],
    overrides: WindowOverrides,
    legacy: Mapping[str, Any],
    placement: Placement,
    spec: Sequence[Opt] = SHADOW_SPEC,
) -> Profiles:
    """Return what ``resolve`` reads for one window.

    The layers come from the house's options, the window's recurring
    values from ``overrides``, and its one-time settings from ``legacy``
    (its flat options: its geometry and its cover). ``RETIRED`` keys are
    left out.
    """
    unit = hub.get(TEMPERATURE_UNIT)
    setup = {opt.key: legacy[opt.key] for opt in spec if opt.home is Level.WINDOW}
    return Profiles(
        house=HouseProfile(
            _current(hub.get(HOUSE)),
            temperature_unit=unit if isinstance(unit, str) else None,
        ),
        floors={
            str(key): FloorProfile(_current(values))
            for key, values in _mapping(hub.get(FLOORS)).items()
        },
        areas={
            str(key): AreaProfile(_current(values))
            for key, values in _mapping(hub.get(AREAS)).items()
        },
        windows={
            window_key: WindowOverrides(
                setup=setup,
                values=_current(overrides.values),
                legacy=_current(overrides.legacy),
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
