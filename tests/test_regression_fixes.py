"""SunData regression tests: sun.py's public API is a contract seam.

Pure-engine counterparts live in tests/engine/test_regression_fixes.py.
The retired adapter-layer tests are pinned at behavior level instead:
solar-times elevation-band handling by
tests/test_entity_surfaces.py::TestSunTimeSensors (Start/End Sun sensors)
and climate-sensor garbage resilience by
tests/simulation/test_climate_scenarios.py::test_sensor_garbage_resilience.
"""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from custom_components.adaptive_cover import sun as sun_module
from custom_components.adaptive_cover.sun import SunData


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
