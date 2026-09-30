"""What a window subentry stores (P8; ADR 0001 as amended by ADR 0007).

Since v2.1 a window subentry stores only what the window uses::

    {
      "window_key": "<old entry_id>",   # a migrated window only
      "name": "<the window's name>",
      "cover_entity_id": "cover.office_door_shades",
      "cover_type": "cover_blind",
      "geometry": {...its one-time settings...},
      "overrides": {"values": {...}, "legacy": {...}},
    }

- ``window_key`` is the key of a window that was a window entry before
  (its old entry_id: the unique_id prefix, the override-store key and the
  card binding key). A window added as a subentry has none: its key is
  its subentry_id.
- ``name`` names the window's device and entities. It is usually the
  subentry's title, but not always (a window entry's title could be
  renamed without its name), so it is stored.
- ``cover_entity_id`` is the one cover the window drives (ADR 0002);
  ``cover_type`` how it moves.
- ``geometry`` holds every one-time setting the window stores (the spec's
  options whose home is the window: azimuth, field of view, heights,
  limits, interpolation, blind spot, privacy opt-in, ...).
- ``overrides`` holds the window's own recurring values, sparsely:
  ``values`` where the spec lets a window override the option, ``legacy``
  for a per-window value no allowed level can hold (see ``lift.py``).

Everything recurring comes from the house, floor and area layers
(``resolve.py``). Nothing else is stored: no copy of the recurring
settings (the "legacy flat keys"), no ``group`` list, no hub leftovers.

``WindowRecord.options`` is the flat view the runtime reads: the geometry
and the cover, as ``cover_entity_id`` and as the one-item ``group`` list
the runtime's cover reads use. It is computed, never stored.

**From v2.0.** A v2.0 subentry stored the window entry's data and options
verbatim (ADR 0006): ``{"window_key", "data": {name, sensor_type},
"options": {...every option..., "overrides": {window_key, values,
legacy}}}``. ``record_from_v2_0`` reads one; ``migration 2.1 -> 3.1``
(``upgrade.py``) rewrites every subentry with it.

Pure: no Home Assistant imports and no clock reads.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final, cast

from ..const import CONF_COVER_ENTITY, CONF_ENTITIES, CONF_SENSOR_TYPE, SensorType
from .normalize import window_covers
from .resolve import WindowOverrides
from .spec import OPTS, Level

WINDOW_KEY: Final = "window_key"
NAME: Final = "name"
COVER: Final = CONF_COVER_ENTITY
COVER_TYPE: Final = "cover_type"
GEOMETRY: Final = "geometry"
OVERRIDES: Final = "overrides"
VALUES: Final = "values"
LEGACY: Final = "legacy"

# The v2.0 subentry shape (ADR 0006).
V2_0_DATA: Final = "data"
V2_0_OPTIONS: Final = "options"

COVER_KEYS: Final = frozenset({CONF_COVER_ENTITY, CONF_ENTITIES})
"""The cover keys of the flat options: stored as ``cover_entity_id`` only."""

GEOMETRY_KEYS: Final[tuple[str, ...]] = tuple(
    opt.key for opt in OPTS if opt.home is Level.WINDOW and opt.key not in COVER_KEYS
)
"""The options a window stores in ``geometry``: its one-time settings."""

_GEOMETRY: Final = frozenset(GEOMETRY_KEYS)


class RecordError(ValueError):
    """Stored window data that is not a window record."""


class _Keep:
    """Sentinel: ``WindowRecord.with_changes`` keeps the field."""

    def __repr__(self) -> str:
        return "KEEP"


KEEP: Final = _Keep()


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast("Mapping[str, Any]", value)
    return {}


def _plain(values: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(values))


def _no_values() -> Mapping[str, Any]:
    return {}


@dataclass(frozen=True)
class WindowRecord:
    """One window as its subentry stores it (see the module docstring)."""

    name: str
    cover: str | None
    cover_type: str
    geometry: Mapping[str, Any] = field(default_factory=_no_values)
    overrides: WindowOverrides = field(default_factory=WindowOverrides)
    window_key: str | None = None
    """A migrated window's old entry_id; None for a window added as a subentry."""

    def __post_init__(self) -> None:
        """Keep the geometry to one-time settings (a copy)."""
        unknown = sorted(set(self.geometry) - _GEOMETRY)
        if unknown:
            raise RecordError(f"not one-time settings: {', '.join(unknown)}")
        object.__setattr__(self, "geometry", _plain(self.geometry))

    @property
    def covers(self) -> list[str]:
        """The cover as a list (empty without one)."""
        return [self.cover] if self.cover else []

    @property
    def options(self) -> dict[str, Any]:
        """The flat one-time options the runtime reads (never stored)."""
        return {
            **_plain(self.geometry),
            CONF_COVER_ENTITY: self.cover,
            CONF_ENTITIES: [self.cover] if self.cover else [],
        }

    def as_data(self) -> dict[str, Any]:
        """Return what the subentry stores."""
        data: dict[str, Any] = {
            NAME: self.name,
            COVER: self.cover,
            COVER_TYPE: self.cover_type,
            GEOMETRY: _plain(self.geometry),
            OVERRIDES: overrides_data(self.overrides),
        }
        if self.window_key is not None:
            data[WINDOW_KEY] = self.window_key
        return data

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> WindowRecord:
        """Read a subentry's data (the 3.1 shape).

        A geometry key this version does not know (stored by a newer minor
        version) is left out, so the window still runs.

        Raises
        ------
        RecordError
            ``data`` is not in the 3.1 shape (a v2.0 subentry, say).

        """
        if GEOMETRY not in data or V2_0_OPTIONS in data:
            raise RecordError("not a v2.1 window record (3.1 shape)")
        key = data.get(WINDOW_KEY)
        cover = data.get(COVER)
        return cls(
            name=str(data.get(NAME) or ""),
            cover=str(cover) if cover else None,
            cover_type=str(data.get(COVER_TYPE) or SensorType.BLIND),
            geometry={
                key: value
                for key, value in _mapping(data.get(GEOMETRY)).items()
                if key in _GEOMETRY
            },
            overrides=overrides_from_data(_mapping(data.get(OVERRIDES))),
            window_key=str(key) if key else None,
        )

    def with_changes(
        self,
        *,
        name: str | None = None,
        cover: str | None | _Keep = KEEP,
        cover_type: str | None = None,
        geometry: Mapping[str, Any] | None = None,
        overrides: WindowOverrides | None = None,
    ) -> WindowRecord:
        """Return the record with the given fields replaced (``cover=None``: no cover)."""
        return replace(
            self,
            name=self.name if name is None else name,
            cover=self.cover if isinstance(cover, _Keep) else cover,
            cover_type=self.cover_type if cover_type is None else cover_type,
            geometry=self.geometry if geometry is None else geometry,
            overrides=self.overrides if overrides is None else overrides,
        )


def overrides_data(overrides: WindowOverrides) -> dict[str, Any]:
    """Return a window's stored ``overrides`` (its sparse recurring values)."""
    return {VALUES: _plain(overrides.values), LEGACY: _plain(overrides.legacy)}


def overrides_from_data(raw: Mapping[str, Any]) -> WindowOverrides:
    """Read a window's stored ``overrides``."""
    return WindowOverrides(
        values=_mapping(raw.get(VALUES)), legacy=_mapping(raw.get(LEGACY))
    )


def geometry_of(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return the one-time settings stored in flat ``options``."""
    return {key: copy.deepcopy(options[key]) for key in GEOMETRY_KEYS if key in options}


def record_from_options(
    name: str,
    cover_type: str,
    options: Mapping[str, Any],
    *,
    overrides: WindowOverrides | None = None,
    window_key: str | None = None,
) -> WindowRecord:
    """Return a window's record from flat options (a form's or a service's).

    The cover is the one ``group`` cover, else ``cover_entity_id`` (the
    cover the runtime drove: ``normalize.window_covers``); the geometry is
    every one-time setting ``options`` holds. Recurring options in
    ``options`` are not stored: pass what the window overrides as
    ``overrides``.

    Raises
    ------
    RecordError
        ``options`` name more than one cover.

    """
    covers = window_covers(options)
    if len(covers) > 1:
        raise RecordError(f"a window drives one cover, not {', '.join(covers)}")
    cover = covers[0] if covers else None
    return WindowRecord(
        name=name,
        cover=str(cover) if cover else None,
        cover_type=cover_type,
        geometry=geometry_of(options),
        overrides=overrides or WindowOverrides(),
        window_key=window_key,
    )


# ------------------------------------------------------------ from v2.0


def v2_0_overrides(
    window_key: str, options: Mapping[str, Any]
) -> WindowOverrides | None:
    """Return the overrides a v2.0 window stored for itself (None: none).

    v2.0 kept them in the window's options as ``{"window_key", "values",
    "legacy"}``; ones naming another window (a copy) were not its own.
    """
    raw = _mapping(options.get(OVERRIDES))
    if raw.get(WINDOW_KEY) != window_key:
        return None
    return overrides_from_data(raw)


def is_v2_0(data: Mapping[str, Any]) -> bool:
    """Whether a subentry's data is in the v2.0 shape (data and options verbatim)."""
    return V2_0_OPTIONS in data and GEOMETRY not in data


def record_from_v2_0(data: Mapping[str, Any], subentry_id: str) -> WindowRecord:
    """Return the 3.1 record of a v2.0 window subentry (ADR 0006 shape).

    Every one-time setting and the window's overrides are kept as stored;
    the copies of the recurring settings (the legacy flat keys), ``group``
    and ``mode`` are dropped: the window resolves them from the layers.

    Raises
    ------
    RecordError
        The window has no overrides of its own (it never ran on v2.0, so
        it was never given its layered settings), or it drives several
        covers.

    """
    entry_data = _mapping(data.get(V2_0_DATA))
    options = _mapping(data.get(V2_0_OPTIONS))
    stored_key = data.get(WINDOW_KEY)
    key = str(stored_key) if stored_key else subentry_id
    overrides = v2_0_overrides(key, options)
    name = str(entry_data.get(NAME) or "")
    if overrides is None:
        raise RecordError(f"{name or key}: no layered settings of its own")
    return record_from_options(
        name,
        str(entry_data.get(CONF_SENSOR_TYPE) or SensorType.BLIND),
        options,
        overrides=overrides,
        window_key=str(stored_key) if stored_key else None,
    )
