"""HA-adapter regression tests for verified live-house bugs.

Pure-engine counterparts live in tests/engine/test_regression_fixes.py;
these cover the adapter layer: solar_times sensors, climate entity reads,
and the SunData snapshot cache.
"""

import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from custom_components.adaptive_cover import sun as sun_module
from custom_components.adaptive_cover.calculation import (
    AdaptiveVerticalCover,
    ClimateCoverData,
)
from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
)
from custom_components.adaptive_cover.sun import SunData


def _make_logger():
    logger = ConfigContextAdapter(logging.getLogger("regression"))
    logger.set_config_name("Regression")
    return logger


class FakeStates:
    """Minimal hass.states stand-in supporting get()."""

    def __init__(self):
        self._states = {}

    def set(self, entity_id, state, attributes=None):
        self._states[entity_id] = SimpleNamespace(
            state=state, attributes=attributes or {}
        )

    def get(self, entity_id):
        return self._states.get(entity_id)


def _make_vertical_cover(mock_sun_data, min_elevation=None, max_elevation=None):
    return AdaptiveVerticalCover(
        hass=MagicMock(),
        logger=_make_logger(),
        sol_azi=180.0,
        sol_elev=45.0,
        sunset_pos=0,
        sunset_off=0,
        sunrise_off=0,
        timezone="UTC",
        fov_left=90,
        fov_right=90,
        win_azi=180,
        h_def=60,
        max_pos=None,
        min_pos=None,
        max_pos_bool=False,
        min_pos_bool=False,
        blind_spot_left=None,
        blind_spot_right=None,
        blind_spot_elevation=None,
        blind_spot_on=False,
        min_elevation=min_elevation,
        max_elevation=max_elevation,
        distance=0.5,
        h_win=2.1,
    )


# --- bug 4: solar_times ignored the min/max elevation band ---


def _banded_sun(mock_sun_data):
    """Elevation profile: night / above-cap / in-band / above-cap / night."""
    times = pd.date_range(start="2026-06-21", periods=289, freq="5min", tz="UTC")
    elevations = (
        [-10.0] * 50 + [60.0] * 50 + [30.0] * 100 + [60.0] * 50 + [-10.0] * 39
    )
    mock_sun_data.times = times
    mock_sun_data.solar_azimuth = [180.0] * len(times)
    mock_sun_data.solar_elevation = elevations
    return times


def test_regression_solar_times_honor_max_elevation(mock_sun_data):
    """Start/end sun-time sensors must use the same elevation band the
    engine's sun_in_fov enforces, not a bare elevation > 0."""
    times = _banded_sun(mock_sun_data)
    cover = _make_vertical_cover(mock_sun_data, max_elevation=50)
    start, end = cover.solar_times()
    # Historically: start=times[50], end=times[249] (any elevation > 0).
    assert start == times[100].to_pydatetime()
    assert end == times[199].to_pydatetime()


def test_regression_solar_times_honor_min_elevation(mock_sun_data):
    times = _banded_sun(mock_sun_data)
    cover = _make_vertical_cover(mock_sun_data, min_elevation=40)
    start, end = cover.solar_times()
    assert start == times[50].to_pydatetime()
    assert end == times[249].to_pydatetime()


def test_regression_solar_times_no_band_unchanged(mock_sun_data):
    times = _banded_sun(mock_sun_data)
    cover = _make_vertical_cover(mock_sun_data)
    start, end = cover.solar_times()
    assert start == times[50].to_pydatetime()
    assert end == times[249].to_pydatetime()


def test_regression_solar_times_band_never_met(mock_sun_data):
    _banded_sun(mock_sun_data)
    cover = _make_vertical_cover(mock_sun_data, min_elevation=70)
    assert cover.solar_times() == (None, None)


# --- bug 5: unavailable/non-numeric climate sensors killed updates ---


def _make_climate(hass, **overrides):
    kwargs = dict(
        hass=hass,
        logger=_make_logger(),
        temp_entity="sensor.indoor_temp",
        temp_low=21.0,
        temp_high=23.0,
        presence_entity=None,
        weather_entity=None,
        weather_condition=None,
        outside_entity=None,
        temp_switch=False,
        blind_type="cover_blind",
        transparent_blind=False,
        lux_entity=None,
        irradiance_entity=None,
        lux_threshold=None,
        irradiance_threshold=None,
        temp_summer_outside=0,
        _use_lux=False,
        _use_irradiance=False,
    )
    kwargs.update(overrides)
    return ClimateCoverData(**kwargs)


def test_regression_climate_lux_unavailable_no_typeerror():
    """float(None) on an unavailable lux sensor raised TypeError and killed
    every coordinator update. Unavailable now reads as 'not dim'."""
    hass = MagicMock()
    hass.states = FakeStates()
    hass.states.set("sensor.indoor_temp", "22.0")
    hass.states.set("sensor.lux", "unavailable")
    climate = _make_climate(
        hass, lux_entity="sensor.lux", lux_threshold=500, _use_lux=True
    )
    assert climate.lux is False
    assert climate.to_inputs().lux_dim is False


def test_regression_climate_irradiance_unavailable_no_typeerror():
    hass = MagicMock()
    hass.states = FakeStates()
    hass.states.set("sensor.indoor_temp", "22.0")
    hass.states.set("sensor.irradiance", "unknown")
    climate = _make_climate(
        hass,
        irradiance_entity="sensor.irradiance",
        irradiance_threshold=300,
        _use_irradiance=True,
    )
    assert climate.irradiance is False
    assert climate.to_inputs().irradiance_dim is False


def test_regression_climate_lux_non_numeric_no_valueerror():
    hass = MagicMock()
    hass.states = FakeStates()
    hass.states.set("sensor.indoor_temp", "22.0")
    hass.states.set("sensor.lux", "n/a")
    climate = _make_climate(
        hass, lux_entity="sensor.lux", lux_threshold=500, _use_lux=True
    )
    assert climate.lux is False


def test_regression_climate_lux_numeric_still_compares():
    hass = MagicMock()
    hass.states = FakeStates()
    hass.states.set("sensor.indoor_temp", "22.0")
    hass.states.set("sensor.lux", "120")
    climate = _make_climate(
        hass, lux_entity="sensor.lux", lux_threshold=500, _use_lux=True
    )
    assert climate.lux is True


def test_regression_climate_non_numeric_temperature_no_valueerror():
    """Non-numeric temperature states must not raise from is_winter/is_summer."""
    hass = MagicMock()
    hass.states = FakeStates()
    hass.states.set("sensor.indoor_temp", "not-a-number")
    climate = _make_climate(hass)
    assert climate.get_current_temperature is None
    assert climate.is_winter is False
    assert climate.is_summer is False
    inputs = climate.to_inputs()
    assert inputs.is_winter is False and inputs.is_summer is False


def test_regression_climate_non_numeric_outside_falls_back_to_inside():
    hass = MagicMock()
    hass.states = FakeStates()
    hass.states.set("sensor.indoor_temp", "19.0")
    hass.states.set("sensor.outside_temp", "unavailable-ish")
    climate = _make_climate(
        hass, outside_entity="sensor.outside_temp", temp_switch=True
    )
    assert climate.get_current_temperature == 19.0
    assert climate.is_winter is True
    assert climate.outside_high is True  # falls back to permissive default


# --- bug 6: SunData regenerated times per property access (midnight race) ---


def _stub_hass():
    return SimpleNamespace(
        config=SimpleNamespace(
            time_zone="America/Denver",
            latitude=40.76,
            longitude=-111.89,
            elevation=1300,
        )
    )


def test_regression_sun_data_snapshot_cached_per_date(monkeypatch):
    """times/solar_azimuth/solar_elevation must come from one snapshot; a
    per-access regeneration could pair one day's index with another day's
    data around midnight or a DST shift."""
    sun_data = SunData("America/Denver", _stub_hass())
    current = {"today": date(2026, 6, 21)}
    monkeypatch.setattr(sun_data, "_today_local", lambda: current["today"])

    times_first = sun_data.times
    azi_first = sun_data.solar_azimuth
    elev_first = sun_data.solar_elevation
    # Same date: served from the cache, identical objects.
    assert sun_data.times is times_first
    assert sun_data.solar_azimuth is azi_first
    assert sun_data.solar_elevation is elev_first
    assert len(azi_first) == len(times_first) == len(elev_first)
    assert times_first[0].date() == date(2026, 6, 21)

    # Date rolls over: the whole snapshot refreshes together.
    current["today"] = date(2026, 6, 22)
    times_next = sun_data.times
    assert times_next is not times_first
    assert times_next[0].date() == date(2026, 6, 22)
    assert sun_data.solar_azimuth is not azi_first
    assert len(sun_data.solar_azimuth) == len(times_next)
    assert len(sun_data.solar_elevation) == len(times_next)


def test_regression_sun_data_dst_day_lists_match_index(monkeypatch):
    """On a 25-hour DST fall-back day the index is longer; azimuth/elevation
    must match it exactly (a mismatched pairing would misalign by hours)."""
    sun_data = SunData("America/Denver", _stub_hass())
    monkeypatch.setattr(sun_data, "_today_local", lambda: date(2026, 11, 1))
    times = sun_data.times
    assert len(times) == 301  # 25 h * 12 + 1: DST fall-back day
    assert len(sun_data.solar_azimuth) == len(times)
    assert len(sun_data.solar_elevation) == len(times)


def test_regression_sun_data_public_api_intact():
    sun_data = SunData("America/Denver", _stub_hass())
    assert isinstance(sun_data.times, pd.DatetimeIndex)
    assert isinstance(sun_data.solar_azimuth, list)
    assert isinstance(sun_data.solar_elevation, list)
    assert sun_data.sunset() is not None
    assert sun_data.sunrise() is not None


# --- deprecated get_astral_location removal ---


def test_regression_deprecated_get_astral_location_removed():
    """homeassistant.helpers.sun.get_astral_location is deprecated and logged
    a warning per call (15k+ in one live install); sun.py must construct the
    astral Location itself."""
    import inspect

    source = inspect.getsource(sun_module)
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any("homeassistant.helpers.sun" in line for line in import_lines)
    assert "get_astral_location(" not in source  # no call site either
    assert not hasattr(sun_module, "get_astral_location")


def test_regression_astral_location_matches_ha_helper():
    """The direct construction must be equivalent to what the deprecated
    helper produced from the same config."""
    hass = _stub_hass()
    location, elevation = sun_module._astral_location(hass)
    assert elevation == 1300
    assert location.latitude == pytest.approx(40.76)
    assert location.longitude == pytest.approx(-111.89)
    assert str(location.timezone) == "America/Denver"
