"""Layered settings: one window's effective options from its profiles (P5).

ADR 0003 precedence, first value found wins:

1. window (its one-time ``setup`` and its recurring ``values`` overrides),
2. area,
3. floor,
4. house,
5. spec default.

A lifted house can also carry ``legacy`` values on a window: values from
the flat per-window options that no level the spec allows can hold (see
``lift.py``). They win over everything, so the lift stays exact, and their
provenance says ``legacy`` so the UI can ask the owner to settle them.

Where an option may be stored comes from the spec: its ``home`` level plus
its ``overridable_at`` levels (``allowed_levels``). A value stored anywhere
else is an error, never silently ignored. A window's area and floor are
live facts (the window device's area, copied from its cover), so they come
in as ``Placement``, separate from the stored profiles.

A stored ``None`` is a value ("explicitly unset"): only a missing key
inherits. An option set nowhere and without a spec default resolves to
``None``, which is what the runtime reads for a missing key.

Pure: no Home Assistant imports and no clock reads.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar, Final

from .spec import NO_DEFAULT, OPTS, Level, Opt


class Source(StrEnum):
    """Where a resolved value came from (the Position attribute ``provenance``)."""

    LEGACY = "legacy"
    WINDOW = "window"
    AREA = "area"
    FLOOR = "floor"
    HOUSE = "house"
    DEFAULT = "default"


class SettingsError(ValueError):
    """Stored settings that the spec does not allow."""


class UnknownOptionError(SettingsError):
    """A stored key that is not an option in the spec."""


class LevelNotAllowedError(SettingsError):
    """An option stored at a level the spec does not allow for it."""


def allowed_levels(opt: Opt) -> frozenset[Level]:
    """Return the levels that may store ``opt``: its home and its override levels."""
    levels = set(opt.overridable_at)
    if opt.home is not None:
        levels.add(opt.home)
    return frozenset(levels)


def spec_default(opt: Opt, temperature_unit: str | None = None) -> Any:
    """Return the spec default of ``opt`` (a fresh copy), or None without one.

    Climate thresholds have one default per HA temperature unit; an unknown
    or missing unit falls back to °C, like ``Opt.shape``.
    """
    if opt.by_temperature_unit is not None:
        shape = opt.by_temperature_unit.get(
            temperature_unit or "", opt.by_temperature_unit["°C"]
        )
        return shape.default
    if opt.default is NO_DEFAULT:
        return None
    return copy.deepcopy(opt.default)


def spec_by_key(spec: Sequence[Opt]) -> dict[str, Opt]:
    """Return the spec rows by option key."""
    return {opt.key: opt for opt in spec}


def _frozen(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a read-only deep copy (callers keep no handle on the profile)."""
    return MappingProxyType(copy.deepcopy(dict(values)))


def _no_values() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True)
class _Layer:
    """Sparse option values stored at one level (house, a floor or an area)."""

    level: ClassVar[Level]
    values: Mapping[str, Any] = field(default_factory=_no_values)

    def __post_init__(self) -> None:
        """Freeze the values."""
        object.__setattr__(self, "values", _frozen(self.values))


@dataclass(frozen=True)
class HouseProfile(_Layer):
    """The house layer. A lifted house stores every house-level option.

    ``temperature_unit`` is HA's unit; the climate-threshold defaults
    depend on it.
    """

    level: ClassVar[Level] = Level.HOUSE
    temperature_unit: str | None = None


@dataclass(frozen=True)
class FloorProfile(_Layer):
    """One HA floor's overrides (sparse)."""

    level: ClassVar[Level] = Level.FLOOR


@dataclass(frozen=True)
class AreaProfile(_Layer):
    """One HA area's (room's) overrides (sparse)."""

    level: ClassVar[Level] = Level.AREA


@dataclass(frozen=True)
class WindowOverrides:
    """What one window stores itself.

    - ``setup``: its one-time settings (options whose home is the window);
    - ``values``: recurring options it overrides, where the spec lets a
      window override them (sparse);
    - ``legacy``: values kept from the flat legacy options that no allowed
      level can hold (sparse; only the lift writes these).
    """

    setup: Mapping[str, Any] = field(default_factory=_no_values)
    values: Mapping[str, Any] = field(default_factory=_no_values)
    legacy: Mapping[str, Any] = field(default_factory=_no_values)

    def __post_init__(self) -> None:
        """Freeze the three maps."""
        for name in ("setup", "values", "legacy"):
            object.__setattr__(self, name, _frozen(getattr(self, name)))


@dataclass(frozen=True)
class Placement:
    """Where a window is: its area and that area's floor (live, not stored)."""

    area_id: str | None = None
    floor_id: str | None = None


def _read_only[T](items: Mapping[str, T]) -> Mapping[str, T]:
    return MappingProxyType(dict(items))


@dataclass(frozen=True)
class Profiles:
    """Everything ``resolve`` reads: the stored layers plus each window's placement."""

    house: HouseProfile = field(default_factory=HouseProfile)
    floors: Mapping[str, FloorProfile] = field(default_factory=dict[str, FloorProfile])
    areas: Mapping[str, AreaProfile] = field(default_factory=dict[str, AreaProfile])
    windows: Mapping[str, WindowOverrides] = field(
        default_factory=dict[str, WindowOverrides]
    )
    placement: Mapping[str, Placement] = field(default_factory=dict[str, Placement])

    def __post_init__(self) -> None:
        """Freeze the maps (the profiles themselves are already frozen)."""
        object.__setattr__(self, "floors", _read_only(self.floors))
        object.__setattr__(self, "areas", _read_only(self.areas))
        object.__setattr__(self, "windows", _read_only(self.windows))
        object.__setattr__(self, "placement", _read_only(self.placement))


@dataclass(frozen=True)
class Resolution:
    """A window's effective options and where each one came from."""

    values: Mapping[str, Any]
    provenance: Mapping[str, Source]


_NOWHERE: Final = Placement()
_NO_FLOOR: Final = FloorProfile()
_NO_AREA: Final = AreaProfile()


def _names(levels: frozenset[Level]) -> str:
    order = (Level.HOUSE, Level.FLOOR, Level.AREA, Level.WINDOW)
    return ", ".join(level.value for level in order if level in levels) or "none"


def _check_layer(layer: _Layer, where: str, by_key: Mapping[str, Opt]) -> None:
    for key in layer.values:
        opt = by_key.get(key)
        if opt is None:
            raise UnknownOptionError(f"{where}: {key!r} is not an option")
        allowed = allowed_levels(opt)
        if layer.level not in allowed:
            raise LevelNotAllowedError(
                f"{where}: {key!r} cannot be set at the {layer.level} level"
                f" (allowed: {_names(allowed)})"
            )


def _check_window(
    window: WindowOverrides, where: str, by_key: Mapping[str, Opt]
) -> None:
    for part, keys in (
        ("setup", window.setup),
        ("values", window.values),
        ("legacy", window.legacy),
    ):
        for key in keys:
            opt = by_key.get(key)
            if opt is None:
                raise UnknownOptionError(f"{where} {part}: {key!r} is not an option")
            if part == "setup" and opt.home is not Level.WINDOW:
                raise LevelNotAllowedError(
                    f"{where} setup: {key!r} is not a one-time window setting"
                    f" (allowed: {_names(allowed_levels(opt))})"
                )
            if part == "values" and Level.WINDOW not in opt.overridable_at:
                raise LevelNotAllowedError(
                    f"{where}: {key!r} cannot be overridden by a window"
                    f" (allowed: {_names(allowed_levels(opt))})"
                )
            if part == "legacy" and Level.WINDOW in allowed_levels(opt):
                raise LevelNotAllowedError(
                    f"{where} legacy: {key!r} can be stored on the window;"
                    " keep it in setup or values"
                )


def check_profiles(profiles: Profiles, spec: Sequence[Opt] = OPTS) -> None:
    """Raise ``SettingsError`` if any stored value sits where the spec forbids it."""
    by_key = spec_by_key(spec)
    _check_layer(profiles.house, "house", by_key)
    for floor_id, floor in profiles.floors.items():
        _check_layer(floor, f"floor {floor_id!r}", by_key)
    for area_id, area in profiles.areas.items():
        _check_layer(area, f"area {area_id!r}", by_key)
    for window_key, window in profiles.windows.items():
        _check_window(window, f"window {window_key!r}", by_key)


def resolve_with_provenance(
    window_key: str, profiles: Profiles, spec: Sequence[Opt] = OPTS
) -> Resolution:
    """Resolve every spec option for one window, with the source of each value.

    Raises
    ------
    KeyError
        The profiles have no window ``window_key``.
    SettingsError
        A layer this window reads stores an unknown option, or an option at
        a level the spec does not allow.

    """
    try:
        window = profiles.windows[window_key]
    except KeyError as err:
        raise KeyError(f"no window {window_key!r} in the profiles") from err
    place = profiles.placement.get(window_key, _NOWHERE)
    floor = _NO_FLOOR
    if place.floor_id is not None:
        floor = profiles.floors.get(place.floor_id, _NO_FLOOR)
    area = _NO_AREA
    if place.area_id is not None:
        area = profiles.areas.get(place.area_id, _NO_AREA)

    by_key = spec_by_key(spec)
    _check_layer(profiles.house, "house", by_key)
    _check_layer(floor, f"floor {place.floor_id!r}", by_key)
    _check_layer(area, f"area {place.area_id!r}", by_key)
    _check_window(window, f"window {window_key!r}", by_key)

    # First match wins; ADR 0003 order (legacy values sit above it all).
    layers: tuple[tuple[Source, Mapping[str, Any]], ...] = (
        (Source.LEGACY, window.legacy),
        (Source.WINDOW, window.values),
        (Source.WINDOW, window.setup),
        (Source.AREA, area.values),
        (Source.FLOOR, floor.values),
        (Source.HOUSE, profiles.house.values),
    )
    values: dict[str, Any] = {}
    provenance: dict[str, Source] = {}
    for opt in spec:
        for source, layer in layers:
            if opt.key in layer:
                values[opt.key] = copy.deepcopy(layer[opt.key])
                provenance[opt.key] = source
                break
        else:
            values[opt.key] = spec_default(opt, profiles.house.temperature_unit)
            provenance[opt.key] = Source.DEFAULT
    return Resolution(
        values=MappingProxyType(values), provenance=MappingProxyType(provenance)
    )


def resolve(
    window_key: str, profiles: Profiles, spec: Sequence[Opt] = OPTS
) -> dict[str, Any]:
    """Return one window's effective options (every spec key, in spec order).

    See ``resolve_with_provenance`` for the errors.
    """
    return dict(resolve_with_provenance(window_key, profiles, spec).values)
