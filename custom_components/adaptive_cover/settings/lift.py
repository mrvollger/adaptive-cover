"""Lift flat per-window legacy options into house / floor / area profiles (P5).

Today every window entry stores one flat options dict. The lift factors
those dicts into the layered model that ``resolve.py`` reads (ADR 0003,
"Moving the live house"), so that ``resolve(w) == legacy_flat(w)`` for
every window:

- **Home level** (the option's ``home`` in the spec, usually the house):
  the most common value among its windows. The lifted house stores every
  house-level option, so a later change of a spec default cannot move it.
- **Narrower levels** (floor, area): a value when all of that floor's or
  area's windows agree on it and it differs from what they would inherit.
- **Window**: one-time options always (they live on the window); a
  recurring value only for a true outlier, and only where the spec lets a
  window override that option.
- **Legacy**: an outlier that no allowed level can hold (for example one
  room's window with its own sunrise offset, which only an area may set)
  is kept as a window ``legacy`` value, so the lift stays exact and the
  owner can settle it later.

Legacy values come first: a level departs from the rules above only when
they would leave legacy values that another choice avoids (the home level
then takes a less common value; a floor or area whose windows disagree
takes the value that leaves the fewest). So options that the allowed
levels can express lift without any legacy value.

Deterministic: windows are taken in ``window_key`` order, and a tie for
the most common value goes to the value that needs fewer stored
overrides, then to the spec default, then to the value seen first.

Values compare as settings, not as Python objects: 30 and 30.0 are one
value, a bool never equals a number, and lists and dicts compare by
content.

Pure: no Home Assistant imports and no clock reads.
"""

from __future__ import annotations

import copy
from collections.abc import Collection, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, NamedTuple, cast

from .resolve import (
    AreaProfile,
    FloorProfile,
    HouseProfile,
    Placement,
    Profiles,
    UnknownOptionError,
    WindowOverrides,
    allowed_levels,
    spec_by_key,
    spec_default,
)
from .spec import OPTS, Level, Opt

# Legacy keys that are window identity, not settings: the window setup
# reads them from the cover (plan: "name, type, area (read from the cover)").
IDENTITY_KEYS: Final = frozenset({"name", "sensor_type"})

_HOUSE_UNIT: Final = "house"
_LAYERED: Final = (Level.HOUSE, Level.FLOOR, Level.AREA)
# A floor or area that stores nothing (its windows inherit).
_INHERIT: Final = object()


@dataclass(frozen=True)
class LegacyWindow:
    """One legacy window entry, as the lift reads it.

    ``options`` is the entry's ``data`` merged with its ``options`` (as
    stored; missing keys and stored ``None`` differ). ``area_id`` is the
    effective area of the window's cover.
    """

    window_key: str
    options: Mapping[str, Any]
    area_id: str | None = None


class Lifted(NamedTuple):
    """The lift's result: the profiles that reproduce every legacy window."""

    house: HouseProfile
    floors: dict[str, FloorProfile]
    areas: dict[str, AreaProfile]
    overrides: dict[str, WindowOverrides]

    def profiles(self, placement: Mapping[str, Placement]) -> Profiles:
        """Return the lifted layers with each window's placement, for ``resolve``."""
        return Profiles(
            house=self.house,
            floors=self.floors,
            areas=self.areas,
            windows=self.overrides,
            placement=placement,
        )


def legacy_flat(
    options: Mapping[str, Any],
    *,
    spec: Sequence[Opt] = OPTS,
    temperature_unit: str | None = None,
) -> dict[str, Any]:
    """Return every spec option as a legacy window has it today.

    A stored value (``None`` included) is kept; a missing key gets its spec
    default (``None`` without one), the value the entry gets from code
    defaults. Identity keys (``IDENTITY_KEYS``) are not settings and are
    left out.

    Raises
    ------
    UnknownOptionError
        ``options`` has a key the spec does not know.

    """
    by_key = spec_by_key(spec)
    unknown = sorted(set(options) - set(by_key) - IDENTITY_KEYS)
    if unknown:
        raise UnknownOptionError(f"not options in the spec: {', '.join(unknown)}")
    return {
        opt.key: (
            copy.deepcopy(options[opt.key])
            if opt.key in options
            else spec_default(opt, temperature_unit)
        )
        for opt in spec
    }


def placements(
    entries: Iterable[LegacyWindow], areas: Mapping[str, str | None]
) -> dict[str, Placement]:
    """Return each window's area and floor (``areas`` maps area_id to floor_id)."""
    return {
        entry.window_key: Placement(
            area_id=entry.area_id,
            floor_id=areas.get(entry.area_id) if entry.area_id is not None else None,
        )
        for entry in entries
    }


# ------------------------------------------------------------ comparison


def _key(value: Any, *, exact: bool = False) -> Hashable:
    """Return a hashable stand-in for an option value.

    With ``exact=False`` (setting equality) ints and floats that are equal
    match; with ``exact=True`` their types must match too. Bools never
    match numbers.
    """
    if value is None or isinstance(value, str):
        return (type(value).__name__, value)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int | float):
        return (type(value).__name__ if exact else "number", value)
    if isinstance(value, list | tuple):
        items = cast("Sequence[Any]", value)
        kind = type(items).__name__ if exact else "sequence"
        return (kind, tuple(_key(item, exact=exact) for item in items))
    if isinstance(value, Mapping):
        pairs = cast("Mapping[Any, Any]", value)
        return (
            "mapping",
            tuple(
                sorted(
                    ((str(k), _key(v, exact=exact)) for k, v in pairs.items()),
                    key=lambda pair: pair[0],
                )
            ),
        )
    raise TypeError(f"cannot compare option value {value!r}")


def _same(a: Any, b: Any) -> bool:
    return _key(a) == _key(b)


@dataclass
class _Tally:
    """One distinct value among some windows."""

    count: int = 0
    forms: dict[Hashable, list[Any]] = field(default_factory=dict[Hashable, list[Any]])

    def add(self, value: Any) -> None:
        self.count += 1
        self.forms.setdefault(_key(value, exact=True), []).append(value)

    @property
    def value(self) -> Any:
        """The most common exact form (30 vs 30.0); the first seen on a tie."""
        return max(self.forms.values(), key=len)[0]


def _tally(values: Iterable[Any]) -> list[_Tally]:
    """Return the distinct values in first-seen order."""
    tallies: dict[Hashable, _Tally] = {}
    for value in values:
        tallies.setdefault(_key(value), _Tally()).add(value)
    return list(tallies.values())


# ------------------------------------------------------------ factoring


@dataclass(frozen=True)
class _Win:
    """One window's value of the option being lifted."""

    key: str
    floor_id: str | None
    area_id: str | None
    value: Any


def _unit(level: Level, win: _Win) -> str | None:
    if level is Level.HOUSE:
        return _HOUSE_UNIT
    if level is Level.FLOOR:
        return win.floor_id
    return win.area_id


@dataclass
class _Placed:
    """Where one option's values go."""

    layers: dict[Level, dict[str, Any]] = field(
        default_factory=lambda: {level: {} for level in _LAYERED}
    )
    setup: dict[str, Any] = field(default_factory=dict[str, Any])
    overrides: dict[str, Any] = field(default_factory=dict[str, Any])
    legacy: dict[str, Any] = field(default_factory=dict[str, Any])

    def merge(self, other: _Placed) -> None:
        for level, units in other.layers.items():
            self.layers[level].update(units)
        self.setup.update(other.setup)
        self.overrides.update(other.overrides)
        self.legacy.update(other.legacy)

    def cost(self) -> tuple[int, int]:
        """(legacy values, stored overrides): fewer is better."""
        stored = sum(len(units) for units in self.layers.values())
        return len(self.legacy), stored + len(self.overrides)


class _OptionLift:
    """Factor one option's per-window values into the allowed levels.

    ``place`` results are memoized and never mutated after they are built
    (callers merge them into their own ``_Placed``).
    """

    def __init__(self, opt: Opt, default: Any) -> None:
        self.opt = opt
        self.allowed = allowed_levels(opt)
        self.default = default
        self._memo: dict[tuple[int, tuple[str, ...], Hashable], _Placed] = {}

    def place(self, members: Sequence[_Win], depth: int, inherited: Any) -> _Placed:
        """Place ``members`` (which all inherit ``inherited``) from ``depth`` down."""
        memo_key = (depth, tuple(win.key for win in members), _key(inherited))
        placed = self._memo.get(memo_key)
        if placed is None:
            placed = self._memo[memo_key] = self._place(members, depth, inherited)
        return placed

    def _place(self, members: Sequence[_Win], depth: int, inherited: Any) -> _Placed:
        if depth == len(_LAYERED):
            return self._windows(members, inherited)
        level = _LAYERED[depth]
        if level not in self.allowed:
            return self.place(members, depth + 1, inherited)
        placed = _Placed()
        groups: dict[str | None, list[_Win]] = {}
        for win in members:
            groups.setdefault(_unit(level, win), []).append(win)
        for unit, group in groups.items():
            if unit is None:
                placed.merge(self.place(group, depth + 1, inherited))
                continue
            if level is self.opt.home:
                value, below = self._home_value(group, depth)
            else:
                value, below = self._narrower_value(group, depth, inherited)
            if value is not _INHERIT:
                placed.layers[level][unit] = value
            placed.merge(below)
        return placed

    def _home_value(self, group: Sequence[_Win], depth: int) -> tuple[Any, _Placed]:
        """Pick the value the home level stores: the most common, tie-broken."""
        best: tuple[tuple[int, int, int, bool, int], Any, _Placed] | None = None
        for rank, tally in enumerate(_tally(win.value for win in group)):
            below = self.place(group, depth + 1, tally.value)
            legacy, stored = below.cost()
            score = (
                legacy,
                -tally.count,
                stored,
                not _same(tally.value, self.default),
                rank,
            )
            if best is None or score < best[0]:
                best = (score, tally.value, below)
        assert best is not None  # a group always has a window
        return best[1], best[2]

    def _narrower_value(
        self, group: Sequence[_Win], depth: int, inherited: Any
    ) -> tuple[Any, _Placed]:
        """Pick what a floor or area stores (``_INHERIT``: nothing)."""
        tallies = _tally(win.value for win in group)
        if len(tallies) == 1:
            shared = tallies[0].value
            if _same(shared, inherited):
                return _INHERIT, self.place(group, depth + 1, inherited)
            return shared, self.place(group, depth + 1, shared)
        below = self.place(group, depth + 1, inherited)
        if not below.legacy:
            return _INHERIT, below
        # The windows disagree and inheriting leaves legacy values: store
        # the value that leaves the fewest (then the fewest overrides).
        best: tuple[tuple[int, int, int], Any, _Placed] = (
            (*below.cost(), -1),
            _INHERIT,
            below,
        )
        for rank, tally in enumerate(tallies):
            if _same(tally.value, inherited):
                continue
            option = self.place(group, depth + 1, tally.value)
            legacy, stored = option.cost()
            score = (legacy, stored + 1, rank)
            if score < best[0]:
                best = (score, tally.value, option)
        return best[1], best[2]

    def _windows(self, members: Sequence[_Win], inherited: Any) -> _Placed:
        """Place the window level: one-time values, outliers, then legacy leftovers."""
        placed = _Placed()
        for win in members:
            if self.opt.home is Level.WINDOW:
                placed.setup[win.key] = win.value
            elif _same(win.value, inherited):
                continue
            elif Level.WINDOW in self.allowed:
                placed.overrides[win.key] = win.value
            else:
                placed.legacy[win.key] = win.value
        return placed


# ------------------------------------------------------------ the lift


def _check_places(
    windows: Sequence[LegacyWindow],
    areas: Mapping[str, str | None],
    floors: Collection[str],
) -> None:
    keys = [window.window_key for window in windows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate window_key in the legacy entries")
    for window in windows:
        if window.area_id is not None and window.area_id not in areas:
            raise ValueError(
                f"window {window.window_key!r}: unknown area {window.area_id!r}"
            )
    for area_id, floor_id in areas.items():
        if floor_id is not None and floor_id not in floors:
            raise ValueError(f"area {area_id!r}: unknown floor {floor_id!r}")


def lift(
    entries: Iterable[LegacyWindow],
    areas: Mapping[str, str | None],
    floors: Collection[str],
    *,
    temperature_unit: str | None = None,
    spec: Sequence[Opt] = OPTS,
) -> Lifted:
    """Factor legacy window options into the fewest house/floor/area/window values.

    ``areas`` maps each HA area_id to its floor_id (or None); ``floors``
    are the HA floor ids. The result resolves back to ``legacy_flat`` of
    every entry (see the module docstring for the rules).

    Raises
    ------
    UnknownOptionError
        An entry has an option the spec does not know.
    ValueError
        Duplicate window keys, or an area or floor that does not exist.

    """
    windows = sorted(entries, key=lambda entry: entry.window_key)
    _check_places(windows, areas, floors)
    where = placements(windows, areas)
    flats = {
        window.window_key: legacy_flat(
            window.options, spec=spec, temperature_unit=temperature_unit
        )
        for window in windows
    }

    house: dict[str, Any] = {}
    # unit (floor_id, area_id or window_key) -> option key -> value
    floor_values: dict[str, dict[str, Any]] = {}
    area_values: dict[str, dict[str, Any]] = {}
    setup: dict[str, dict[str, Any]] = {}
    overrides: dict[str, dict[str, Any]] = {}
    legacy: dict[str, dict[str, Any]] = {}
    for opt in spec:
        members = [
            _Win(
                key=window.window_key,
                floor_id=where[window.window_key].floor_id,
                area_id=where[window.window_key].area_id,
                value=flats[window.window_key][opt.key],
            )
            for window in windows
        ]
        option = _OptionLift(opt, spec_default(opt, temperature_unit))
        found = option.place(members, 0, option.default)
        if _HOUSE_UNIT in found.layers[Level.HOUSE]:
            house[opt.key] = found.layers[Level.HOUSE][_HOUSE_UNIT]
        for into, units in (
            (floor_values, found.layers[Level.FLOOR]),
            (area_values, found.layers[Level.AREA]),
            (setup, found.setup),
            (overrides, found.overrides),
            (legacy, found.legacy),
        ):
            for unit, value in units.items():
                into.setdefault(unit, {})[opt.key] = value

    return Lifted(
        house=HouseProfile(house, temperature_unit=temperature_unit),
        floors={
            floor_id: FloorProfile(values)
            for floor_id, values in sorted(floor_values.items())
        },
        areas={
            area_id: AreaProfile(values)
            for area_id, values in sorted(area_values.items())
        },
        overrides={
            window.window_key: WindowOverrides(
                setup=setup.get(window.window_key, {}),
                values=overrides.get(window.window_key, {}),
                legacy=legacy.get(window.window_key, {}),
            )
            for window in windows
        },
    )
