"""Golden-day harness: run the CURRENT cover pipeline over a real solar day.

Each scenario fixes location, date, and cover config, then steps through the
day at 15-minute intervals computing the position and reason the current
implementation produces. The rendered schedule is committed under
``goldens/`` and doubles as the acceptance spec for the engine refactor:
the new engine must reproduce these schedules bit-for-bit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
from astral import LocationInfo
from astral import sun as astral_sun
from astral.location import Location
from freezegun import freeze_time

from custom_components.adaptive_cover.calculation import (
    AdaptiveHorizontalCover,
    AdaptiveTiltCover,
    AdaptiveVerticalCover,
    ClimateCoverData,
    ClimateCoverState,
    NormalCoverState,
    get_state_reason,
)
from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
)

GOLDENS_DIR = Path(__file__).parent / "goldens"

SLC = dict(lat=40.76, lon=-111.89, tz="America/Denver")
STEP_MINUTES = 15


class FakeSunData:
    """Deterministic SunData replacement for a fixed date and location."""

    def __init__(self, lat, lon, tz, date):
        info = LocationInfo(name="test", region="test", timezone=tz,
                            latitude=lat, longitude=lon)
        self.location = Location(info)
        self.observer = info.observer
        self.elevation = 0
        self.timezone = tz
        self.date = date
        self.times = pd.date_range(
            start=date, end=date + pd.Timedelta(days=1),
            freq=f"{STEP_MINUTES}min", tz=tz, name="time",
        )
        self.solar_azimuth = [
            astral_sun.azimuth(self.observer, t.to_pydatetime()) for t in self.times
        ]
        self.solar_elevation = [
            astral_sun.elevation(self.observer, t.to_pydatetime()) for t in self.times
        ]

    def sunset(self):
        return astral_sun.sunset(self.observer, self.date)

    def sunrise(self):
        return astral_sun.sunrise(self.observer, self.date)


class FakeStates:
    """Minimal hass.states stand-in."""

    def __init__(self):
        self._states = {}

    def set(self, entity_id, state, attributes=None):
        self._states[entity_id] = SimpleNamespace(
            state=state, attributes=attributes or {}
        )

    def get(self, entity_id):
        return self._states.get(entity_id)


@dataclass
class Scenario:
    """One golden-day scenario."""

    name: str
    date: str  # YYYY-MM-DD
    cover_type: str = "vertical"  # vertical | awning | tilt
    win_azi: float = 180
    fov_left: float = 90
    fov_right: float = 90
    h_win: float = 2.1
    distance: float = 0.5
    h_def: float = 60
    sunset_pos: float = 0
    sunset_off: float = 0
    sunrise_off: float = 0
    min_elevation: float | None = None
    max_elevation: float | None = None
    max_pos: float | None = None
    min_pos: float | None = None
    awn_length: float = 2.1
    awn_angle: float = 0
    tilt_mode: str = "mode2"
    slat_distance: float = 2
    slat_depth: float = 3
    climate: dict | None = None  # {temp, presence, weather}
    location: dict = field(default_factory=lambda: dict(SLC))


SCENARIOS = [
    Scenario(name="slc_south_winter_solstice", date="2026-12-21"),
    Scenario(name="slc_south_summer_solstice", date="2026-06-21"),
    Scenario(name="slc_east_equinox", date="2026-03-20", win_azi=100),
    Scenario(
        name="slc_south_userstyle_equinox",
        date="2026-03-20",
        win_azi=190,
        fov_left=50,
        fov_right=50,
        h_win=2.0,
        distance=0.1,
        h_def=99,
        min_elevation=5,
        max_elevation=50,
        sunset_off=20,
        sunrise_off=-20,
    ),
    Scenario(name="slc_awning_summer", date="2026-06-21", cover_type="awning"),
    Scenario(name="slc_tilt_mode2_equinox", date="2026-03-20", cover_type="tilt"),
    Scenario(
        name="slc_climate_winter_home_sunny",
        date="2026-12-21",
        climate=dict(temp=18.0, presence="home", weather="sunny"),
    ),
    Scenario(
        name="slc_climate_summer_away",
        date="2026-06-21",
        climate=dict(temp=26.0, presence="not_home", weather="sunny"),
    ),
]


def _make_logger():
    logger = ConfigContextAdapter(logging.getLogger("golden"))
    logger.set_config_name("Golden")
    return logger


def _make_cover(scenario, hass, sol_azi, sol_elev):
    common = dict(
        hass=hass,
        logger=_make_logger(),
        sol_azi=sol_azi,
        sol_elev=sol_elev,
        sunset_pos=scenario.sunset_pos,
        sunset_off=scenario.sunset_off,
        sunrise_off=scenario.sunrise_off,
        timezone=scenario.location["tz"],
        fov_left=scenario.fov_left,
        fov_right=scenario.fov_right,
        win_azi=scenario.win_azi,
        h_def=scenario.h_def,
        max_pos=scenario.max_pos,
        min_pos=scenario.min_pos,
        max_pos_bool=False,
        min_pos_bool=False,
        blind_spot_left=None,
        blind_spot_right=None,
        blind_spot_elevation=None,
        blind_spot_on=False,
        min_elevation=scenario.min_elevation,
        max_elevation=scenario.max_elevation,
    )
    if scenario.cover_type == "vertical":
        return AdaptiveVerticalCover(
            **common, distance=scenario.distance, h_win=scenario.h_win
        )
    if scenario.cover_type == "awning":
        return AdaptiveHorizontalCover(
            **common,
            distance=scenario.distance,
            h_win=scenario.h_win,
            awn_length=scenario.awn_length,
            awn_angle=scenario.awn_angle,
        )
    return AdaptiveTiltCover(
        **common,
        slat_distance=scenario.slat_distance,
        depth=scenario.slat_depth,
        mode=scenario.tilt_mode,
    )


def _make_climate(scenario, hass):
    cfg = scenario.climate
    states = hass.states
    states.set("sensor.indoor_temp", str(cfg["temp"]))
    states.set("device_tracker.person", cfg["presence"])
    states.set("weather.home", cfg["weather"])
    return ClimateCoverData(
        hass=hass,
        logger=_make_logger(),
        temp_entity="sensor.indoor_temp",
        temp_low=21.0,
        temp_high=23.0,
        presence_entity="device_tracker.person",
        weather_entity="weather.home",
        weather_condition=["sunny", "partlycloudy", "clear"],
        outside_entity=None,
        temp_switch=False,
        blind_type="cover_tilt" if scenario.cover_type == "tilt" else "cover_blind",
        transparent_blind=False,
        lux_entity=None,
        irradiance_entity=None,
        lux_threshold=None,
        irradiance_threshold=None,
        temp_summer_outside=0,
        _use_lux=False,
        _use_irradiance=False,
    )


def render_scenario(scenario: Scenario) -> str:
    """Run one scenario through the current pipeline; return the schedule text."""
    loc = scenario.location
    date = pd.Timestamp(scenario.date)
    sun_data = FakeSunData(loc["lat"], loc["lon"], loc["tz"], date)

    hass = MagicMock()
    hass.states = FakeStates()

    lines = [
        f"# scenario={scenario.name} date={scenario.date} "
        f"lat={loc['lat']} lon={loc['lon']} tz={loc['tz']}",
        f"# cover={scenario.cover_type} win_azi={scenario.win_azi} "
        f"fov={scenario.fov_left}/{scenario.fov_right} "
        f"elev_range={scenario.min_elevation}..{scenario.max_elevation} "
        f"climate={'on' if scenario.climate else 'off'}",
    ]

    with patch(
        "custom_components.adaptive_cover.calculation.SunData",
        return_value=sun_data,
    ):
        cover = _make_cover(scenario, hass, 180.0, 0.0)
        start, end = cover.solar_times()
        lines.append(f"# solar_times start={start} end={end}")

        for i, ts in enumerate(sun_data.times):
            cover.sol_azi = sun_data.solar_azimuth[i]
            cover.sol_elev = sun_data.solar_elevation[i]
            with freeze_time(ts.to_pydatetime()):
                if scenario.climate:
                    climate = _make_climate(scenario, hass)
                    state = ClimateCoverState(cover, climate)
                    pos = round(float(state.get_state()))
                    reason = get_state_reason(cover, climate)
                else:
                    pos = round(float(NormalCoverState(cover).get_state()))
                    reason = get_state_reason(cover)
            lines.append(
                f"{ts.strftime('%H:%M')} pos={pos:>3} "
                f"azi={cover.sol_azi:6.1f} elev={cover.sol_elev:5.1f} "
                f"reason={reason}"
            )
    return "\n".join(lines) + "\n"


def golden_path(scenario: Scenario) -> Path:
    return GOLDENS_DIR / f"{scenario.name}.txt"
