"""ShadeConfig and ControlState: the coordinator's typed options and toggles (P4)."""

from __future__ import annotations

import dataclasses

import pytest

from custom_components.adaptive_cover.const import (
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
from custom_components.adaptive_cover.runtime.shade_config import (
    ControlState,
    ControlToggle,
    ShadeConfig,
)


def test_defaults_when_options_are_empty():
    config = ShadeConfig.from_options({})
    assert config.entities == []
    assert config.min_change == 1
    assert config.time_threshold == 2
    assert config.manual_reset is False
    assert config.manual_duration == DEFAULT_MANUAL_OVERRIDE_DURATION
    unset = [
        "start_time",
        "start_time_entity",
        "end_time",
        "end_time_entity",
        "manual_threshold",
        "interp_start",
        "interp_end",
        "interp_list",
        "interp_list_new",
        "quiet_start",
        "quiet_end",
        "max_moves_hour",
        "sunset_pos",
        "default_height",
        "privacy_position",
    ]
    assert {name: getattr(config, name) for name in unset} == dict.fromkeys(unset)


@pytest.mark.parametrize(
    ("key", "field", "value"),
    [
        (CONF_ENTITIES, "entities", ["cover.a", "cover.b"]),
        (CONF_DELTA_POSITION, "min_change", 7),
        (CONF_DELTA_TIME, "time_threshold", 15),
        (CONF_START_TIME, "start_time", "07:30:00"),
        (CONF_START_ENTITY, "start_time_entity", "input_datetime.start"),
        (CONF_END_TIME, "end_time", "21:00:00"),
        (CONF_END_ENTITY, "end_time_entity", "sensor.end"),
        (CONF_MANUAL_OVERRIDE_RESET, "manual_reset", True),
        (CONF_MANUAL_OVERRIDE_DURATION, "manual_duration", {"minutes": 45}),
        (CONF_MANUAL_THRESHOLD, "manual_threshold", 5),
        (CONF_INTERP_START, "interp_start", 10),
        (CONF_INTERP_END, "interp_end", 90),
        (CONF_INTERP_LIST, "interp_list", ["0", "50", "100"]),
        (CONF_INTERP_LIST_NEW, "interp_list_new", ["0", "20", "100"]),
        (CONF_QUIET_START, "quiet_start", "22:00:00"),
        (CONF_QUIET_END, "quiet_end", "06:00:00"),
        (CONF_MAX_MOVES_HOUR, "max_moves_hour", 4),
        (CONF_SUNSET_POS, "sunset_pos", 0),
        (CONF_DEFAULT_HEIGHT, "default_height", 60),
        (CONF_PRIVACY_POSITION, "privacy_position", 35),
    ],
)
def test_each_option_lands_in_its_field(key, field, value):
    assert getattr(ShadeConfig.from_options({key: value}), field) == value


def test_values_are_not_cast():
    """A read never raises where the options.get it replaced did not."""
    config = ShadeConfig.from_options({CONF_DELTA_POSITION: "junk"})
    assert config.min_change == "junk"


def test_config_is_frozen():
    config = ShadeConfig.from_options({})
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.min_change = 5  # type: ignore[misc]


def test_toggles_start_unrestored():
    controls = ControlState()
    assert (
        controls.control,
        controls.manual,
        controls.outside_temp,
        controls.lux,
        controls.irradiance,
    ) == (None, None, None, None, None)
    assert controls.climate is False


@pytest.mark.parametrize(
    ("manual", "clears"),
    [
        (None, False),  # restart / reload: the switch has not restored yet
        (True, False),
        (False, True),  # explicit off
    ],
)
def test_only_an_explicit_off_clears_overrides(manual, clears):
    assert ControlState(manual=manual).clears_overrides is clears


class _Owner:
    manual_toggle = ControlToggle[bool | None]("manual")
    switch_mode = ControlToggle[bool]("climate")

    def __init__(self) -> None:
        self.controls = ControlState(climate=True)


def test_control_toggle_reads_and_writes_the_state():
    owner = _Owner()
    assert owner.manual_toggle is None
    assert owner.switch_mode is True
    setattr(owner, "manual_toggle", False)  # how the switch platform does it
    owner.switch_mode = False
    assert owner.controls == ControlState(manual=False, climate=False)
    assert owner.manual_toggle is False


def test_control_toggle_on_the_class_is_the_descriptor():
    assert isinstance(_Owner.manual_toggle, ControlToggle)
