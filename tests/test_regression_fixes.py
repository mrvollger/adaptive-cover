"""SunData regression tests: sun.py's public API is a contract seam.

Pure-engine counterparts live in tests/engine/test_regression_fixes.py.
The retired adapter-layer tests are pinned at behavior level instead:
solar-times elevation-band handling by
tests/test_entity_surfaces.py::TestSunTimeSensors (Start/End Sun sensors)
and climate-sensor garbage resilience by
tests/simulation/test_climate_scenarios.py::test_sensor_garbage_resilience.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from custom_components.adaptive_cover import sun as sun_module
from custom_components.adaptive_cover.sun import SolarDay, SunData


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


def test_regression_sun_data_snapshot_cached_per_date(freezer):
    """times/solar_azimuth/solar_elevation must come from one snapshot; a
    per-access regeneration could pair one day's index with another day's
    data around midnight or a DST shift."""
    sun_data = SunData("America/Denver", _stub_hass())
    freezer.move_to("2026-06-21 18:00:00+00:00")  # 12:00 MDT, Jun 21

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
    freezer.move_to("2026-06-22 18:00:00+00:00")  # 12:00 MDT, Jun 22
    times_next = sun_data.times
    assert times_next is not times_first
    assert times_next[0].date() == date(2026, 6, 22)
    assert sun_data.solar_azimuth is not azi_first
    assert len(sun_data.solar_azimuth) == len(times_next)
    assert len(sun_data.solar_elevation) == len(times_next)


def test_regression_sun_data_dst_day_lists_match_index(freezer):
    """On a 25-hour DST fall-back day the index is longer; azimuth/elevation
    must match it exactly (a mismatched pairing would misalign by hours)."""
    sun_data = SunData("America/Denver", _stub_hass())
    freezer.move_to("2026-11-01 18:00:00+00:00")  # 11:00 MST, Nov 1 (DST end)
    times = sun_data.times
    assert len(times) == 301  # 25 h * 12 + 1: DST fall-back day
    assert len(sun_data.solar_azimuth) == len(times)
    assert len(sun_data.solar_elevation) == len(times)


def test_regression_sun_data_public_api_intact():
    """The SunData surface; C2 (P2): times is a tuple of tz-aware datetimes."""
    sun_data = SunData("America/Denver", _stub_hass())
    assert isinstance(sun_data.times, tuple)
    assert all(isinstance(ts, datetime) for ts in sun_data.times)
    assert all(ts.tzinfo is not None for ts in sun_data.times)
    assert isinstance(sun_data.solar_azimuth, list)
    assert isinstance(sun_data.solar_elevation, list)
    assert sun_data.sunset() is not None
    assert sun_data.sunrise() is not None


# --- C2 (P2): the pandas table became SolarDay, with the same values ---


@pytest.mark.parametrize(
    ("utc_noon", "points", "hours"),
    [
        ("2026-06-21 18:00:00+00:00", 289, 24),  # an ordinary day
        ("2026-03-08 19:00:00+00:00", 277, 23),  # DST starts: 02:00 -> 03:00
        ("2026-11-01 19:00:00+00:00", 301, 25),  # DST ends: 02:00 -> 01:00
    ],
    ids=["normal_day", "dst_start", "dst_end"],
)
def test_sun_data_day_points_follow_real_time(freezer, utc_noon, points, hours):
    """Local midnight to local midnight, both included, every 5 real minutes.

    The pandas table stepped in real time, so a DST day has one hour of
    points fewer (277) or more (301); the stdlib table must keep that.
    """
    freezer.move_to(utc_noon)
    times = SunData("America/Denver", _stub_hass()).times
    assert len(times) == points
    denver = ZoneInfo("America/Denver")
    first, last = times[0], times[-1]
    assert (first.hour, first.minute) == (0, 0)
    assert (last.hour, last.minute) == (0, 0)
    assert last.date() == first.date() + timedelta(days=1)
    assert last.astimezone(UTC) - first.astimezone(UTC) == timedelta(hours=hours)
    steps = {b.astimezone(UTC) - a.astimezone(UTC) for a, b in zip(times, times[1:])}
    assert steps == {timedelta(minutes=5)}
    assert all(str(ts.tzinfo) == str(denver) for ts in times)


def test_sun_data_values_are_astral_at_each_point(freezer):
    """Same values as before C2: azimuth/elevation[i] are astral at times[i]."""
    freezer.move_to("2026-11-01 19:00:00+00:00")  # the 25-hour day
    sun_data = SunData("America/Denver", _stub_hass())
    location = sun_data.location
    for i in (0, 12, 13, 24, 25, 150, len(sun_data.times) - 1):
        ts = sun_data.times[i]
        assert sun_data.solar_azimuth[i] == location.solar_azimuth(ts, 1300)
        assert sun_data.solar_elevation[i] == location.solar_elevation(ts, 1300)


def test_sun_data_solar_day_is_the_snapshot(freezer):
    freezer.move_to("2026-06-21 18:00:00+00:00")
    sun_data = SunData("America/Denver", _stub_hass())
    day = sun_data.solar_day()
    assert isinstance(day, SolarDay)
    assert day.date == date(2026, 6, 21)
    assert day.times is sun_data.times
    assert day.azimuth is sun_data.solar_azimuth
    assert day.elevation is sun_data.solar_elevation


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
    sun_data = SunData("America/Denver", _stub_hass())
    location, elevation = sun_data.location, sun_data.elevation
    assert elevation == 1300
    assert location.latitude == pytest.approx(40.76)
    assert location.longitude == pytest.approx(-111.89)
    assert str(location.timezone) == "America/Denver"
