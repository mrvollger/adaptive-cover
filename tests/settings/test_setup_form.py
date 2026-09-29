"""The setup form's layout, presets and "Copy from" (settings/schema.py, P6).

Pure: the section each spec row lands in, what a preset may fill, and what
"Copy from" takes. The flows that use them are tested through the config
flow in tests/test_window_setup_form.py.
"""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_SENSOR_TYPE,
    SensorType,
)
from custom_components.adaptive_cover.settings import schema
from custom_components.adaptive_cover.settings.spec import (
    OPTS,
    OPTS_BY_KEY,
    Group,
    Level,
    Scope,
)

COVER_TYPES = (SensorType.BLIND, SensorType.AWNING, SensorType.TILT)
FORM_OPTS = [opt for opt in OPTS if opt.group is not Group.NONE]


@pytest.mark.parametrize("opt", FORM_OPTS, ids=lambda o: o.key)
def test_recurring_settings_sit_only_in_exception_sections(opt):
    """Plan: the window form shows recurring keys only as exceptions."""
    section = schema.setup_section(opt)
    if opt.scope is Scope.RECURRING:
        assert section in schema.EXCEPTION_SECTIONS
    else:
        assert section in schema.ONE_TIME_SECTIONS


def test_window_section_is_identity_facing_and_geometry():
    """The expanded section holds what makes this window, nothing optional."""
    for cover_type in COVER_TYPES:
        keys = [opt.key for opt in schema.setup_opts(schema.WINDOW_SECTION, cover_type)]
        assert keys[:4] == [CONF_COVER_ENTITY, CONF_AZIMUTH, "fov_left", "fov_right"]
        for key in keys:
            opt = OPTS_BY_KEY[key]
            assert opt.scope is Scope.ONE_TIME and opt.home is Level.WINDOW


def test_reconfigure_form_has_no_recurring_setting():
    for cover_type in COVER_TYPES:
        sections = schema.setup_section_fields(
            cover_type, values={}, temperature_unit="°C", recurring=False
        )
        assert tuple(sections) == schema.ONE_TIME_SECTIONS
        for fields in sections.values():
            for marker in fields:
                opt = OPTS_BY_KEY.get(str(marker))
                assert opt is None or opt.scope is Scope.ONE_TIME, marker


def test_only_the_cover_must_be_entered():
    """Every other field is optional or has a default: cover + azimuth suffice."""
    sections = schema.setup_section_fields(
        SensorType.BLIND, values={}, temperature_unit="°F"
    )
    for fields in sections.values():
        for marker in fields:
            if isinstance(marker, vol.Required) and str(marker) != CONF_COVER_ENTITY:
                assert marker.default is not vol.UNDEFINED, marker


# ------------------------------------------------------------------ presets


@pytest.mark.parametrize("preset", list(schema.PRESETS))
def test_presets_fill_one_time_geometry_only(preset):
    values = schema.preset_values(preset)
    assert tuple(values) == schema.PRESET_KEYS
    for key in values:
        opt = OPTS_BY_KEY[key]
        assert opt.scope is Scope.ONE_TIME, key
        assert key not in schema.IDENTITY_KEYS
        assert schema.setup_section(opt) in ("window", "sun_limits"), key


@pytest.mark.parametrize("preset", list(schema.PRESETS))
@pytest.mark.parametrize("cover_type", [SensorType.BLIND, SensorType.AWNING])
def test_preset_values_pass_the_form(preset, cover_type):
    values = {k: v for k, v in schema.preset_values(preset).items() if v is not None}
    sections = schema.setup_section_fields(
        cover_type, values=values, temperature_unit="°C"
    )
    entered = {CONF_COVER_ENTITY: "cover.x", **values}
    taken: dict = {}
    for fields in sections.values():
        keys = {str(m) for m in fields}
        taken |= vol.Schema(fields)({k: v for k, v in entered.items() if k in keys})
    assert {k: taken[k] for k in values} == values


def test_preset_values_are_a_fresh_copy():
    values = schema.preset_values("window")
    values[CONF_HEIGHT_WIN] = 9
    assert schema.PRESETS["window"][CONF_HEIGHT_WIN] == 2.0


# ---------------------------------------------------------------- copy from


def test_copy_from_takes_everything_but_identity():
    options = {opt.key: f"v-{opt.key}" for opt in FORM_OPTS}
    options[CONF_ENTITIES] = ["cover.source"]
    copied = schema.copy_from_values({CONF_SENSOR_TYPE: SensorType.TILT}, options)
    assert CONF_COVER_ENTITY not in copied
    assert CONF_ENTITIES not in copied
    assert "name" not in copied
    assert copied[CONF_SENSOR_TYPE] == SensorType.TILT
    for opt in FORM_OPTS:
        if opt.key != CONF_COVER_ENTITY:
            assert copied[opt.key] == f"v-{opt.key}"


def test_copy_from_sets_every_key_so_nothing_is_left_behind():
    copied = schema.copy_from_values({}, {CONF_AZIMUTH: 100})
    assert copied[CONF_AZIMUTH] == 100
    assert copied[CONF_HEIGHT_WIN] is None
    assert copied[CONF_SENSOR_TYPE] == SensorType.BLIND


def test_copy_from_copies_lists_and_dicts():
    source = {"weather_state": ["sunny"], "manual_override_duration": {"hours": 2}}
    copied = schema.copy_from_values({}, source)
    copied["weather_state"].append("cloudy")
    copied["manual_override_duration"]["hours"] = 9
    assert source == {
        "weather_state": ["sunny"],
        "manual_override_duration": {"hours": 2},
    }
