"""Voluptuous schemas and selectors generated from the option spec.

Every settings surface comes from ``spec.OPTS``:

- the setup wizard pages (``wizard_type_schema``, ``wizard_schema``);
- the one-page options form sections (``options_section_fields``);
- the ``change_settings`` and ``add_entry`` service schemas, and the
  options ``add_entry`` gives an entry without ``copy_from``;
- the ranges of the live number entities (``number_shape``).
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import voluptuous as vol
from homeassistant.helpers import selector

from ..const import SensorType
from .spec import NO_DEFAULT, OPTS, OPTS_BY_KEY, Coerce, Group, Kind, Opt, opts_in

ENTITY_ID_PATTERN: Final = r"^[a-z_]+\.[a-z0-9_]+$"

_COVER_FEATURE: Final = {
    SensorType.BLIND: "cover.CoverEntityFeature.SET_POSITION",
    SensorType.AWNING: "cover.CoverEntityFeature.SET_POSITION",
    SensorType.TILT: "cover.CoverEntityFeature.SET_TILT_POSITION",
}

# Wizard pages after the cover-type page, and the group each one collects.
WIZARD_PAGES: Final = {
    "interp": Group.INTERP,
    "blind_spot": Group.BLIND_SPOT,
    "automation": Group.AUTOMATION,
    "climate": Group.CLIMATE,
    "weather": Group.WEATHER,
}
# The cover-type page (vertical / horizontal / tilt) collects these groups.
WIZARD_TYPE_GROUPS: Final = (Group.CLIMATE_TOGGLE, Group.COVER, Group.SUN)

# Options form: section -> groups, in order. The climate section holds only
# the toggle while climate mode is off (so the feature stays discoverable).
OPTIONS_SECTIONS: Final = {
    "covers_geometry": (Group.COVER,),
    "sun_behavior": (Group.SUN, Group.BLIND_SPOT, Group.INTERP),
    "automation_timing": (Group.AUTOMATION,),
    "climate": (Group.CLIMATE_TOGGLE, Group.CLIMATE, Group.WEATHER),
}
_CLIMATE_OFF_GROUPS: Final = (Group.CLIMATE_TOGGLE,)

# Every option the wizard can collect (it persists all of them).
WIZARD_OPTION_KEYS: Final = frozenset(
    opt.key for opt in OPTS if opt.group is not Group.NONE
)
# Options-form keys where "absent from the submitted form" clears the option.
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
        return selector.EntitySelector(
            selector.EntitySelectorConfig(
                multiple=opt.multiple,
                filter=selector.EntityWithDeviceFilterSelectorConfig(
                    domain=list(opt.domains),
                    supported_features=[_COVER_FEATURE[cover_type or SensorType.BLIND]],
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


# --------------------------------------------------------------- wizard


def _wizard_fields(
    opts: Iterable[Opt],
    *,
    cover_type: str | None,
    temperature_unit: str | None,
    fov_span: float | None = None,
) -> dict[vol.Marker, Any]:
    fields: dict[vol.Marker, Any] = {}
    for opt in opts:
        marker_cls = vol.Required if opt.wizard_required else vol.Optional
        default = opt.shape("wizard", temperature_unit)["default"]
        marker = (
            marker_cls(opt.key)
            if default is NO_DEFAULT
            else marker_cls(opt.key, default=_default_factory(default))
        )
        fields[marker] = form_validator(
            opt,
            "wizard",
            cover_type=cover_type,
            temperature_unit=temperature_unit,
            fov_span=fov_span,
        )
    return fields


def wizard_type_schema(cover_type: str, temperature_unit: str | None) -> vol.Schema:
    """Build the wizard's cover-type page (vertical / horizontal / tilt)."""
    opts = [opt for group in WIZARD_TYPE_GROUPS for opt in opts_in(group, cover_type)]
    return vol.Schema(
        _wizard_fields(opts, cover_type=cover_type, temperature_unit=temperature_unit)
    )


def wizard_schema(
    page: str,
    *,
    temperature_unit: str | None = None,
    fov_span: float | None = None,
) -> vol.Schema:
    """Build a wizard page after the cover-type page (see ``WIZARD_PAGES``).

    ``fov_span`` (fov_left + fov_right) sizes the blind-spot sliders.
    """
    return vol.Schema(
        _wizard_fields(
            opts_in(WIZARD_PAGES[page]),
            cover_type=None,
            temperature_unit=temperature_unit,
            fov_span=fov_span,
        )
    )


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
