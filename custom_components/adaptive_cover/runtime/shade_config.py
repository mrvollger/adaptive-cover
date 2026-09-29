"""Typed reads of one window's options and switch toggles (refactor P4).

:class:`ShadeConfig` is what the coordinator reads from ``entry.options`` on
every refresh (it was ``_update_options``). :class:`ControlState` holds the
switch-driven toggles. Both are plain data with no ``hass``: the coordinator
builds and owns them, and the other runtime components read them.

Options read once at setup (cover type, climate mode, inverse state,
interpolation, return-to-sunset, ignore intermediate states) stay on the
coordinator until the components that use them move out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, Self, overload

from ..const import (
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_END_ENTITY,
    CONF_END_TIME,
    CONF_ENTITIES,
    CONF_INTERP_END,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
    CONF_INTERP_START,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MANUAL_THRESHOLD,
    CONF_MAX_MOVES_HOUR,
    CONF_PRIVACY_POSITION,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_START_ENTITY,
    CONF_START_TIME,
    CONF_SUNSET_POS,
    DEFAULT_MANUAL_OVERRIDE_DURATION,
)


@dataclass(frozen=True, slots=True)
class ShadeConfig:
    """The options one refresh reads, typed (built by :meth:`from_options`).

    Values are taken as stored: no casting, so a read never raises where
    the plain ``options.get`` it replaces did not.
    """

    entities: list[str]
    """The covers this window drives."""
    min_change: float
    """Position-delta gate: the smallest move worth making (%)."""
    time_threshold: float
    """Time-delta gate: minutes between our commands to one cover."""
    start_time: str | None
    start_time_entity: str | None
    end_time: str | None
    end_time_entity: str | None
    manual_reset: bool
    """A later manual move restarts the override clock."""
    manual_duration: dict[str, float]
    """How long a manual override lasts (``timedelta`` keyword arguments)."""
    manual_threshold: float | None
    """Smallest difference from our position that counts as manual."""
    interp_start: float | None
    interp_end: float | None
    interp_list: Sequence[int | float | str] | None
    interp_list_new: Sequence[int | float | str] | None
    quiet_start: str | None
    quiet_end: str | None
    max_moves_hour: int | None
    sunset_pos: float | None
    """Position after sunset; with the next two, a snap position."""
    default_height: float | None
    """Position when the sun is not in front of the window."""
    privacy_position: float | None

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> ShadeConfig:
        """Read the per-refresh options, with the coordinator's defaults."""
        return cls(
            entities=options.get(CONF_ENTITIES, []),
            min_change=options.get(CONF_DELTA_POSITION, 1),
            time_threshold=options.get(CONF_DELTA_TIME, 2),
            start_time=options.get(CONF_START_TIME),
            start_time_entity=options.get(CONF_START_ENTITY),
            end_time=options.get(CONF_END_TIME),
            end_time_entity=options.get(CONF_END_ENTITY),
            manual_reset=options.get(CONF_MANUAL_OVERRIDE_RESET, False),
            manual_duration=options.get(
                CONF_MANUAL_OVERRIDE_DURATION, DEFAULT_MANUAL_OVERRIDE_DURATION
            ),
            manual_threshold=options.get(CONF_MANUAL_THRESHOLD),
            interp_start=options.get(CONF_INTERP_START),
            interp_end=options.get(CONF_INTERP_END),
            interp_list=options.get(CONF_INTERP_LIST),
            interp_list_new=options.get(CONF_INTERP_LIST_NEW),
            quiet_start=options.get(CONF_QUIET_START),
            quiet_end=options.get(CONF_QUIET_END),
            max_moves_hour=options.get(CONF_MAX_MOVES_HOUR),
            sunset_pos=options.get(CONF_SUNSET_POS),
            default_height=options.get(CONF_DEFAULT_HEIGHT),
            privacy_position=options.get(CONF_PRIVACY_POSITION),
        )


@dataclass(slots=True)
class ControlState:
    """The window's switch toggles.

    None means "not restored yet": the switch platform restores its state
    after the coordinator's first refresh.
    """

    control: bool | None = None
    """Automatic control (the "Toggle Control" switch)."""
    manual: bool | None = None
    """Manual-override detection (the "Manual Override" switch)."""
    climate: bool = False
    """Climate mode (the "Climate Mode" switch); starts from the option."""
    outside_temp: bool | None = None
    """Use the outside temperature (the "Outside Temperature" switch)."""
    lux: bool | None = None
    irradiance: bool | None = None

    @property
    def clears_overrides(self) -> bool:
        """Return True when manual-override detection is switched off.

        Only an EXPLICIT off clears overrides. During startup/reload the
        toggle is still None (switches restore after the first refresh),
        and treating that as off wiped overrides on every options edit.
        """
        return self.manual is False


class _HasControls(Protocol):
    """An owner of a :class:`ControlState` (the coordinator)."""

    controls: ControlState


class ControlToggle[T: bool | None]:
    """An attribute that reads and writes one :class:`ControlState` field.

    The switch platform sets toggles by name (``setattr(coordinator,
    "manual_toggle", True)``); declaring ``manual_toggle =
    ControlToggle[bool | None]("manual")`` on the coordinator keeps those
    names while the state lives in one ``ControlState``. ``T`` is the
    field's type.
    """

    def __init__(self, field_name: str) -> None:
        """Forward to ``owner.controls.<field_name>``."""
        self._field = field_name

    @overload
    def __get__(self, owner: None, owner_type: type[Any] | None = None) -> Self: ...

    @overload
    def __get__(
        self, owner: _HasControls, owner_type: type[Any] | None = None
    ) -> T: ...

    def __get__(
        self, owner: _HasControls | None, owner_type: type[Any] | None = None
    ) -> Self | T:
        """Return the toggle (the descriptor itself on the class)."""
        if owner is None:
            return self
        value: T = getattr(owner.controls, self._field)
        return value

    def __set__(self, owner: _HasControls, value: T) -> None:
        """Set the toggle."""
        setattr(owner.controls, self._field, value)
