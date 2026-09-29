"""The cover adapters are built from ShadeConfig, not positional values (P3).

``calculation.build_cover`` turns a window's options (through
``ShadeConfig.geometry``) into the adapter the coordinator drives; the
overhang and glare options apply to vertical blinds only, privacy to
every type. The fields are keyword-only, so the order-coupled positional
construction the coordinator used cannot come back.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from custom_components.adaptive_cover.calculation import (
    AdaptiveVerticalCover,
    ClimateCoverData,
    build_cover,
)
from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
)
from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_DEFAULT_HEIGHT,
    CONF_DISTANCE,
    CONF_EYE_HEIGHT,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_LENGTH_AWNING,
    CONF_LUX_THRESHOLD,
    CONF_OCCUPIED_DISTANCE,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_PRIVACY_MODE,
    CONF_PRIVACY_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_TEMP_LOW,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    SensorType,
)
from custom_components.adaptive_cover.engine.models import (
    GlareModel,
    Overhang,
    PrivacyConfig,
)
from custom_components.adaptive_cover.runtime.shade_config import (
    ControlState,
    ShadeConfig,
)

OPTIONS = {
    CONF_AZIMUTH: 190,
    CONF_FOV_LEFT: 50,
    CONF_FOV_RIGHT: 45,
    CONF_DEFAULT_HEIGHT: 97,
    CONF_SUNSET_POS: 3,
    CONF_SUNSET_OFFSET: 20,
    CONF_HEIGHT_WIN: 2.1,
    CONF_DISTANCE: 0.4,
    CONF_LENGTH_AWNING: 2.5,
    CONF_AWNING_ANGLE: 10,
    CONF_TILT_DEPTH: 3,
    CONF_TILT_DISTANCE: 2,
    CONF_TILT_MODE: "mode1",
    CONF_OVERHANG_DEPTH: 1.2,
    CONF_OVERHANG_HEIGHT: 2.6,
    CONF_EYE_HEIGHT: 1.2,
    CONF_OCCUPIED_DISTANCE: 2.0,
    CONF_PRIVACY_MODE: True,
    CONF_PRIVACY_OFFSET: 0,
}


def _logger() -> ConfigContextAdapter:
    logger = ConfigContextAdapter(logging.getLogger(__name__))
    logger.set_config_name("adapters")
    return logger


def _build(cover_type: str, options: dict | None = None):
    config = ShadeConfig.from_options(OPTIONS if options is None else options)
    return build_cover(
        cover_type,
        SimpleNamespace(),
        _logger(),
        config.geometry,
        sun=(185.0, 30.0),
        timezone="America/Denver",
    )


def test_vertical_blind_gets_every_option():
    config = _build(SensorType.BLIND).engine_config()
    assert config.cover_type == "vertical"
    assert (config.window_azimuth, config.fov_left, config.fov_right) == (190, 50, 45)
    assert (config.default_position, config.sunset_position) == (97, 3)
    # the sunrise offset falls back to the sunset offset
    assert (config.sunset_offset_min, config.sunrise_offset_min) == (20, 20)
    assert (config.distance_shaded_area, config.window_height) == (0.4, 2.1)
    assert config.overhang == Overhang(depth=1.2, height_above_sill=2.6)
    assert config.glare == GlareModel(eye_height=1.2, occupied_distance=2.0)
    # an offset of 0 closes right at sunset (not the 30-minute fallback)
    assert config.privacy == PrivacyConfig(enabled=True, offset_min=0, position=0)


def test_awning_and_tilt_ignore_overhang_and_glare():
    awning = _build(SensorType.AWNING).engine_config()
    assert awning.cover_type == "awning"
    assert (awning.awning_length, awning.awning_angle) == (2.5, 10)
    assert awning.overhang is None
    assert awning.glare is None
    assert awning.privacy is not None

    tilt = _build(SensorType.TILT).engine_config()
    assert tilt.cover_type == "tilt"
    assert (tilt.slat_depth, tilt.slat_distance, tilt.tilt_mode) == (3, 2, "mode1")
    assert tilt.overhang is None
    assert tilt.glare is None
    assert tilt.privacy is not None


def test_no_privacy_without_privacy_mode():
    options = {**OPTIONS, CONF_PRIVACY_MODE: False}
    assert _build(SensorType.BLIND, options).privacy is None


def test_unknown_cover_type_is_refused():
    with pytest.raises(ValueError, match="cover_door"):
        _build("cover_door")


def test_adapters_take_no_positional_values():
    with pytest.raises(TypeError):
        AdaptiveVerticalCover(SimpleNamespace(), _logger())  # type: ignore[misc]


def test_climate_adapter_reads_options_and_toggles():
    config = ShadeConfig.from_options({CONF_TEMP_LOW: 21, CONF_LUX_THRESHOLD: 900})
    controls = ControlState(outside_temp=True, lux=False, irradiance=None)
    climate = ClimateCoverData.from_config(
        SimpleNamespace(), _logger(), config.climate, controls, SensorType.BLIND
    )
    assert (climate.temp_low, climate.lux_threshold) == (21, 900)
    assert climate.temp_switch is True
    assert climate.lux is False  # the Lux switch is off
    assert climate.blind_type == SensorType.BLIND
