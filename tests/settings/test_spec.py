"""The option spec (settings/spec.py) and what it generates.

- Every row follows the plan's one-time vs recurring table.
- spec.py stays pure data (no Home Assistant imports).
- The remaining per-surface drift is exactly the listed ``legacy`` entries,
  so new drift has to be added on purpose.
- A value one surface accepts, the services accept too (form -> service
  round trip), and every default passes its own validators.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import voluptuous as vol

from custom_components.adaptive_cover.const import SensorType
from custom_components.adaptive_cover.number import TUNABLES
from custom_components.adaptive_cover.settings import schema, spec
from custom_components.adaptive_cover.settings.spec import (
    NO_DEFAULT,
    OPTS,
    OPTS_BY_KEY,
    Kind,
    Level,
    Scope,
)

SETTINGS_DIR = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "adaptive_cover"
    / "settings"
)
UNITS = ("°C", "°F")

H, F, A, W = Level.HOUSE, Level.FLOOR, Level.AREA, Level.WINDOW

# docs/refactor_plan.md, "One-time vs recurring settings", written out per
# key: (scope, home, narrower override levels). Independent of the spec.
PLAN_TABLE: dict[str, tuple[Scope, Level | None, set[Level]]] = {
    # one-time, window setup
    "group": (Scope.ONE_TIME, W, set()),
    "set_azimuth": (Scope.ONE_TIME, W, set()),
    "fov_left": (Scope.ONE_TIME, W, set()),
    "fov_right": (Scope.ONE_TIME, W, set()),
    "window_height": (Scope.ONE_TIME, W, set()),
    "distance_shaded_area": (Scope.ONE_TIME, W, set()),
    "length_awning": (Scope.ONE_TIME, W, set()),
    "angle": (Scope.ONE_TIME, W, set()),
    "slat_depth": (Scope.ONE_TIME, W, set()),
    "slat_distance": (Scope.ONE_TIME, W, set()),
    "tilt_mode": (Scope.ONE_TIME, W, set()),
    "overhang_depth": (Scope.ONE_TIME, W, set()),
    "overhang_height": (Scope.ONE_TIME, W, set()),
    "min_elevation": (Scope.ONE_TIME, W, set()),
    "max_elevation": (Scope.ONE_TIME, W, set()),
    "blind_spot": (Scope.ONE_TIME, W, set()),
    "blind_spot_left": (Scope.ONE_TIME, W, set()),
    "blind_spot_right": (Scope.ONE_TIME, W, set()),
    "blind_spot_elevation": (Scope.ONE_TIME, W, set()),
    "min_position": (Scope.ONE_TIME, W, set()),
    "max_position": (Scope.ONE_TIME, W, set()),
    "enable_min_position": (Scope.ONE_TIME, W, set()),
    "enable_max_position": (Scope.ONE_TIME, W, set()),
    "inverse_state": (Scope.ONE_TIME, W, set()),
    "interp": (Scope.ONE_TIME, W, set()),
    "interp_start": (Scope.ONE_TIME, W, set()),
    "interp_end": (Scope.ONE_TIME, W, set()),
    "interp_list": (Scope.ONE_TIME, W, set()),
    "interp_list_new": (Scope.ONE_TIME, W, set()),
    "transparent_blind": (Scope.ONE_TIME, W, set()),
    "privacy_mode": (Scope.ONE_TIME, W, set()),
    # recurring
    "climate_mode": (Scope.RECURRING, H, {A}),
    "temp_low": (Scope.RECURRING, H, {F, A}),
    "temp_high": (Scope.RECURRING, H, {F, A}),
    "temp_entity": (Scope.RECURRING, F, {A}),
    "weather_entity": (Scope.RECURRING, H, set()),
    "weather_state": (Scope.RECURRING, H, set()),
    "presence_entity": (Scope.RECURRING, H, set()),
    "outside_temp": (Scope.RECURRING, H, set()),
    "outside_threshold": (Scope.RECURRING, H, set()),
    "lux_entity": (Scope.RECURRING, H, set()),
    "lux_threshold": (Scope.RECURRING, H, set()),
    "irradiance_entity": (Scope.RECURRING, H, set()),
    "irradiance_threshold": (Scope.RECURRING, H, set()),
    "manual_override_duration": (Scope.RECURRING, H, {A}),
    "manual_override_reset": (Scope.RECURRING, H, {A}),
    "manual_ignore_intermediate": (Scope.RECURRING, H, {A}),
    "manual_threshold": (Scope.RECURRING, H, {A}),
    "eye_height": (Scope.RECURRING, H, {A, W}),
    "occupied_distance": (Scope.RECURRING, H, {A, W}),
    "start_time": (Scope.RECURRING, H, {A}),
    "start_entity": (Scope.RECURRING, H, {A}),
    "sunrise_offset": (Scope.RECURRING, H, {A}),
    "end_time": (Scope.RECURRING, H, {A}),
    "end_entity": (Scope.RECURRING, H, {A}),
    "sunset_offset": (Scope.RECURRING, H, {A}),
    "return_sunset": (Scope.RECURRING, H, {A}),
    "default_percentage": (Scope.RECURRING, H, {A, W}),
    "sunset_position": (Scope.RECURRING, H, {A, W}),
    "privacy_offset": (Scope.RECURRING, H, {A}),
    "privacy_position": (Scope.RECURRING, H, {A}),
    "quiet_start": (Scope.RECURRING, H, set()),
    "quiet_end": (Scope.RECURRING, H, set()),
    "max_moves_hour": (Scope.RECURRING, H, set()),
    "delta_position": (Scope.RECURRING, H, set()),
    "delta_time": (Scope.RECURRING, H, set()),
    # internal: the control strategy ("basic"), never shown
    "mode": (Scope.INTERNAL, None, set()),
}

# Drift the spec still carries (see spec.py "legacy"). Removing an entry is
# a ledgered drift fix; adding one needs a reason in the same change.
EXPECTED_LEGACY: dict[str, dict] = {
    "delta_time": {"form.min": 2},
    "length_awning": {"service.bounded": False},
    "angle": {"service.bounded": False},
    "overhang_depth": {"service.bounded": False, "number.min": 0, "number.step": 0.05},
    "overhang_height": {
        "service.bounded": False,
        "number.min": 0.5,
        "number.step": 0.05,
    },
    "eye_height": {"service.bounded": False, "number.min": 0.5, "number.step": 0.05},
    "occupied_distance": {"service.bounded": False},
    "slat_depth": {"service.bounded": False},
    "slat_distance": {"service.bounded": False},
    "min_elevation": {"service.bounded": False},
    "max_elevation": {"service.bounded": False},
    "outside_threshold": {"service.bounded": False},
    "max_position": {"service.min": 0},
    "min_position": {"service.max": 100},
    "privacy_offset": {"number.unit": "min"},
    "blind_spot_left": {
        "options.max": 90,
        "options.unit": None,
        "options.slider": False,
    },
    "blind_spot_right": {
        "options.max": 90,
        "options.unit": None,
        "options.slider": False,
    },
    "temp_low": {
        "form.min": 0,
        "form.max": 86,
        "form.step": 1,
        "form.unit": "°",
        "form.slider": True,
        "service.bounded": False,
        "number.default@°C": 21,
    },
    "temp_high": {
        "form.min": 0,
        "form.max": 90,
        "form.step": 1,
        "form.unit": "°",
        "form.slider": True,
        "service.bounded": False,
        "number.default@°C": 25,
    },
}


def test_every_option_follows_the_plan_table():
    table = {opt.key: (opt.scope, opt.home, set(opt.overridable_at)) for opt in OPTS}
    assert table == PLAN_TABLE


def test_one_time_settings_live_on_the_window_without_overrides():
    for opt in OPTS:
        if opt.scope is Scope.ONE_TIME:
            assert (opt.home, opt.overridable_at) == (W, ()), opt.key


def test_recurring_settings_live_at_house_or_floor():
    """Every recurring key is reachable from a house, floor or room sheet."""
    for opt in OPTS:
        if opt.scope is Scope.RECURRING:
            assert opt.home in (H, F), opt.key
            assert W not in opt.overridable_at or opt.home is H, opt.key


def test_keys_are_unique():
    assert len(OPTS_BY_KEY) == len(OPTS)


def test_spec_is_pure_data():
    source = (SETTINGS_DIR / "spec.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+homeassistant", source, re.M)


def test_legacy_drift_is_exactly_the_listed_entries():
    legacy = {opt.key: dict(opt.legacy) for opt in OPTS if opt.legacy}
    assert legacy == EXPECTED_LEGACY


def test_clearable_keys_match_the_pre_spec_options_form():
    """The options form's "absent means cleared" set did not move."""
    clearable = set(schema.CLEARABLE_KEYS)
    assert clearable == {
        "min_elevation",
        "max_elevation",
        "overhang_depth",
        "overhang_height",
        "eye_height",
        "occupied_distance",
        "start_entity",
        "end_entity",
        "manual_threshold",
        "quiet_start",
        "quiet_end",
        "max_moves_hour",
        "blind_spot_left",
        "blind_spot_right",
        "blind_spot_elevation",
        "outside_temp",
        "weather_entity",
        "presence_entity",
        "lux_entity",
        "irradiance_entity",
        "interp_start",
        "interp_end",
    }


def test_number_entities_are_the_spec_rows_with_a_live_number():
    assert {t.key for t in TUNABLES} == {o.key for o in OPTS if o.number is not None}


def _boundary_values(opt: spec.Opt, surface: str, unit: str) -> list:
    shape = opt.shape(surface, unit)
    values = [shape[name] for name in ("min", "max") if shape[name] is not None]
    if shape["default"] is not NO_DEFAULT:
        values.append(shape["default"])
    return values


@pytest.mark.parametrize("unit", UNITS)
@pytest.mark.parametrize(
    "opt",
    [o for o in OPTS if o.service is not None and o.kind in (Kind.NUMBER, Kind.INT)],
    ids=lambda o: o.key,
)
def test_services_accept_what_the_forms_and_numbers_accept(opt, unit):
    """Round trip: a value a form or number accepts, the services accept.

    A value set in the wizard, the options form or a number entity can
    always be sent back through change_settings (for example by a script
    copying one window's settings to another).
    """
    service = schema.service_validator(opt, unit)
    surfaces = ["wizard", "options"] + (["number"] if opt.number else [])
    for surface in surfaces:
        for value in _boundary_values(opt, surface, unit):
            service(value)


@pytest.mark.parametrize("unit", UNITS)
@pytest.mark.parametrize(
    "opt",
    [o for o in OPTS if o.has_default and o.kind is not Kind.INTERNAL],
    ids=lambda o: o.key,
)
def test_defaults_pass_their_own_validators(opt, unit):
    default = opt.shape("wizard", unit)["default"]
    for cover_type in sorted(opt.cover_types):
        vol.Schema(
            schema.form_validator(
                opt,
                "wizard",
                cover_type=cover_type,
                temperature_unit=unit,
                fov_span=180,
            )
        )(default)
    if opt.service is not None:
        schema.service_validator(opt, unit)(default)


def test_add_entry_baseline_is_a_fresh_copy():
    first = schema.add_entry_baseline()
    first["interp_list"].append("50")
    first["manual_override_duration"]["hours"] = 9
    second = schema.add_entry_baseline()
    assert second["interp_list"] == []
    assert second["manual_override_duration"]["hours"] == 2


def test_wizard_covers_every_cover_type():
    for cover_type in (SensorType.BLIND, SensorType.AWNING, SensorType.TILT):
        keys = {str(m) for m in schema.wizard_type_schema(cover_type, "°C").schema}
        expected = {
            o.key
            for o in OPTS
            if o.group in schema.WIZARD_TYPE_GROUPS and cover_type in o.cover_types
        }
        assert keys == expected
