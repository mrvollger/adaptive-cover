"""Typed reads of one window's options and switch toggles (refactor P4).

:class:`ShadeConfig` is what the coordinator reads from ``entry.options`` on
every refresh (it was ``_update_options``). :class:`ControlState` holds the
switch-driven toggles. Both are plain data with no ``hass``: the coordinator
builds and owns them, and the other runtime components read them.

``ShadeConfig`` also carries what the cover adapters read
(:class:`CoverGeometry`, see ``calculation.AdaptiveGeneralCover.from_config``)
and what the climate adapter reads (:class:`ClimateOptions`), so every
option has one read with one fallback: :data:`ABSENT`.

The options read once at setup (climate mode, inverse state, interpolation,
return-to-sunset, ignore intermediate states) are here too, with the same
fallbacks, but the coordinator still reads them itself until the components
that use them move out.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol, Self, overload

from ..const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_BLIND_SPOT_ELEVATION,
    CONF_BLIND_SPOT_LEFT,
    CONF_BLIND_SPOT_RIGHT,
    CONF_CLIMATE_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENABLE_BLIND_SPOT,
    CONF_ENABLE_MAX_POSITION,
    CONF_ENABLE_MIN_POSITION,
    CONF_END_ENTITY,
    CONF_END_TIME,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_INTERP,
    CONF_INTERP_END,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
    CONF_INTERP_START,
    CONF_INVERSE_STATE,
    CONF_IRRADIANCE_ENTITY,
    CONF_IRRADIANCE_THRESHOLD,
    CONF_LENGTH_AWNING,
    CONF_LUX_ENTITY,
    CONF_LUX_THRESHOLD,
    CONF_MANUAL_IGNORE_INTERMEDIATE,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MANUAL_THRESHOLD,
    CONF_MAX_ELEVATION,
    CONF_MAX_MOVES_HOUR,
    CONF_MAX_POSITION,
    CONF_MIN_ELEVATION,
    CONF_MIN_POSITION,
    CONF_OCCUPIED_DISTANCE,
    CONF_OUTSIDE_THRESHOLD,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_PRESENCE_ENTITY,
    CONF_PRIVACY_MODE,
    CONF_PRIVACY_OFFSET,
    CONF_PRIVACY_POSITION,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_RETURN_SUNSET,
    CONF_START_ENTITY,
    CONF_START_TIME,
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_HYSTERESIS,
    CONF_TEMP_LOW,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    CONF_TRANSPARENT_BLIND,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_STATE,
    DEFAULT_MANUAL_OVERRIDE_DURATION,
)

# What each option reads as when the entry does not store it: the fallback
# of every runtime read of that key (None: the read has no fallback). A key
# stored as None reads as None, not as its fallback.
#
# Config migration 1.3 writes these into an entry that lacks a key (see
# absent_options), so a later change to a spec default cannot move an
# existing window. The sunrise offset is not listed: it falls back to the
# sunset offset. The covers (CONF_ENTITIES) are not listed either: the
# migration writes them with cover_entity_id.
ABSENT: Final[Mapping[str, Any]] = MappingProxyType(
    {
        # setup-time reads (the coordinator reads these itself, same fallback)
        CONF_CLIMATE_MODE: False,
        CONF_INVERSE_STATE: False,
        CONF_INTERP: False,
        CONF_RETURN_SUNSET: None,
        CONF_MANUAL_IGNORE_INTERMEDIATE: False,
        # gates, schedule, overrides
        CONF_DELTA_POSITION: 1,
        CONF_DELTA_TIME: 2,
        CONF_START_TIME: None,
        CONF_START_ENTITY: None,
        CONF_END_TIME: None,
        CONF_END_ENTITY: None,
        CONF_MANUAL_OVERRIDE_RESET: False,
        CONF_MANUAL_OVERRIDE_DURATION: DEFAULT_MANUAL_OVERRIDE_DURATION,
        CONF_MANUAL_THRESHOLD: None,
        CONF_INTERP_START: None,
        CONF_INTERP_END: None,
        CONF_INTERP_LIST: None,
        CONF_INTERP_LIST_NEW: None,
        CONF_QUIET_START: None,
        CONF_QUIET_END: None,
        CONF_MAX_MOVES_HOUR: None,
        # the cover adapter (CoverGeometry)
        CONF_SUNSET_POS: None,
        CONF_SUNSET_OFFSET: None,
        CONF_FOV_LEFT: None,
        CONF_FOV_RIGHT: None,
        CONF_AZIMUTH: None,
        CONF_DEFAULT_HEIGHT: None,
        CONF_MAX_POSITION: None,
        CONF_MIN_POSITION: None,
        CONF_ENABLE_MAX_POSITION: False,
        CONF_ENABLE_MIN_POSITION: False,
        CONF_BLIND_SPOT_LEFT: None,
        CONF_BLIND_SPOT_RIGHT: None,
        CONF_BLIND_SPOT_ELEVATION: None,
        CONF_ENABLE_BLIND_SPOT: False,
        CONF_MIN_ELEVATION: None,
        CONF_MAX_ELEVATION: None,
        CONF_DISTANCE: None,
        CONF_HEIGHT_WIN: None,
        CONF_LENGTH_AWNING: None,
        CONF_AWNING_ANGLE: None,
        CONF_TILT_DISTANCE: None,
        CONF_TILT_DEPTH: None,
        CONF_TILT_MODE: None,
        CONF_OVERHANG_DEPTH: None,
        CONF_OVERHANG_HEIGHT: None,
        CONF_EYE_HEIGHT: None,
        CONF_OCCUPIED_DISTANCE: None,
        CONF_PRIVACY_MODE: None,
        CONF_PRIVACY_OFFSET: None,
        CONF_PRIVACY_POSITION: None,
        # the climate adapter (ClimateOptions)
        CONF_TEMP_ENTITY: None,
        CONF_TEMP_LOW: None,
        CONF_TEMP_HIGH: None,
        # 0: the plain threshold rule (the season has no hysteresis).
        CONF_TEMP_HYSTERESIS: 0,
        CONF_PRESENCE_ENTITY: None,
        CONF_WEATHER_ENTITY: None,
        CONF_WEATHER_STATE: None,
        CONF_OUTSIDETEMP_ENTITY: None,
        CONF_TRANSPARENT_BLIND: None,
        CONF_LUX_ENTITY: None,
        CONF_IRRADIANCE_ENTITY: None,
        CONF_LUX_THRESHOLD: None,
        CONF_IRRADIANCE_THRESHOLD: None,
        CONF_OUTSIDE_THRESHOLD: None,
    }
)

# The privacy offset (minutes after sunset) when privacy mode is on and no
# offset is stored. An offset of 0 ("close right at sunset") is kept.
PRIVACY_OFFSET_FALLBACK: Final = 30


def _read(options: Mapping[str, Any], key: str) -> Any:
    """One option as the runtime reads it (the ABSENT fallback when unset)."""
    return options.get(key, ABSENT[key])


def absent_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return the values ``options`` reads through fallbacks, by option.

    Writing the result into ``options`` changes no runtime read: each key
    gets the value its reads fell back to (mutable values are copies).
    """
    missing = {
        key: copy.deepcopy(value) for key, value in ABSENT.items() if key not in options
    }
    if CONF_SUNRISE_OFFSET not in options:
        missing[CONF_SUNRISE_OFFSET] = _sunrise_offset(options)
    return missing


def _sunrise_offset(options: Mapping[str, Any]) -> Any:
    """Read the sunrise offset: the sunset offset's value when unset."""
    return options.get(CONF_SUNRISE_OFFSET, _read(options, CONF_SUNSET_OFFSET))


@dataclass(frozen=True, slots=True)
class CoverGeometry:
    """What a cover adapter reads (``calculation.AdaptiveGeneralCover``).

    Field names are the adapter's. Values are taken as stored, except the
    privacy offset and position (see :meth:`from_options`).
    """

    sunset_pos: Any
    sunset_off: Any
    sunrise_off: Any
    """Falls back to the sunset offset when unset."""
    fov_left: Any
    fov_right: Any
    win_azi: Any
    h_def: Any
    max_pos: Any
    min_pos: Any
    max_pos_bool: Any
    min_pos_bool: Any
    blind_spot_left: Any
    blind_spot_right: Any
    blind_spot_elevation: Any
    blind_spot_on: Any
    min_elevation: Any
    max_elevation: Any
    # vertical blinds and awnings
    distance: Any
    h_win: Any
    # awnings
    awn_length: Any
    awn_angle: Any
    # venetian (tilt) blinds
    slat_distance: Any
    slat_depth: Any
    tilt_mode: Any
    # vertical blinds only (the adapter applies them)
    overhang_depth: Any
    overhang_height: Any
    eye_height: Any
    occupied_distance: Any
    # privacy after dusk
    privacy_mode: Any
    privacy_offset: Any
    """Minutes after sunset; 30 when unset or None."""
    privacy_position: Any
    """The privacy close position; 0 when unset, None or 0."""

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> CoverGeometry:
        """Read the adapter's options."""
        privacy_offset = _read(options, CONF_PRIVACY_OFFSET)
        return cls(
            sunset_pos=_read(options, CONF_SUNSET_POS),
            sunset_off=_read(options, CONF_SUNSET_OFFSET),
            sunrise_off=_sunrise_offset(options),
            fov_left=_read(options, CONF_FOV_LEFT),
            fov_right=_read(options, CONF_FOV_RIGHT),
            win_azi=_read(options, CONF_AZIMUTH),
            h_def=_read(options, CONF_DEFAULT_HEIGHT),
            max_pos=_read(options, CONF_MAX_POSITION),
            min_pos=_read(options, CONF_MIN_POSITION),
            max_pos_bool=_read(options, CONF_ENABLE_MAX_POSITION),
            min_pos_bool=_read(options, CONF_ENABLE_MIN_POSITION),
            blind_spot_left=_read(options, CONF_BLIND_SPOT_LEFT),
            blind_spot_right=_read(options, CONF_BLIND_SPOT_RIGHT),
            blind_spot_elevation=_read(options, CONF_BLIND_SPOT_ELEVATION),
            blind_spot_on=_read(options, CONF_ENABLE_BLIND_SPOT),
            min_elevation=_read(options, CONF_MIN_ELEVATION),
            max_elevation=_read(options, CONF_MAX_ELEVATION),
            distance=_read(options, CONF_DISTANCE),
            h_win=_read(options, CONF_HEIGHT_WIN),
            awn_length=_read(options, CONF_LENGTH_AWNING),
            awn_angle=_read(options, CONF_AWNING_ANGLE),
            slat_distance=_read(options, CONF_TILT_DISTANCE),
            slat_depth=_read(options, CONF_TILT_DEPTH),
            tilt_mode=_read(options, CONF_TILT_MODE),
            overhang_depth=_read(options, CONF_OVERHANG_DEPTH),
            overhang_height=_read(options, CONF_OVERHANG_HEIGHT),
            eye_height=_read(options, CONF_EYE_HEIGHT),
            occupied_distance=_read(options, CONF_OCCUPIED_DISTANCE),
            privacy_mode=_read(options, CONF_PRIVACY_MODE),
            # explicit None check: an offset of 0 ("close right at sunset")
            # must not be coerced to the 30-minute fallback
            privacy_offset=(
                PRIVACY_OFFSET_FALLBACK if privacy_offset is None else privacy_offset
            ),
            privacy_position=_read(options, CONF_PRIVACY_POSITION) or 0,
        )


@dataclass(frozen=True, slots=True)
class ClimateOptions:
    """What the climate adapter reads (``calculation.ClimateCoverData``)."""

    temp_entity: Any
    temp_low: Any
    temp_high: Any
    presence_entity: Any
    weather_entity: Any
    weather_condition: Any
    outside_entity: Any
    transparent_blind: Any
    lux_entity: Any
    irradiance_entity: Any
    lux_threshold: Any
    irradiance_threshold: Any
    temp_summer_outside: Any
    """The outside-temperature threshold."""
    temp_hysteresis: Any
    """How far past a threshold the season must go to flip (0: off)."""

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> ClimateOptions:
        """Read the climate adapter's options."""
        return cls(
            temp_entity=_read(options, CONF_TEMP_ENTITY),
            temp_low=_read(options, CONF_TEMP_LOW),
            temp_high=_read(options, CONF_TEMP_HIGH),
            presence_entity=_read(options, CONF_PRESENCE_ENTITY),
            weather_entity=_read(options, CONF_WEATHER_ENTITY),
            weather_condition=_read(options, CONF_WEATHER_STATE),
            outside_entity=_read(options, CONF_OUTSIDETEMP_ENTITY),
            transparent_blind=_read(options, CONF_TRANSPARENT_BLIND),
            lux_entity=_read(options, CONF_LUX_ENTITY),
            irradiance_entity=_read(options, CONF_IRRADIANCE_ENTITY),
            lux_threshold=_read(options, CONF_LUX_THRESHOLD),
            irradiance_threshold=_read(options, CONF_IRRADIANCE_THRESHOLD),
            temp_summer_outside=_read(options, CONF_OUTSIDE_THRESHOLD),
            temp_hysteresis=_read(options, CONF_TEMP_HYSTERESIS),
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
    geometry: CoverGeometry
    """What the cover adapter reads."""
    climate: ClimateOptions
    """What the climate adapter reads."""
    climate_mode: bool
    inverse_state: bool
    interpolation: bool
    return_sunset: bool | None
    ignore_intermediate: bool

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> ShadeConfig:
        """Read the per-refresh options, with the coordinator's defaults."""
        return cls(
            entities=options.get(CONF_ENTITIES, []),
            min_change=_read(options, CONF_DELTA_POSITION),
            time_threshold=_read(options, CONF_DELTA_TIME),
            start_time=_read(options, CONF_START_TIME),
            start_time_entity=_read(options, CONF_START_ENTITY),
            end_time=_read(options, CONF_END_TIME),
            end_time_entity=_read(options, CONF_END_ENTITY),
            manual_reset=_read(options, CONF_MANUAL_OVERRIDE_RESET),
            manual_duration=_read(options, CONF_MANUAL_OVERRIDE_DURATION),
            manual_threshold=_read(options, CONF_MANUAL_THRESHOLD),
            interp_start=_read(options, CONF_INTERP_START),
            interp_end=_read(options, CONF_INTERP_END),
            interp_list=_read(options, CONF_INTERP_LIST),
            interp_list_new=_read(options, CONF_INTERP_LIST_NEW),
            quiet_start=_read(options, CONF_QUIET_START),
            quiet_end=_read(options, CONF_QUIET_END),
            max_moves_hour=_read(options, CONF_MAX_MOVES_HOUR),
            sunset_pos=_read(options, CONF_SUNSET_POS),
            default_height=_read(options, CONF_DEFAULT_HEIGHT),
            privacy_position=_read(options, CONF_PRIVACY_POSITION),
            geometry=CoverGeometry.from_options(options),
            climate=ClimateOptions.from_options(options),
            climate_mode=_read(options, CONF_CLIMATE_MODE),
            inverse_state=_read(options, CONF_INVERSE_STATE),
            interpolation=_read(options, CONF_INTERP),
            return_sunset=_read(options, CONF_RETURN_SUNSET),
            ignore_intermediate=_read(options, CONF_MANUAL_IGNORE_INTERMEDIATE),
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
