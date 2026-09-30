"""Spec round trip: setup form <-> options <-> service <-> normalize (plan P3).

A value one settings surface accepts and stores must read back unchanged
through every other surface: the options form shows it and saves it
again as is, ``change_settings`` accepts it without changing it, and the
normalizers (the cover's two keys, migration 1.3) keep it.

Property style, seeded: each case draws a random valid value for every
option of a cover type from the spec's own shapes (the range every
surface accepts), then pushes it through the generated validators
(``settings/schema.py``). The flow-level cases at the bottom drive the
real setup form, options form and services for a few draws.
"""

from __future__ import annotations

import random
from typing import Any

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adaptive_cover.const import (
    CONF_BLIND_SPOT_ELEVATION,
    CONF_BLIND_SPOT_LEFT,
    CONF_BLIND_SPOT_RIGHT,
    CONF_CLIMATE_MODE,
    CONF_COVER_ENTITY,
    CONF_ENABLE_BLIND_SPOT,
    CONF_ENTITIES,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_INTERP,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.migration import options_1_3
from custom_components.adaptive_cover.runtime.shade_config import ShadeConfig
from custom_components.adaptive_cover.settings import schema
from custom_components.adaptive_cover.settings.normalize import (
    normalize_cover,
    window_cover,
    with_cover,
)
from custom_components.adaptive_cover.settings.shadow import without_overrides
from custom_components.adaptive_cover.settings.spec import (
    OPTS,
    Group,
    Kind,
    Opt,
)
from custom_components.adaptive_cover.settings.validate import cross_field_errors

from ..window_form import add_legacy_house, add_window

COVER_TYPES = (SensorType.BLIND, SensorType.AWNING, SensorType.TILT)
UNITS = ("°C", "°F")
SEEDS = range(40)

# Options that may exist only when their wizard page runs.
_BLIND_SPOT = {CONF_BLIND_SPOT_LEFT, CONF_BLIND_SPOT_RIGHT, CONF_BLIND_SPOT_ELEVATION}
_INTERP = {o.key for o in OPTS if o.group is Group.INTERP}
# A range for unbounded numbers (offsets, thresholds) to draw from.
_OPEN_RANGE = (-120.0, 1200.0)


def _form_opts(cover_type: str) -> list[Opt]:
    return [
        opt
        for opt in OPTS
        if opt.kind is not Kind.INTERNAL and cover_type in opt.cover_types
    ]


def _range(opt: Opt, unit: str) -> tuple[float, float, float]:
    """(min, max, step) that the wizard, the options form and the service take."""
    shapes = [opt.shape(surface, unit) for surface in ("wizard", "options")]
    if opt.service is not None and opt.shape("service", unit)["bounded"]:
        shapes.append(opt.shape("service", unit))
    lows = [s["min"] for s in shapes if s["min"] is not None]
    highs = [s["max"] for s in shapes if s["max"] is not None]
    low = max(lows) if lows else _OPEN_RANGE[0]
    high = min(highs) if highs else _OPEN_RANGE[1]
    step = opt.shape("wizard", unit)["step"] or 1
    return low, high, step


def _draw_number(rng: random.Random, low: float, high: float, step: float) -> float:
    steps = int((high - low) // step)
    return round(low + step * rng.randint(0, steps), 4)


def _draw(rng: random.Random, opt: Opt, unit: str) -> Any:
    """One value of ``opt`` that every surface accepts."""
    if opt.kind in (Kind.NUMBER, Kind.INT):
        low, high, step = _range(opt, unit)
        value = _draw_number(rng, low, high, step)
        return int(value) if opt.kind is Kind.INT else value
    if opt.kind in (Kind.BOOL, Kind.SWITCH):
        return rng.random() < 0.5
    if opt.kind is Kind.TIME:
        return f"{rng.randint(0, 23):02d}:{rng.choice((0, 15, 30, 45)):02d}:00"
    if opt.kind is Kind.DURATION:
        return {"hours": rng.randint(0, 4), "minutes": rng.randint(0, 59), "seconds": 0}
    if opt.kind is Kind.ENTITY:
        return f"{opt.domains[0]}.round_trip_{rng.randint(0, 999)}"
    if opt.kind is Kind.SELECT:
        if opt.multiple:
            return sorted(rng.sample(opt.options, rng.randint(0, len(opt.options))))
        return rng.choice(opt.options)
    raise AssertionError(f"no draw for {opt.key} ({opt.kind})")


def draw_options(seed: int, cover_type: str, unit: str) -> dict[str, Any]:
    """A random, cross-field valid option set for one cover type."""
    rng = random.Random(f"{seed}-{cover_type}-{unit}")
    values = {opt.key: _draw(rng, opt, unit) for opt in _form_opts(cover_type)}
    # Cross-field rules (settings/validate.py) and the FOV-sized blind spot.
    values[CONF_MIN_ELEVATION], values[CONF_MAX_ELEVATION] = sorted(
        rng.sample(range(0, 91), 2)
    )
    span = int(values[CONF_FOV_LEFT] + values[CONF_FOV_RIGHT])
    left, right = sorted(rng.sample(range(0, min(90, span - 1) + 1), 2))
    values[CONF_BLIND_SPOT_LEFT], values[CONF_BLIND_SPOT_RIGHT] = left, max(right, 1)
    values[CONF_INTERP_LIST_NEW] = values[CONF_INTERP_LIST][:]
    assert not cross_field_errors(values), cross_field_errors(values)
    return values


def _same(validated: dict[str, Any], values: dict[str, Any]) -> None:
    for key, value in values.items():
        assert validated[key] == value, (key, validated[key], value)


def _cases():
    return [(seed, t, u) for seed in SEEDS for t in COVER_TYPES for u in UNITS]


@pytest.mark.parametrize(("seed", "cover_type", "unit"), _cases())
def test_wizard_options_and_service_keep_every_value(seed, cover_type, unit):
    values = draw_options(seed, cover_type, unit)
    fov_span = values[CONF_FOV_LEFT] + values[CONF_FOV_RIGHT]

    # setup form: every section takes its values as they are
    wizard: dict[str, Any] = {}
    setup = schema.setup_section_fields(cover_type, values={}, temperature_unit=unit)
    for fields in setup.values():
        keys = {str(m) for m in fields}
        wizard.update(
            vol.Schema(fields)({k: v for k, v in values.items() if k in keys})
        )
    _same(wizard, values)
    # (the drawn blind spot fits the drawn FOV, inside the form's full span)
    assert fov_span <= schema.FULL_FOV_SPAN

    # options form: every section shows the stored value and saves it as is
    sections = schema.options_section_fields(
        cover_type, climate_on=True, options=wizard, temperature_unit=unit
    )
    saved: dict[str, Any] = {}
    for fields in sections.values():
        keys = {str(m) for m in fields}
        for marker in fields:
            assert marker.description == {"suggested_value": wizard.get(str(marker))}
        saved.update(vol.Schema(fields)({k: v for k, v in wizard.items() if k in keys}))
    _same(saved, values)

    # services: change_settings takes every service option unchanged
    service_keys = set(schema.changeable_options(unit))
    call = {k: v for k, v in saved.items() if k in service_keys}
    validated = schema.change_settings_schema(unit)({"config_entry": "x", **call})
    _same(validated, call)
    added = schema.add_entry_schema(unit)(
        {"name": "x", "cover": saved[CONF_COVER_ENTITY], **call}
    )
    _same(added, call)


@pytest.mark.parametrize(("seed", "cover_type", "unit"), _cases())
def test_normalizers_keep_what_the_surfaces_store(seed, cover_type, unit):
    stored = with_cover(draw_options(seed, cover_type, unit), f"cover.w{seed}")
    assert window_cover(stored) == f"cover.w{seed}"
    assert normalize_cover(stored) == stored
    migrated = options_1_3(stored)
    assert options_1_3(migrated) == migrated
    assert {k: migrated[k] for k in stored} == stored
    assert ShadeConfig.from_options(migrated) == ShadeConfig.from_options(stored)


def test_every_form_option_is_drawn():
    """A new spec row needs a draw (or the round trip skips it)."""
    for cover_type in COVER_TYPES:
        drawn = set(draw_options(0, cover_type, "°C"))
        assert drawn == {o.key for o in _form_opts(cover_type)}


# ------------------------------------------------ through the real flows

FLOW_SEEDS = range(4)


@pytest.fixture(autouse=False)
async def unload_all(hass):
    # The window-entry flows: a house that still has window entries (P7).
    add_legacy_house(hass)
    yield
    for entry in hass.config_entries.async_entries():
        if entry.state is config_entries.ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def _wizard(hass, cover_type: str, values: dict[str, Any]):
    """Add a window through the one-screen setup form."""
    result = await add_window(
        hass, {"name": "Round trip", schema.FIELD_SENSOR_TYPE: cover_type, **values}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    return result["result"]


@pytest.mark.usefixtures("stub_sun_integration", "unload_all")
@pytest.mark.parametrize("seed", FLOW_SEEDS)
@pytest.mark.parametrize("cover_type", COVER_TYPES)
async def test_real_flows_round_trip(hass, seed, cover_type):
    unit = hass.config.units.temperature_unit
    values = draw_options(seed, cover_type, unit)
    # every feature on (the form shows every field either way)
    values.update({CONF_INTERP: True, CONF_ENABLE_BLIND_SPOT: True})
    values[CONF_CLIMATE_MODE] = True
    values[CONF_WEATHER_ENTITY] = "weather.round_trip"
    entry = await _wizard(hass, cover_type, values)
    await hass.async_block_till_done()
    stored = dict(entry.options)
    _same(stored, values)
    assert stored[CONF_ENTITIES] == [values[CONF_COVER_ENTITY]]

    # the options form, saved without a change, stores the same options
    result = await hass.config_entries.options.async_init(entry.entry_id)
    sections = {
        str(marker): {
            str(field): field.description["suggested_value"]
            for field in section.schema.schema
            if field.description["suggested_value"] is not None
        }
        for marker, section in result["data_schema"].schema.items()
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=sections
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert dict(entry.options) == stored

    # change_settings with every service option that is set: accepted,
    # nothing moves. (A key the wizard stores as None because the cover
    # type does not use it, e.g. a tilt blind's window_height, is left
    # out: most service fields do not take None.)
    service_keys = set(schema.changeable_options(unit))
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id}
        | {k: v for k, v in stored.items() if k in service_keys and v is not None},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert dict(entry.options) == stored

    # add_entry copying it onto another cover: the same settings
    response = await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {"name": "Copy", "cover": "cover.round_trip_copy", "copy_from": entry.entry_id},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    copy = hass.config_entries.async_get_entry(response["entry_id"])
    # The copy has overrides of its own (P5 flip: it joins the layered
    # settings at its setup); everything else is the source's.
    assert without_overrides(copy.options) == with_cover(
        without_overrides(stored), "cover.round_trip_copy"
    )
    assert copy.options["overrides"]["window_key"] == copy.entry_id
    assert {
        key: value
        for key, value in copy.options["overrides"].items()
        if key != "window_key"
    } == {
        key: value for key, value in stored["overrides"].items() if key != "window_key"
    }
