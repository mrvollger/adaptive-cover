"""Changeable options for the adaptive_cover.change_settings service.

Single source of truth mapping option keys to validators. Anything listed
here can be changed at runtime via the service; changes persist into the
config entry's options (unlike adaptive-lighting's ephemeral equivalent)
and take effect on the automatic entry reload.

Deliberately excluded: name and sensor_type (entry data, not options),
interpolation lists (shape-coupled), and entity group membership (use the
options flow so the event listeners re-wire).
"""

from __future__ import annotations

import voluptuous as vol

from .const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_END_TIME,
    CONF_EYE_HEIGHT,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_IRRADIANCE_THRESHOLD,
    CONF_LENGTH_AWNING,
    CONF_LUX_THRESHOLD,
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
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_PRIVACY_MODE,
    CONF_PRIVACY_OFFSET,
    CONF_PRIVACY_POSITION,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_START_TIME,
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
)

_NULLABLE_NUMBER = vol.Any(None, vol.Coerce(float))
_PERCENT = vol.All(vol.Coerce(float), vol.Range(min=0, max=100))
_NULLABLE_PERCENT = vol.Any(None, _PERCENT)

CHANGEABLE_OPTIONS: dict[str, object] = {
    # window geometry
    CONF_AZIMUTH: vol.All(vol.Coerce(float), vol.Range(min=0, max=359)),
    CONF_HEIGHT_WIN: vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10)),
    CONF_DISTANCE: vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10)),
    CONF_FOV_LEFT: vol.All(vol.Coerce(float), vol.Range(min=1, max=90)),
    CONF_FOV_RIGHT: vol.All(vol.Coerce(float), vol.Range(min=1, max=90)),
    CONF_MIN_ELEVATION: _NULLABLE_NUMBER,
    CONF_MAX_ELEVATION: _NULLABLE_NUMBER,
    # overhang + glare
    CONF_OVERHANG_DEPTH: _NULLABLE_NUMBER,
    CONF_OVERHANG_HEIGHT: _NULLABLE_NUMBER,
    CONF_EYE_HEIGHT: _NULLABLE_NUMBER,
    CONF_OCCUPIED_DISTANCE: _NULLABLE_NUMBER,
    # awning / tilt geometry
    CONF_LENGTH_AWNING: _NULLABLE_NUMBER,
    CONF_AWNING_ANGLE: _NULLABLE_NUMBER,
    CONF_TILT_DEPTH: _NULLABLE_NUMBER,
    CONF_TILT_DISTANCE: _NULLABLE_NUMBER,
    CONF_TILT_MODE: vol.Any(None, vol.In(["mode1", "mode2"])),
    # positions & offsets
    CONF_DEFAULT_HEIGHT: _PERCENT,
    CONF_SUNSET_POS: _PERCENT,
    CONF_SUNSET_OFFSET: vol.Coerce(float),
    CONF_SUNRISE_OFFSET: vol.Coerce(float),
    CONF_MIN_POSITION: _NULLABLE_PERCENT,
    CONF_MAX_POSITION: _NULLABLE_PERCENT,
    # privacy
    CONF_PRIVACY_MODE: vol.Boolean(),
    CONF_PRIVACY_OFFSET: vol.All(vol.Coerce(float), vol.Range(min=0, max=180)),
    CONF_PRIVACY_POSITION: _PERCENT,
    # smoothing & timing
    CONF_QUIET_START: vol.Any(None, str),
    CONF_QUIET_END: vol.Any(None, str),
    CONF_MAX_MOVES_HOUR: vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=1, max=60))),
    CONF_DELTA_POSITION: vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
    CONF_DELTA_TIME: vol.All(vol.Coerce(int), vol.Range(min=0)),
    CONF_START_TIME: vol.Any(None, str),
    CONF_END_TIME: vol.Any(None, str),
    # manual override
    CONF_MANUAL_OVERRIDE_DURATION: vol.Any(None, dict),
    CONF_MANUAL_OVERRIDE_RESET: vol.Boolean(),
    CONF_MANUAL_THRESHOLD: vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=0, max=99))),
    # climate thresholds
    CONF_TEMP_LOW: _NULLABLE_NUMBER,
    CONF_TEMP_HIGH: _NULLABLE_NUMBER,
    CONF_OUTSIDE_THRESHOLD: _NULLABLE_NUMBER,
    CONF_LUX_THRESHOLD: _NULLABLE_NUMBER,
    CONF_IRRADIANCE_THRESHOLD: _NULLABLE_NUMBER,
}


# Baseline for entries created via the add_entry service without a
# copy_from template. Mirrors the wizard's defaults.
DEFAULT_OPTIONS: dict = {
    "mode": "basic",
    CONF_AZIMUTH: 180,
    CONF_HEIGHT_WIN: 2.1,
    CONF_DISTANCE: 0.5,
    CONF_DEFAULT_HEIGHT: 100,
    CONF_FOV_LEFT: 90,
    CONF_FOV_RIGHT: 90,
    CONF_SUNSET_POS: 0,
    CONF_SUNSET_OFFSET: 0,
    CONF_SUNRISE_OFFSET: 0,
    CONF_DELTA_POSITION: 1,
    CONF_DELTA_TIME: 2,
    CONF_START_TIME: "00:00:00",
    CONF_END_TIME: "00:00:00",
    CONF_MANUAL_OVERRIDE_DURATION: {"minutes": 15},
    CONF_MANUAL_OVERRIDE_RESET: False,
    "climate_mode": False,
    "inverse_state": False,
    "blind_spot": False,
    "interp": False,
    "enable_max_position": False,
    "enable_min_position": False,
    "interp_list": [],
    "interp_list_new": [],
}


def add_entry_schema() -> vol.Schema:
    """Build the add_entry service schema: identity + any changeable option."""
    schema: dict = {
        vol.Required("name"): str,
        vol.Required("covers"): [str],
        vol.Optional("copy_from"): str,
        vol.Optional("sensor_type"): vol.In(
            ["cover_blind", "cover_awning", "cover_tilt"]
        ),
    }
    for key, validator in CHANGEABLE_OPTIONS.items():
        schema[vol.Optional(key)] = validator
    return vol.Schema(schema)


def change_settings_schema() -> vol.Schema:
    """Build the service schema: config_entry + any changeable option."""
    schema: dict = {vol.Required("config_entry"): str}
    for key, validator in CHANGEABLE_OPTIONS.items():
        schema[vol.Optional(key)] = validator
    return vol.Schema(schema)
