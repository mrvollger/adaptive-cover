"""Voluptuous schemas and selectors generated from the option spec.

Every settings surface comes from ``spec.OPTS``:

- the one-screen setup form that adds a window and reconfigures it
  (``setup_section_fields``, ``setup_schema``), with its presets and
  "Copy from" values;
- the one-page options form sections (``options_section_fields``);
- the ``change_settings`` and ``add_entry`` service schemas, and the
  options ``add_entry`` gives an entry without ``copy_from``;
- the ``set_profile`` service schema (every recurring setting);
- the ranges of the live number entities (``number_shape``).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

import voluptuous as vol
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from ..const import (
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_DISTANCE,
    CONF_ENABLE_BLIND_SPOT,
    CONF_ENTITIES,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_SENSOR_TYPE,
    SensorType,
)
from .spec import (
    NO_DEFAULT,
    OPTS,
    OPTS_BY_KEY,
    Coerce,
    Group,
    Kind,
    Opt,
    Scope,
    opts_in,
)

ENTITY_ID_PATTERN: Final = r"^[a-z_]+\.[a-z0-9_]+$"

_COVER_FEATURE: Final = {
    SensorType.BLIND: "cover.CoverEntityFeature.SET_POSITION",
    SensorType.AWNING: "cover.CoverEntityFeature.SET_POSITION",
    SensorType.TILT: "cover.CoverEntityFeature.SET_TILT_POSITION",
}

# Options form: section -> groups, in order. The climate section holds only
# the toggle while climate mode is off (so the feature stays discoverable).
OPTIONS_SECTIONS: Final = {
    "covers_geometry": (Group.COVER,),
    "sun_behavior": (Group.SUN, Group.BLIND_SPOT, Group.INTERP),
    "automation_timing": (Group.AUTOMATION,),
    "climate": (Group.CLIMATE_TOGGLE, Group.CLIMATE, Group.WEATHER),
}
_CLIMATE_OFF_GROUPS: Final = (Group.CLIMATE_TOGGLE,)

# Every option a form shows (a new window stores all of them).
SETUP_OPTION_KEYS: Final = frozenset(
    opt.key for opt in OPTS if opt.group is not Group.NONE
)
# Form keys where "absent from the submitted form" clears the option.
CLEARABLE_KEYS: Final = frozenset(opt.key for opt in OPTS if opt.clearable)


# ------------------------------------------------------------- selectors


def _number_selector(opt: Opt, shape: Mapping[str, Any], fov_span: float | None):
    config: dict[str, Any] = {"mode": "slider" if shape["slider"] else "box"}
    maximum = shape["max"]
    if opt.max_from_fov is not None and fov_span is not None:
        maximum = fov_span + opt.max_from_fov
    for name, value in (
        ("min", shape["min"]),
        ("max", maximum),
        ("step", shape["step"]),
        ("unit_of_measurement", shape["unit"]),
    ):
        if value is not None:
            config[name] = value
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def _entity_selector(opt: Opt, cover_type: str | None) -> selector.EntitySelector:
    if opt.cover_filter:
        # No cover type yet (the setup form picks it on the same screen):
        # covers that suit any type.
        features = (
            [_COVER_FEATURE[cover_type]]
            if cover_type is not None
            else sorted(set(_COVER_FEATURE.values()))
        )
        return selector.EntitySelector(
            selector.EntitySelectorConfig(
                multiple=opt.multiple,
                filter=selector.EntityWithDeviceFilterSelectorConfig(
                    domain=list(opt.domains), supported_features=features
                ),
            )
        )
    config: dict[str, Any] = {"domain": list(opt.domains)}
    if opt.device_class is not None:
        config["device_class"] = opt.device_class
    if opt.multiple:
        config["multiple"] = True
    return selector.EntitySelector(selector.EntitySelectorConfig(**config))


def _select_selector(opt: Opt) -> selector.SelectSelector:
    config: dict[str, Any] = {"options": list(opt.options)}
    if opt.multiple:
        config["multiple"] = True
    if opt.custom_value:
        config["custom_value"] = True
    if opt.translation_key is not None:
        config["translation_key"] = opt.translation_key
    return selector.SelectSelector(selector.SelectSelectorConfig(**config))


def form_validator(
    opt: Opt,
    surface: str,
    *,
    cover_type: str | None = None,
    temperature_unit: str | None = None,
    fov_span: float | None = None,
) -> Any:
    """Return the selector (or plain validator) a form shows for ``opt``."""
    shape = opt.shape(surface, temperature_unit)
    if opt.kind is Kind.NUMBER:
        return _number_selector(opt, shape, fov_span)
    if opt.kind is Kind.INT:
        return vol.All(vol.Coerce(int), vol.Range(min=shape["min"], max=shape["max"]))
    if opt.kind is Kind.ENTITY:
        return _entity_selector(opt, cover_type)
    if opt.kind is Kind.SELECT:
        return _select_selector(opt)
    simple = {
        Kind.BOOL: lambda: bool,
        Kind.SWITCH: selector.BooleanSelector,
        Kind.TIME: selector.TimeSelector,
        Kind.DURATION: selector.DurationSelector,
    }
    if opt.kind in simple:
        return simple[opt.kind]()
    raise ValueError(f"{opt.key}: {opt.kind} has no form field")


def _default_factory(value: Any) -> Any:
    """Wrap a marker default; lists and dicts get a fresh copy per use."""
    if isinstance(value, (list, dict)):
        return lambda: copy.deepcopy(value)
    return value


# ------------------------------------------------------------ setup form
#
# One screen adds a window, and the same screen reconfigures it (plan P6).
# Its sections, in order. Each spec row lands in exactly one
# (``setup_section``), so a new row shows up without touching this table.
#
# | Section              | Scope     | Shows                                         |
# |----------------------|-----------|-----------------------------------------------|
# | window (expanded)    | one-time  | Copy from, preset, name, cover, cover type,   |
# |                      |           | azimuth, field of view, the type's geometry   |
# | sun_limits           | one-time  | min/max sun elevation, blind spot             |
# | advanced             | one-time  | position limits, inverse, interpolation,      |
# |                      |           | transparent blind, privacy opt-in             |
# | exceptions_positions | recurring | glare band, default/sunset positions, offsets |
# | exceptions_schedule  | recurring | deltas, times, manual moves, privacy, quiet   |
# | exceptions_climate   | recurring | climate mode, sensors, thresholds, weather    |
#
# Recurring settings belong to the house (plan: "One-time vs recurring
# settings"); the window form shows them only in the collapsed exceptions
# sections. Until the house layer lands (P5) each window stores its own
# copy, which is what the runtime reads, so they start at the spec
# defaults (the owner's values) and stay editable.

# The spec calls the setup surface "wizard" (``Opt.shape``, ``legacy``).
SETUP_SURFACE: Final = "wizard"

# Form-only fields of the Window section (not options).
FIELD_COPY_FROM: Final = "copy_from"
FIELD_PRESET: Final = "preset"
FIELD_NAME: Final = "name"
FIELD_SENSOR_TYPE: Final = CONF_SENSOR_TYPE

COVER_TYPES: Final = (SensorType.BLIND, SensorType.AWNING, SensorType.TILT)

WINDOW_SECTION: Final = "window"
ONE_TIME_SECTIONS: Final = (WINDOW_SECTION, "sun_limits", "advanced")
EXCEPTION_SECTIONS: Final = (
    "exceptions_positions",
    "exceptions_schedule",
    "exceptions_climate",
)
SETUP_SECTIONS: Final = ONE_TIME_SECTIONS + EXCEPTION_SECTIONS

# Where the window faces: the Window section shows these right after the
# cover and its type, before the geometry.
_FACING: Final = (CONF_AZIMUTH, CONF_FOV_LEFT, CONF_FOV_RIGHT)
_SUN_LIMITS: Final = frozenset(
    {CONF_MIN_ELEVATION, CONF_MAX_ELEVATION, CONF_ENABLE_BLIND_SPOT}
)
_EXCEPTIONS_BY_GROUP: Final = MappingProxyType(
    {
        Group.COVER: "exceptions_positions",
        Group.SUN: "exceptions_positions",
        Group.AUTOMATION: "exceptions_schedule",
        Group.CLIMATE_TOGGLE: "exceptions_climate",
        Group.CLIMATE: "exceptions_climate",
        Group.WEATHER: "exceptions_climate",
    }
)


# The blind-spot sliders span the widest field of view: the FOV is on the
# same screen, so it cannot size them, and any stored edge stays in range.
FULL_FOV_SPAN: Final = sum(
    OPTS_BY_KEY[key].max or 0 for key in (CONF_FOV_LEFT, CONF_FOV_RIGHT)
)

# What identifies a window: never copied from another window.
IDENTITY_KEYS: Final = frozenset({FIELD_NAME, CONF_COVER_ENTITY, CONF_ENTITIES})

# Geometry presets, taken from the owner's windows (plan: "Built-in
# defaults"). A preset fills geometry only: never the name, cover, cover
# type or a recurring setting. Every preset sets every key in PRESET_KEYS
# (None clears one), so switching presets leaves nothing behind.
PRESET_KEYS: Final = (
    CONF_HEIGHT_WIN,
    CONF_DISTANCE,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_MIN_ELEVATION,
    CONF_MAX_ELEVATION,
)


def _preset(
    *,
    fov: tuple[int, int],
    overhang: tuple[float, float] | None = None,
    elevation: tuple[int | None, int | None] = (None, None),
) -> Mapping[str, Any]:
    """Return a 2 m window, glare zone 10 cm, with this FOV, overhang and sun limits."""
    depth, height = overhang or (None, None)
    values = (2.0, 0.1, *fov, depth, height, *elevation)
    return MappingProxyType(dict(zip(PRESET_KEYS, values, strict=True)))


PRESETS: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType(
    {
        # A plain window, 60° each side.
        "window": _preset(fov=(60, 60)),
        # A window under a balcony or eave (the south windows).
        "window_overhang": _preset(fov=(50, 50), overhang=(1.2, 2.6), elevation=(5, None)),
        # A glass door under an overhang (the doors to the deck).
        "glass_door_overhang": _preset(fov=(40, 40), overhang=(1.2, 2.3), elevation=(5, 40)),
    }
)  # fmt: skip


def setup_section(opt: Opt) -> str:
    """Return the setup-form section that shows ``opt`` (see the table above)."""
    if opt.scope is Scope.RECURRING:
        return _EXCEPTIONS_BY_GROUP[opt.group]
    if opt.key in _FACING or opt.group is Group.COVER:
        return WINDOW_SECTION
    if opt.key in _SUN_LIMITS or opt.group is Group.BLIND_SPOT:
        return "sun_limits"
    return "advanced"


def setup_opts(section_name: str, cover_type: str) -> tuple[Opt, ...]:
    """Spec rows one setup-form section shows for ``cover_type``, in form order.

    Spec order, except that the Window section starts with the cover, then
    where the window faces, then the geometry.
    """
    opts = [
        opt
        for opt in OPTS
        if opt.group is not Group.NONE
        and cover_type in opt.cover_types
        and setup_section(opt) == section_name
    ]
    if section_name == WINDOW_SECTION:
        first = (CONF_COVER_ENTITY, *_FACING)
        opts.sort(
            key=lambda opt: first.index(opt.key) if opt.key in first else len(first)
        )
    return tuple(opts)


def copy_from_values(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> dict[str, Any]:
    """Return what "Copy from" takes from a window: every form value but its identity.

    ``data`` and ``options`` are the source window's entry data and
    options. Every form key is set (None where the source has no value),
    so copying from a second window leaves nothing of the first behind.
    The cover type comes along: the geometry belongs to it.
    """
    values: dict[str, Any] = {
        opt.key: copy.deepcopy(options.get(opt.key))
        for opt in OPTS
        if opt.key in SETUP_OPTION_KEYS and opt.key not in IDENTITY_KEYS
    }
    values[FIELD_SENSOR_TYPE] = data.get(CONF_SENSOR_TYPE) or SensorType.BLIND
    return values


def preset_values(preset: str) -> dict[str, Any]:
    """Return the geometry one preset fills in (see ``PRESETS``)."""
    return dict(PRESETS[preset])


def _suggested(value: Any) -> dict[str, Any]:
    """Marker keywords that pre-fill a field with ``value`` (None: nothing)."""
    return {} if value is None else {"description": {"suggested_value": value}}


def _setup_marker(
    opt: Opt, values: Mapping[str, Any], temperature_unit: str | None
) -> vol.Marker:
    """Return the setup form's field for ``opt``: spec default, current value shown.

    Only the cover must be picked. A field the spec requires on setup stays
    required where it has a default (it can never be left empty); one
    without a default (the indoor temperature sensor) is optional, because
    its section is optional now.
    """
    default = opt.shape(SETUP_SURFACE, temperature_unit)["default"]
    required = opt.key == CONF_COVER_ENTITY or (
        opt.wizard_required and default is not NO_DEFAULT
    )
    marker_cls = vol.Required if required else vol.Optional
    kwargs = _suggested(values.get(opt.key))
    if default is not NO_DEFAULT:
        kwargs["default"] = _default_factory(default)
    return marker_cls(opt.key, **kwargs)


def _select(**config: Any) -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(**config))


def _start_fields(
    values: Mapping[str, Any], windows: Mapping[str, str]
) -> dict[vol.Marker, Any]:
    """Copy from (only when there is a window to copy), preset and name."""
    fields: dict[vol.Marker, Any] = {}
    if windows:
        marker = vol.Optional(
            FIELD_COPY_FROM, **_suggested(values.get(FIELD_COPY_FROM))
        )
        fields[marker] = _select(
            options=[
                selector.SelectOptionDict(value=entry_id, label=title)
                for entry_id, title in windows.items()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    marker = vol.Optional(FIELD_PRESET, **_suggested(values.get(FIELD_PRESET)))
    fields[marker] = _select(
        options=list(PRESETS),
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key=FIELD_PRESET,
    )
    marker = vol.Optional(FIELD_NAME, **_suggested(values.get(FIELD_NAME)))
    fields[marker] = selector.TextSelector()
    return fields


def _type_field(cover_type: str) -> dict[vol.Marker, Any]:
    """Return the cover type field; left as is, it keeps the type the form shows."""
    marker = vol.Required(FIELD_SENSOR_TYPE, default=cover_type)
    return {
        marker: _select(options=list(COVER_TYPES), translation_key=FIELD_SENSOR_TYPE)
    }


def setup_section_fields(
    cover_type: str,
    *,
    values: Mapping[str, Any],
    temperature_unit: str | None,
    windows: Mapping[str, str] | None = None,
    recurring: bool = True,
) -> dict[str, dict[vol.Marker, Any]]:
    """``{section: fields}`` of the setup form for one cover type.

    ``values`` pre-fills the fields (current, copied or preset values);
    every other field shows its spec default. ``windows`` (entry_id ->
    title) are the windows "Copy from" offers. ``recurring=False`` leaves
    out the exceptions sections (the reconfigure step: one-time settings
    only).
    """
    sections: dict[str, dict[vol.Marker, Any]] = {}
    for name in SETUP_SECTIONS if recurring else ONE_TIME_SECTIONS:
        fields: dict[vol.Marker, Any] = {}
        if name == WINDOW_SECTION:
            fields |= _start_fields(values, windows or {})
        for opt in setup_opts(name, cover_type):
            fields[_setup_marker(opt, values, temperature_unit)] = form_validator(
                opt,
                SETUP_SURFACE,
                # The cover field offers covers of every type: the type is
                # picked on the same screen.
                cover_type=None if opt.key == CONF_COVER_ENTITY else cover_type,
                temperature_unit=temperature_unit,
                fov_span=FULL_FOV_SPAN,
            )
            if opt.key == CONF_COVER_ENTITY:
                fields |= _type_field(cover_type)
        sections[name] = fields
    return sections


def setup_schema(
    section_fields: Mapping[str, Mapping[vol.Marker, Any]],
    *,
    expanded: frozenset[str] = frozenset(),
) -> vol.Schema:
    """Assemble the sectioned setup form: the Window section and ``expanded`` open."""
    return vol.Schema(
        {
            vol.Required(name): section(
                vol.Schema(dict(fields)),
                {"collapsed": name != WINDOW_SECTION and name not in expanded},
            )
            for name, fields in section_fields.items()
        }
    )


def flatten_sections(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Merge a sectioned form's ``{section: {field: value}}`` into one dict."""
    flat: dict[str, Any] = {}
    for values in user_input.values():
        if isinstance(values, Mapping):
            flat.update(values)
    return flat


# ---------------------------------------------------------- options form


def options_section_fields(
    cover_type: str,
    *,
    climate_on: bool,
    options: Mapping[str, Any],
    temperature_unit: str | None,
) -> dict[str, dict[vol.Marker, Any]]:
    """``{section: fields}`` of the one-page options form.

    Every field is optional and pre-filled with the entry's current value.
    """
    sections: dict[str, dict[vol.Marker, Any]] = {}
    for name, groups in OPTIONS_SECTIONS.items():
        if name == "climate" and not climate_on:
            groups = _CLIMATE_OFF_GROUPS
        sections[name] = {
            vol.Optional(
                opt.key, description={"suggested_value": options.get(opt.key)}
            ): form_validator(
                opt,
                "options",
                cover_type=cover_type,
                temperature_unit=temperature_unit,
            )
            for group in groups
            for opt in opts_in(group, cover_type)
        }
    return sections


# -------------------------------------------------------------- services

_COERCERS: Final = {
    Coerce.FLOAT: lambda opt: vol.Coerce(float),
    Coerce.INT: lambda opt: vol.Coerce(int),
    # vol.Boolean is a decorated validator factory; its stub hides that.
    Coerce.BOOL: lambda opt: vol.Boolean(),  # pyright: ignore[reportCallIssue]
    Coerce.STR: lambda opt: str,
    Coerce.DICT: lambda opt: dict,
    Coerce.ENTITY_ID: lambda opt: vol.Match(ENTITY_ID_PATTERN),
    Coerce.STR_LIST: lambda opt: vol.All(vol.Coerce(list), [str]),
    Coerce.ENUM: lambda opt: vol.In(list(opt.options)),
}


def service_validator(opt: Opt, temperature_unit: str | None = None) -> Any:
    """How change_settings and add_entry validate ``opt``."""
    service = opt.service
    if service is None:
        raise ValueError(f"{opt.key} is not a service field")
    shape = opt.shape("service", temperature_unit)
    validator = _COERCERS[service.coerce](opt)
    ranged = shape["bounded"] and (shape["min"] is not None or shape["max"] is not None)
    if service.coerce in (Coerce.FLOAT, Coerce.INT) and ranged:
        validator = vol.All(validator, vol.Range(min=shape["min"], max=shape["max"]))
    if service.nullable:
        validator = vol.Any(None, validator)
    return validator


def changeable_options(temperature_unit: str | None = None) -> dict[str, Any]:
    """Option key -> validator for everything the services may change.

    Not changeable: name and sensor_type (entry data), the interpolation
    lists (shape-coupled), and cover membership (the options flow re-wires
    the listeners).
    """
    return {
        opt.key: service_validator(opt, temperature_unit)
        for opt in OPTS
        if opt.service is not None
    }


def add_entry_schema(temperature_unit: str | None = None) -> vol.Schema:
    """Build the add_entry service schema: identity + any changeable option.

    The window's cover is ``cover``. ``covers`` (a list) is still accepted
    for scripts written before P3; the service takes exactly one of them,
    with exactly one cover (ADR 0002).
    """
    schema: dict[vol.Marker, Any] = {
        vol.Required("name"): str,
        vol.Optional("cover"): vol.Match(ENTITY_ID_PATTERN),
        vol.Optional("covers"): [str],
        vol.Optional("copy_from"): str,
        vol.Optional("sensor_type"): vol.In(
            [SensorType.BLIND, SensorType.AWNING, SensorType.TILT]
        ),
    }
    for key, validator in changeable_options(temperature_unit).items():
        schema[vol.Optional(key)] = validator
    return vol.Schema(schema)


def change_settings_schema(temperature_unit: str | None = None) -> vol.Schema:
    """Build the change_settings schema: entry + rename + any changeable option."""
    schema: dict[vol.Marker, Any] = {
        vol.Required("config_entry"): str,
        # entry-data rename (title + device name + log prefix)
        vol.Optional("name"): vol.All(str, vol.Length(min=1)),
    }
    for key, validator in changeable_options(temperature_unit).items():
        schema[vol.Optional(key)] = validator
    return vol.Schema(schema)


PROFILE_SCOPES: Final = ("house", "floor", "area")


def profile_validator(opt: Opt, temperature_unit: str | None = None) -> Any:
    """How ``set_profile`` validates ``opt`` (a recurring setting).

    The option's service validator where it has one; a toggle or a
    checkbox takes a boolean, an entity field an entity id. None is always
    accepted: on a floor or an area it removes the value (the house decides
    whether it may be empty, ``layers.async_set_profile``).
    """
    if opt.service is not None:
        validator = service_validator(opt, temperature_unit)
    elif opt.kind in (Kind.BOOL, Kind.SWITCH, Kind.INTERNAL):
        # vol.Boolean is a decorated validator factory; its stub hides that.
        validator = vol.Boolean()  # pyright: ignore[reportCallIssue]
    elif opt.kind is Kind.ENTITY:
        validator = vol.Match(ENTITY_ID_PATTERN)
    else:
        raise ValueError(f"{opt.key} has no set_profile validator")
    return vol.Any(None, validator)


def may_be_empty(opt: Opt) -> bool:
    """Whether ``opt`` may be stored as None (an entity, or a nullable service field)."""
    return opt.kind is Kind.ENTITY or (opt.service is not None and opt.service.nullable)


def set_profile_schema(
    spec: tuple[Opt, ...] | list[Opt], temperature_unit: str | None = None
) -> vol.Schema:
    """Build the set_profile schema: scope, id and every recurring setting.

    Which level may store which setting is checked when the call runs
    (``layers.check_profile_keys``), from the spec's home and
    overridable_at levels.
    """
    schema: dict[vol.Marker, Any] = {
        vol.Required("scope"): vol.In(PROFILE_SCOPES),
        vol.Optional("id"): vol.All(str, vol.Length(min=1)),
    }
    recurring = [opt for opt in spec if opt.scope is Scope.RECURRING]
    for opt in recurring:
        schema[vol.Optional(opt.key)] = profile_validator(opt, temperature_unit)
    return vol.Schema(schema)


def add_entry_baseline() -> dict[str, Any]:
    """Return the options add_entry starts from when it has no copy_from."""
    return {
        opt.key: copy.deepcopy(opt.default)
        for opt in OPTS
        if opt.baseline and opt.default is not NO_DEFAULT
    }


# --------------------------------------------------------------- numbers


@dataclass(frozen=True)
class NumberShape:
    """Range, step, unit and unset-default of a live number entity."""

    min: float
    max: float
    step: float
    unit: str | None
    default: float | None


def number_shape(key: str, temperature_unit: str | None) -> NumberShape:
    """How the live number entity for ``key`` shows it in HA's unit."""
    opt = OPTS_BY_KEY[key]
    if opt.number is None:
        raise ValueError(f"{key} has no live number")
    shape = opt.shape("number", temperature_unit)
    default = shape["default"]
    if not opt.number.shows_default or default is NO_DEFAULT:
        default = None
    return NumberShape(
        min=shape["min"],
        max=shape["max"],
        step=shape["step"],
        unit=shape["unit"],
        default=default,
    )
