"""The option spec: one declarative row per config-entry option.

Every settings surface is generated from ``OPTS`` (see ``schema.py``): the
setup wizard pages, the one-page options form, the ``change_settings`` and
``add_entry`` service schemas, the options ``add_entry`` gives an entry
without ``copy_from``, and the ranges of the live number entities.

Each row also records whether the setting is one-time or recurring and
where it lives, following docs/refactor_plan.md ("One-time vs recurring
settings"). P5 uses ``home`` and ``overridable_at`` for the house / floor /
area layers; until then tests/settings checks them against the plan.

Pure data: no Home Assistant imports, so the table can be read and tested
without hass.

``legacy`` records where a surface still differs from the row's canonical
shape. Each entry is drift that existed before the spec (tests/contract/
spec_parity.json pins it); a fix removes the entry, regenerates the parity
snapshot and adds a ledger entry. Keys are ``"<surface>.<attr>"`` with
surface one of ``form`` (wizard and options), ``wizard``, ``options``,
``service`` and ``number``, and attr one of ``min``, ``max``, ``step``,
``unit``, ``slider``, ``default`` and ``bounded`` (False: the service
applies no range). A per-temperature-unit value is written
``"<surface>.<attr>@<unit>"``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import KW_ONLY, dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final

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
    CONF_MODE,
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
    CONF_TEMP_LOW,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    CONF_TRANSPARENT_BLIND,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_STATE,
    DEFAULT_DEFAULT_HEIGHT,
    DEFAULT_EYE_HEIGHT,
    DEFAULT_MANUAL_OVERRIDE_DURATION,
    DEFAULT_OCCUPIED_DISTANCE,
    DEFAULT_TEMP_THRESHOLDS,
    DEFAULT_WEATHER_STATE,
    STRATEGY_MODE_BASIC,
    SensorType,
)


class Kind(StrEnum):
    """How a form shows the option (and so which selector it gets)."""

    NUMBER = "number"  # NumberSelector, slider or box
    INT = "int"  # plain integer field with a range
    BOOL = "bool"  # plain boolean field (a checkbox)
    SWITCH = "switch"  # BooleanSelector (a toggle)
    TIME = "time"  # TimeSelector
    DURATION = "duration"  # DurationSelector
    ENTITY = "entity"  # EntitySelector
    SELECT = "select"  # SelectSelector
    INTERNAL = "internal"  # never on a form


class Group(StrEnum):
    """Where the option sits on the wizard and on the options form.

    | Group          | Wizard page           | Options section   |
    |----------------|-----------------------|-------------------|
    | CLIMATE_TOGGLE | cover-type page, top  | climate, top      |
    | COVER          | cover-type page       | covers_geometry   |
    | SUN            | cover-type page       | sun_behavior      |
    | BLIND_SPOT     | blind_spot            | sun_behavior      |
    | INTERP         | interp                | sun_behavior      |
    | AUTOMATION     | automation            | automation_timing |
    | CLIMATE        | climate               | climate (when on) |
    | WEATHER        | weather               | climate (when on) |
    | NONE           | -                     | -                 |
    """

    CLIMATE_TOGGLE = "climate_toggle"
    COVER = "cover"
    SUN = "sun"
    BLIND_SPOT = "blind_spot"
    INTERP = "interp"
    AUTOMATION = "automation"
    CLIMATE = "climate"
    WEATHER = "weather"
    NONE = "none"


class Scope(StrEnum):
    """One-time (window setup) vs recurring (house level) settings."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"
    INTERNAL = "internal"


class Level(StrEnum):
    """A settings layer (P5 resolves window -> area -> floor -> house)."""

    HOUSE = "house"
    FLOOR = "floor"
    AREA = "area"
    WINDOW = "window"


class Coerce(StrEnum):
    """The value type the change_settings / add_entry services accept."""

    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    STR = "str"
    DICT = "dict"
    ENTITY_ID = "entity_id"
    STR_LIST = "str_list"
    ENUM = "enum"


@dataclass(frozen=True, kw_only=True)
class Service:
    """How the change_settings and add_entry services accept the option.

    The service applies the row's min/max; ``nullable`` also accepts None
    (to clear the option).
    """

    coerce: Coerce
    nullable: bool = False


@dataclass(frozen=True, kw_only=True)
class LiveNumber:
    """The option also has a live number entity (number.py owns its name).

    ``shows_default``: the entity shows the default while the option is
    unset (otherwise it shows unknown until set).
    """

    shows_default: bool = False


@dataclass(frozen=True, kw_only=True)
class UnitShape:
    """Range, step and default of an option in one HA temperature unit."""

    min: float
    max: float
    step: float
    default: float


# Unit marker: the option is stored and compared in HA's temperature unit.
TEMPERATURE: Final = "temperature"

ALL_COVER_TYPES: Final = frozenset(
    {SensorType.BLIND, SensorType.AWNING, SensorType.TILT}
)
POSITION_COVER_TYPES: Final = frozenset({SensorType.BLIND, SensorType.AWNING})
AWNING_ONLY: Final = frozenset({SensorType.AWNING})
TILT_ONLY: Final = frozenset({SensorType.TILT})


class _NoDefault:
    """Sentinel: the option has no default."""

    def __repr__(self) -> str:
        return "NO_DEFAULT"


NO_DEFAULT: Final = _NoDefault()
_EMPTY: Mapping[str, Any] = MappingProxyType({})
_SHAPE_ATTRS = ("min", "max", "step", "unit", "slider", "default", "bounded")


@dataclass(frozen=True)
class Opt:
    """One config-entry option and every surface that shows or accepts it.

    The first six fields are positional (the table's columns); the rest
    are keywords.
    """

    key: str
    kind: Kind
    group: Group
    scope: Scope
    # Where a recurring setting lives and which narrower layers may
    # override it (plan: "One-time vs recurring settings"). One-time
    # settings live on the window and have no override.
    home: Level | None
    overridable_at: tuple[Level, ...] = ()
    _: KW_ONLY
    cover_types: frozenset[str] = ALL_COVER_TYPES

    default: Any = NO_DEFAULT
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None  # TEMPERATURE: HA's temperature unit
    slider: bool = False  # NUMBER: a slider instead of a box
    by_temperature_unit: Mapping[str, UnitShape] | None = None

    # Selector details (SELECT / ENTITY / BLIND_SPOT)
    options: tuple[str, ...] = ()
    multiple: bool = False
    custom_value: bool = False
    translation_key: str | None = None
    domains: tuple[str, ...] = ()
    device_class: str | None = None
    cover_filter: bool = False  # ENTITY: covers that support this cover type
    max_from_fov: int | None = None  # wizard max = fov_left + fov_right + this

    wizard_required: bool = False
    clearable: bool = False  # options form: an absent field clears it
    baseline: bool = False  # add_entry without copy_from starts from default
    service: Service | None = None
    number: LiveNumber | None = None
    legacy: Mapping[str, Any] = field(default_factory=lambda: _EMPTY)

    @property
    def has_default(self) -> bool:
        """Whether the option has a default (a per-unit one counts)."""
        return self.default is not NO_DEFAULT or self.by_temperature_unit is not None

    def shape(self, surface: str, temperature_unit: str | None) -> dict[str, Any]:
        """Min, max, step, unit, slider, default and bounded on ``surface``.

        ``surface`` is ``wizard``, ``options``, ``service`` or ``number``.
        Starts from the canonical row, applies the per-unit shape, then the
        ``legacy`` drift for that surface. ``bounded`` is False where a
        service still applies no range.
        """
        shape: dict[str, Any] = {
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "unit": self.unit,
            "slider": self.slider,
            "default": self.default,
            "bounded": True,
        }
        if self.unit == TEMPERATURE and self.by_temperature_unit is not None:
            per_unit = self.by_temperature_unit.get(
                temperature_unit or "", self.by_temperature_unit["°C"]
            )
            shape.update(
                min=per_unit.min,
                max=per_unit.max,
                step=per_unit.step,
                unit=temperature_unit,
                default=per_unit.default,
            )
        surfaces = ("form", surface) if surface in ("wizard", "options") else (surface,)
        for name in surfaces:
            for attr in _SHAPE_ATTRS:
                for token in (f"{name}.{attr}", f"{name}.{attr}@{temperature_unit}"):
                    if token in self.legacy:
                        shape[attr] = self.legacy[token]
        return shape


H = Level.HOUSE
F = Level.FLOOR
A = Level.AREA
W = Level.WINDOW
ONE = Scope.ONE_TIME
REC = Scope.RECURRING

_FLOAT = Service(coerce=Coerce.FLOAT)
_FLOAT_OPTIONAL = Service(coerce=Coerce.FLOAT, nullable=True)
_ENTITY_ID = Service(coerce=Coerce.ENTITY_ID, nullable=True)
_TIME = Service(coerce=Coerce.STR, nullable=True)
_BOOL = Service(coerce=Coerce.BOOL)

# ------------------------------------------------------------------ drift
# Before P3 the services accepted any number for these (no range).
_ANY_NUMBER: Final = MappingProxyType({"service.bounded": False})
# Before P3 the options form showed the blind-spot edges as plain 0-90
# boxes; the wizard sizes its sliders from the FOV.
_BLIND_SPOT_OPTIONS: Final = MappingProxyType(
    {"options.max": 90, "options.unit": None, "options.slider": False}
)
# Before P3 the wizard and options form showed both climate thresholds as a
# unit-less 0-86 / 0-90 slider with step 1, the services accepted any
# number, and the °C numbers defaulted to 21 / 25.
_TEMP_LEGACY: Final = MappingProxyType(
    {
        "form.min": 0,
        "form.step": 1,
        "form.unit": "°",
        "form.slider": True,
        "service.bounded": False,
    }
)

# Climate thresholds per HA temperature unit (stored and compared in it).
_TEMP_LOW: Final = MappingProxyType(
    {
        "°C": UnitShape(min=5, max=30, step=0.5, default=DEFAULT_TEMP_THRESHOLDS["°C"][0]),
        "°F": UnitShape(min=40, max=90, step=0.5, default=DEFAULT_TEMP_THRESHOLDS["°F"][0]),
    }
)  # fmt: skip
_TEMP_HIGH: Final = MappingProxyType(
    {
        "°C": UnitShape(min=10, max=40, step=0.5, default=DEFAULT_TEMP_THRESHOLDS["°C"][1]),
        "°F": UnitShape(min=50, max=100, step=0.5, default=DEFAULT_TEMP_THRESHOLDS["°F"][1]),
    }
)  # fmt: skip

WEATHER_CONDITIONS: Final = (
    "clear-night", "clear", "cloudy", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant", "exceptional",
)  # fmt: skip

# Columns: key, kind, group, scope, home, overridable_at; then keywords.
# Row order is form order: within a group, the wizard page and the options
# section list the options in this order.
# fmt: off
OPTS: Final[tuple[Opt, ...]] = (
    # ---------------------------------------------------- climate toggle
    Opt(CONF_CLIMATE_MODE, Kind.SWITCH, Group.CLIMATE_TOGGLE, REC, H, (A,),
        default=False, baseline=True, service=_BOOL),
    # ---------------------------------------------------- cover geometry
    Opt(CONF_LENGTH_AWNING, Kind.NUMBER, Group.COVER, ONE, W,
        cover_types=AWNING_ONLY, default=2.1, min=0.3, max=6, step=0.01,
        unit="m", slider=True, wizard_required=True, service=_FLOAT_OPTIONAL,
        legacy=_ANY_NUMBER),
    Opt(CONF_AWNING_ANGLE, Kind.NUMBER, Group.COVER, ONE, W,
        cover_types=AWNING_ONLY, default=0, min=0, max=45, step=1, unit="°",
        slider=True, wizard_required=True, service=_FLOAT_OPTIONAL,
        legacy=_ANY_NUMBER),
    Opt(CONF_ENTITIES, Kind.ENTITY, Group.COVER, ONE, W,
        default=[], domains=("cover",), multiple=True, cover_filter=True),
    Opt(CONF_HEIGHT_WIN, Kind.NUMBER, Group.COVER, ONE, W,
        cover_types=POSITION_COVER_TYPES, default=2.1, min=0.1, max=10,
        step=0.01, unit="m", slider=True, wizard_required=True, baseline=True,
        service=_FLOAT, legacy={"form.max": 6}),
    Opt(CONF_DISTANCE, Kind.NUMBER, Group.COVER, ONE, W,
        cover_types=POSITION_COVER_TYPES, default=0.5, min=0.1, max=10,
        step=0.1, unit="m", slider=True, wizard_required=True, baseline=True,
        service=_FLOAT, legacy={"form.max": 2}),
    Opt(CONF_OVERHANG_DEPTH, Kind.NUMBER, Group.COVER, ONE, W,
        cover_types=POSITION_COVER_TYPES, min=0.1, max=5, step=0.01, unit="m",
        clearable=True, service=_FLOAT_OPTIONAL, number=LiveNumber(),
        legacy={**_ANY_NUMBER, "number.min": 0, "number.step": 0.05}),
    Opt(CONF_OVERHANG_HEIGHT, Kind.NUMBER, Group.COVER, ONE, W,
        cover_types=POSITION_COVER_TYPES, min=0.1, max=10, step=0.01, unit="m",
        clearable=True, service=_FLOAT_OPTIONAL, number=LiveNumber(),
        legacy={**_ANY_NUMBER, "number.min": 0.5, "number.step": 0.05}),
    Opt(CONF_EYE_HEIGHT, Kind.NUMBER, Group.COVER, REC, H, (A, W),
        cover_types=POSITION_COVER_TYPES, default=DEFAULT_EYE_HEIGHT, min=0.1,
        max=3, step=0.01, unit="m", clearable=True, service=_FLOAT_OPTIONAL,
        number=LiveNumber(),
        legacy={**_ANY_NUMBER, "number.min": 0.5, "number.step": 0.05}),
    Opt(CONF_OCCUPIED_DISTANCE, Kind.NUMBER, Group.COVER, REC, H, (A, W),
        cover_types=POSITION_COVER_TYPES, default=DEFAULT_OCCUPIED_DISTANCE,
        min=0.1, max=10, step=0.1, unit="m", clearable=True,
        service=_FLOAT_OPTIONAL, number=LiveNumber(), legacy=_ANY_NUMBER),
    Opt(CONF_TILT_DEPTH, Kind.NUMBER, Group.COVER, ONE, W,
        cover_types=TILT_ONLY, default=3, min=0.1, max=15, step=0.1,
        unit="cm", slider=True, wizard_required=True, service=_FLOAT_OPTIONAL,
        legacy=_ANY_NUMBER),
    Opt(CONF_TILT_DISTANCE, Kind.NUMBER, Group.COVER, ONE, W,
        cover_types=TILT_ONLY, default=2, min=0.1, max=15, step=0.1,
        unit="cm", slider=True, wizard_required=True, service=_FLOAT_OPTIONAL,
        legacy=_ANY_NUMBER),
    Opt(CONF_TILT_MODE, Kind.SELECT, Group.COVER, ONE, W,
        cover_types=TILT_ONLY, default="mode2", options=("mode1", "mode2"),
        translation_key="tilt_mode", wizard_required=True,
        service=Service(coerce=Coerce.ENUM, nullable=True)),
    # ---------------------------------------------------- sun behavior
    Opt(CONF_AZIMUTH, Kind.NUMBER, Group.SUN, ONE, W,
        default=180, min=0, max=359, step=1, unit="°", slider=True,
        wizard_required=True, baseline=True, service=_FLOAT),
    Opt(CONF_DEFAULT_HEIGHT, Kind.NUMBER, Group.SUN, REC, H, (A, W),
        default=DEFAULT_DEFAULT_HEIGHT, min=0, max=100, step=1, unit="%",
        slider=True, wizard_required=True, baseline=True, service=_FLOAT),
    Opt(CONF_MAX_POSITION, Kind.INT, Group.SUN, ONE, W,
        min=1, max=100, service=_FLOAT_OPTIONAL, legacy={"service.min": 0}),
    Opt(CONF_ENABLE_MAX_POSITION, Kind.BOOL, Group.SUN, ONE, W,
        default=False, baseline=True),
    Opt(CONF_MIN_POSITION, Kind.INT, Group.SUN, ONE, W,
        min=0, max=99, service=_FLOAT_OPTIONAL, legacy={"service.max": 100}),
    Opt(CONF_ENABLE_MIN_POSITION, Kind.BOOL, Group.SUN, ONE, W,
        default=False, baseline=True),
    Opt(CONF_MIN_ELEVATION, Kind.INT, Group.SUN, ONE, W,
        min=0, max=90, clearable=True, service=_FLOAT_OPTIONAL,
        legacy=_ANY_NUMBER),
    Opt(CONF_MAX_ELEVATION, Kind.INT, Group.SUN, ONE, W,
        min=0, max=90, clearable=True, service=_FLOAT_OPTIONAL,
        legacy=_ANY_NUMBER),
    Opt(CONF_FOV_LEFT, Kind.NUMBER, Group.SUN, ONE, W,
        default=90, min=1, max=90, step=1, unit="°", slider=True,
        wizard_required=True, baseline=True, service=_FLOAT),
    Opt(CONF_FOV_RIGHT, Kind.NUMBER, Group.SUN, ONE, W,
        default=90, min=1, max=90, step=1, unit="°", slider=True,
        wizard_required=True, baseline=True, service=_FLOAT),
    Opt(CONF_SUNSET_POS, Kind.NUMBER, Group.SUN, REC, H, (A, W),
        default=0, min=0, max=100, step=1, unit="%", slider=True,
        wizard_required=True, baseline=True, service=_FLOAT),
    Opt(CONF_SUNSET_OFFSET, Kind.NUMBER, Group.SUN, REC, H, (A,),
        default=0, step=1, unit="minutes", wizard_required=True,
        baseline=True, service=_FLOAT),
    Opt(CONF_SUNRISE_OFFSET, Kind.NUMBER, Group.SUN, REC, H, (A,),
        default=0, step=1, unit="minutes", wizard_required=True,
        baseline=True, service=_FLOAT),
    Opt(CONF_INVERSE_STATE, Kind.BOOL, Group.SUN, ONE, W,
        default=False, wizard_required=True, baseline=True),
    Opt(CONF_ENABLE_BLIND_SPOT, Kind.BOOL, Group.SUN, ONE, W,
        default=False, wizard_required=True, baseline=True),
    Opt(CONF_INTERP, Kind.BOOL, Group.SUN, ONE, W,
        default=False, wizard_required=True, baseline=True),
    # ---------------------------------------------------- blind spot
    Opt(CONF_BLIND_SPOT_LEFT, Kind.NUMBER, Group.BLIND_SPOT, ONE, W,
        default=0, min=0, step=1, unit="°", slider=True, max_from_fov=-1,
        wizard_required=True, clearable=True, legacy=_BLIND_SPOT_OPTIONS),
    Opt(CONF_BLIND_SPOT_RIGHT, Kind.NUMBER, Group.BLIND_SPOT, ONE, W,
        default=1, min=1, step=1, unit="°", slider=True, max_from_fov=0,
        wizard_required=True, clearable=True, legacy=_BLIND_SPOT_OPTIONS),
    Opt(CONF_BLIND_SPOT_ELEVATION, Kind.INT, Group.BLIND_SPOT, ONE, W,
        min=0, max=90, clearable=True),
    # ---------------------------------------------------- interpolation
    Opt(CONF_INTERP_START, Kind.INT, Group.INTERP, ONE, W,
        min=0, max=100, clearable=True),
    Opt(CONF_INTERP_END, Kind.INT, Group.INTERP, ONE, W,
        min=0, max=100, clearable=True),
    Opt(CONF_INTERP_LIST, Kind.SELECT, Group.INTERP, ONE, W,
        default=[], options=("0", "50", "100"), multiple=True,
        custom_value=True, baseline=True),
    Opt(CONF_INTERP_LIST_NEW, Kind.SELECT, Group.INTERP, ONE, W,
        default=[], options=("0", "50", "100"), multiple=True,
        custom_value=True, baseline=True),
    # ---------------------------------------------------- automation
    Opt(CONF_DELTA_POSITION, Kind.NUMBER, Group.AUTOMATION, REC, H,
        default=1, min=1, max=90, step=1, unit="%", slider=True,
        wizard_required=True, baseline=True,
        service=Service(coerce=Coerce.INT)),
    Opt(CONF_DELTA_TIME, Kind.NUMBER, Group.AUTOMATION, REC, H,
        default=2, min=0, step=1, unit="minutes", baseline=True,
        service=Service(coerce=Coerce.INT), legacy={"form.min": 2}),
    Opt(CONF_START_TIME, Kind.TIME, Group.AUTOMATION, REC, H, (A,),
        default="00:00:00", baseline=True, service=_TIME),
    Opt(CONF_START_ENTITY, Kind.ENTITY, Group.AUTOMATION, REC, H, (A,),
        domains=("sensor", "input_datetime"), clearable=True),
    Opt(CONF_MANUAL_OVERRIDE_DURATION, Kind.DURATION, Group.AUTOMATION, REC,
        H, (A,), default=DEFAULT_MANUAL_OVERRIDE_DURATION,
        wizard_required=True, baseline=True,
        service=Service(coerce=Coerce.DICT, nullable=True)),
    Opt(CONF_MANUAL_OVERRIDE_RESET, Kind.BOOL, Group.AUTOMATION, REC, H, (A,),
        default=False, wizard_required=True, baseline=True, service=_BOOL),
    Opt(CONF_MANUAL_THRESHOLD, Kind.INT, Group.AUTOMATION, REC, H, (A,),
        min=0, max=99, clearable=True,
        service=Service(coerce=Coerce.INT, nullable=True)),
    Opt(CONF_MANUAL_IGNORE_INTERMEDIATE, Kind.BOOL, Group.AUTOMATION, REC, H,
        (A,), default=False),
    Opt(CONF_END_TIME, Kind.TIME, Group.AUTOMATION, REC, H, (A,),
        default="00:00:00", baseline=True, service=_TIME),
    Opt(CONF_END_ENTITY, Kind.ENTITY, Group.AUTOMATION, REC, H, (A,),
        domains=("sensor", "input_datetime"), clearable=True),
    Opt(CONF_RETURN_SUNSET, Kind.BOOL, Group.AUTOMATION, REC, H, (A,),
        default=False),
    Opt(CONF_PRIVACY_MODE, Kind.BOOL, Group.AUTOMATION, ONE, W,
        default=False, service=_BOOL),
    Opt(CONF_PRIVACY_OFFSET, Kind.NUMBER, Group.AUTOMATION, REC, H, (A,),
        default=30, min=0, max=180, step=5, unit="minutes", service=_FLOAT,
        number=LiveNumber(shows_default=True), legacy={"number.unit": "min"}),
    Opt(CONF_PRIVACY_POSITION, Kind.NUMBER, Group.AUTOMATION, REC, H, (A,),
        default=0, min=0, max=100, step=1, unit="%", service=_FLOAT),
    Opt(CONF_QUIET_START, Kind.TIME, Group.AUTOMATION, REC, H,
        clearable=True, service=_TIME),
    Opt(CONF_QUIET_END, Kind.TIME, Group.AUTOMATION, REC, H,
        clearable=True, service=_TIME),
    Opt(CONF_MAX_MOVES_HOUR, Kind.INT, Group.AUTOMATION, REC, H,
        min=1, max=60, clearable=True,
        service=Service(coerce=Coerce.INT, nullable=True)),
    # ---------------------------------------------------- climate
    Opt(CONF_TEMP_ENTITY, Kind.ENTITY, Group.CLIMATE, REC, F, (A,),
        domains=("climate", "sensor"), wizard_required=True,
        service=_ENTITY_ID),
    Opt(CONF_TEMP_LOW, Kind.NUMBER, Group.CLIMATE, REC, H, (F, A),
        unit=TEMPERATURE, by_temperature_unit=_TEMP_LOW, wizard_required=True,
        service=_FLOAT_OPTIONAL, number=LiveNumber(shows_default=True),
        legacy={**_TEMP_LEGACY, "form.max": 86, "number.default@°C": 21}),
    Opt(CONF_TEMP_HIGH, Kind.NUMBER, Group.CLIMATE, REC, H, (F, A),
        unit=TEMPERATURE, by_temperature_unit=_TEMP_HIGH, wizard_required=True,
        service=_FLOAT_OPTIONAL, number=LiveNumber(shows_default=True),
        legacy={**_TEMP_LEGACY, "form.max": 90, "number.default@°C": 25}),
    Opt(CONF_OUTSIDETEMP_ENTITY, Kind.ENTITY, Group.CLIMATE, REC, H,
        domains=("sensor",), clearable=True, service=_ENTITY_ID),
    Opt(CONF_OUTSIDE_THRESHOLD, Kind.INT, Group.CLIMATE, REC, H,
        default=0, min=0, max=100, service=_FLOAT_OPTIONAL,
        legacy=_ANY_NUMBER),
    Opt(CONF_PRESENCE_ENTITY, Kind.ENTITY, Group.CLIMATE, REC, H,
        domains=("device_tracker", "zone", "binary_sensor", "input_boolean"),
        clearable=True, service=_ENTITY_ID),
    Opt(CONF_LUX_ENTITY, Kind.ENTITY, Group.CLIMATE, REC, H,
        domains=("sensor",), device_class="illuminance", clearable=True),
    Opt(CONF_LUX_THRESHOLD, Kind.NUMBER, Group.CLIMATE, REC, H,
        default=1000, step=1, unit="lux", service=_FLOAT_OPTIONAL),
    Opt(CONF_IRRADIANCE_ENTITY, Kind.ENTITY, Group.CLIMATE, REC, H,
        domains=("sensor",), device_class="irradiance", clearable=True),
    Opt(CONF_IRRADIANCE_THRESHOLD, Kind.NUMBER, Group.CLIMATE, REC, H,
        default=300, step=1, unit="W/m²", service=_FLOAT_OPTIONAL),
    Opt(CONF_TRANSPARENT_BLIND, Kind.SWITCH, Group.CLIMATE, ONE, W,
        default=False),
    Opt(CONF_WEATHER_ENTITY, Kind.ENTITY, Group.CLIMATE, REC, H,
        domains=("weather",), clearable=True, service=_ENTITY_ID),
    # ---------------------------------------------------- weather
    Opt(CONF_WEATHER_STATE, Kind.SELECT, Group.WEATHER, REC, H,
        default=DEFAULT_WEATHER_STATE, options=WEATHER_CONDITIONS,
        multiple=True, service=Service(coerce=Coerce.STR_LIST)),
    # ---------------------------------------------------- internal
    # The control strategy ("basic"), not the wizard's cover-type picker
    # that shares the CONF_MODE key on the first page.
    Opt(CONF_MODE, Kind.INTERNAL, Group.NONE, Scope.INTERNAL, None,
        default=STRATEGY_MODE_BASIC, baseline=True),
)
# fmt: on

OPTS_BY_KEY: Final[Mapping[str, Opt]] = MappingProxyType({opt.key: opt for opt in OPTS})


def opts_in(group: Group, cover_type: str | None = None) -> tuple[Opt, ...]:
    """Rows of one group, in form order, optionally for one cover type."""
    return tuple(
        opt
        for opt in OPTS
        if opt.group is group and (cover_type is None or cover_type in opt.cover_types)
    )
