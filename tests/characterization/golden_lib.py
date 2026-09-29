"""Golden-day harness: run the engine over a real solar day.

Each scenario fixes location, date, and cover config, then steps through the
day at 15-minute intervals computing the position and reason via the pure
engine seam ``engine.evaluate(config, sun, ctx, climate)``. The rendered
schedule is committed under ``goldens/`` and doubles as the acceptance spec
for refactors: a new implementation must reproduce these schedules
bit-for-bit.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from astral import LocationInfo
from astral import sun as astral_sun
from astral.location import Location
from homeassistant.util import dt as dt_util

from custom_components.adaptive_cover import calculation
from custom_components.adaptive_cover.engine import evaluate as engine_evaluate
from custom_components.adaptive_cover.engine import geometry as engine_geometry
from custom_components.adaptive_cover.engine.models import (
    ClimateInputs,
    CoverConfig,
    GlareModel,
    Overhang,
    PositionLimits,
    PrivacyConfig,
    SunSnapshot,
    TimeContext,
)

GOLDENS_DIR = Path(__file__).parent / "goldens"

SLC = dict(lat=40.76, lon=-111.89, tz="America/Denver")
STEP_MINUTES = 15

TEMP_LOW = 21.0
TEMP_HIGH = 23.0
WEATHER_CONDITIONS = ("sunny", "partlycloudy", "clear")


class SunDataOverride:
    """Swap ``calculation.sun_data_factory`` for the life of a test scope.

    Usable as a context manager or via ``start()``/``stop()`` (the
    simulation harness spans many awaits). Overrides nest: ``stop()``
    restores whatever factory was active at ``start()``.
    """

    def __init__(self, factory: Callable) -> None:
        self._factory = factory
        self._saved: list[Callable] = []

    def start(self) -> SunDataOverride:
        self._saved.append(calculation.sun_data_factory)
        calculation.sun_data_factory = self._factory
        return self

    def stop(self) -> None:
        calculation.sun_data_factory = self._saved.pop()

    def __enter__(self) -> SunDataOverride:
        return self.start()

    def __exit__(self, *exc_info) -> None:
        self.stop()


def patch_sun_data(sun_data) -> SunDataOverride:
    """THE single test-side place that replaces the production sun provider.

    Every test-side replacement goes through this helper (harness, root
    conftest, entity tests, golden renderer, truth-table generator). It
    uses the production seam ``calculation.sun_data_factory``: every cover
    adapter built while the override is active gets ``sun_data``.
    """
    return SunDataOverride(lambda _timezone, _hass: sun_data)


def use_real_sun_data() -> SunDataOverride:
    """Undo any fake (e.g. the autouse flat sun): adapters get real SunData."""
    from custom_components.adaptive_cover.sun import SunData

    return SunDataOverride(SunData)


def is_integration_context(coordinator, ctx) -> bool:
    """THE single test-side place that knows how our own commands are marked.

    Delegates to the coordinator's public seam ``is_own_context``.
    """
    return coordinator.is_own_context(ctx)


class _NoAstralLocation:
    """The flat sun has no astral location to ask about other days.

    The coordinator's next-event code asks ``sun_data.location`` for
    TOMORROW's sunrise/sunset once today's has passed, inside a try block;
    raising here makes that lookup yield no event, exactly as the old
    MagicMock did (its result could not be compared to a datetime).
    """

    def sunrise(self, *_args, **_kwargs):
        raise LookupError("flat sun: no astral location")

    def sunset(self, *_args, **_kwargs):
        raise LookupError("flat sun: no astral location")


class FlatSunData:
    """Deterministic default sun: azimuth 180 / elevation 45 all day long.

    Replaces the old autouse MagicMock. It implements exactly the SunData
    surface production reads (``times``, ``solar_azimuth``,
    ``solar_elevation``, ``sunrise()``, ``sunset()``, ``location``), so
    an API drift fails loudly instead of returning a Mock.

    Nothing is captured from the wall clock when the fixture is built:
    every value is computed at call time from HA's clock (``dt_util``) in
    HA's configured time zone, so a frozen test sees a frozen sun and the
    table always spans the local day the coordinator's day-rollover check
    compares against. By default the whole day is daylight: sunrise is the
    start of the previous UTC day and sunset the end of the next one. Tests
    move either with ``sunrise_at`` / ``sunset_at``.
    """

    N = 289  # 24h of 5-minute samples, inclusive
    AZIMUTH = 180.0
    ELEVATION = 45.0
    location = _NoAstralLocation()

    def __init__(self) -> None:
        self.sunrise_at: dt.datetime | None = None
        self.sunset_at: dt.datetime | None = None

    @property
    def times(self) -> pd.DatetimeIndex:
        tz = dt_util.DEFAULT_TIME_ZONE
        today_local = dt_util.now(tz).date()
        return pd.date_range(start=today_local, periods=self.N, freq="5min", tz=str(tz))

    @property
    def solar_azimuth(self) -> list[float]:
        return [self.AZIMUTH] * self.N

    @property
    def solar_elevation(self) -> list[float]:
        return [self.ELEVATION] * self.N

    def sunrise(self) -> dt.datetime:
        if self.sunrise_at is not None:
            return self.sunrise_at
        yesterday = dt_util.utcnow().date() - dt.timedelta(days=1)
        return dt.datetime(
            yesterday.year,
            yesterday.month,
            yesterday.day,
            0,
            0,
            1,
            tzinfo=dt.UTC,
        )

    def sunset(self) -> dt.datetime:
        if self.sunset_at is not None:
            return self.sunset_at
        tomorrow = dt_util.utcnow().date() + dt.timedelta(days=1)
        return dt.datetime(
            tomorrow.year,
            tomorrow.month,
            tomorrow.day,
            23,
            59,
            59,
            tzinfo=dt.UTC,
        )


class FakeSunData:
    """Deterministic SunData replacement for a fixed date and location."""

    def __init__(self, lat, lon, tz, date):
        info = LocationInfo(
            name="test", region="test", timezone=tz, latitude=lat, longitude=lon
        )
        self.location = Location(info)
        self.observer = info.observer
        self.elevation = 0
        self.timezone = tz
        self.date = date
        self.times = pd.date_range(
            start=date,
            end=date + pd.Timedelta(days=1),
            freq=f"{STEP_MINUTES}min",
            tz=tz,
            name="time",
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
    overhang: tuple[float, float] | None = None  # (depth, height_above_sill)
    glare: tuple[float, float] | None = None  # (eye_height, occupied_distance)
    privacy: tuple[float, float] | None = None  # (offset_min, position)


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
    # --- redesign feature scenarios (user-house geometry, metric) ---
    Scenario(
        name="house_winter_glare_overhang",
        date="2026-12-21",
        h_win=2.44,
        distance=0.5,
        overhang=(1.22, 3.05),
        glare=(1.22, 0.91),
        privacy=(30, 0),
        climate=dict(temp=18.0, presence="home", weather="sunny"),
    ),
    Scenario(
        name="house_summer_overhang",
        date="2026-06-21",
        h_win=2.44,
        distance=0.5,
        overhang=(1.22, 3.05),
        glare=(1.22, 0.91),
        privacy=(30, 0),
        climate=dict(temp=26.0, presence="home", weather="sunny"),
    ),
    Scenario(
        name="house_equinox_privacy_basic",
        date="2026-03-20",
        h_win=2.44,
        distance=0.5,
        overhang=(1.22, 3.05),
        privacy=(30, 0),
    ),
]


def _engine_config(scenario: Scenario) -> CoverConfig:
    """Build the pure engine config for one scenario."""
    common = dict(
        window_azimuth=scenario.win_azi,
        fov_left=scenario.fov_left,
        fov_right=scenario.fov_right,
        default_position=scenario.h_def,
        sunset_position=scenario.sunset_pos,
        sunset_offset_min=scenario.sunset_off,
        sunrise_offset_min=scenario.sunrise_off,
        min_elevation=scenario.min_elevation,
        max_elevation=scenario.max_elevation,
        limits=PositionLimits(
            min_position=scenario.min_pos,
            max_position=scenario.max_pos,
            min_only_when_sun=False,
            max_only_when_sun=False,
        ),
        overhang=(
            Overhang(
                depth=scenario.overhang[0],
                height_above_sill=scenario.overhang[1],
            )
            if scenario.overhang
            else None
        ),
        glare=(
            GlareModel(
                eye_height=scenario.glare[0],
                occupied_distance=scenario.glare[1],
            )
            if scenario.glare
            else None
        ),
        privacy=(
            PrivacyConfig(
                enabled=True,
                offset_min=scenario.privacy[0],
                position=scenario.privacy[1],
            )
            if scenario.privacy
            else None
        ),
    )
    if scenario.cover_type == "vertical":
        return CoverConfig(
            cover_type="vertical",
            distance_shaded_area=scenario.distance,
            window_height=scenario.h_win,
            **common,
        )
    if scenario.cover_type == "awning":
        return CoverConfig(
            cover_type="awning",
            distance_shaded_area=scenario.distance,
            window_height=scenario.h_win,
            awning_length=scenario.awn_length,
            awning_angle=scenario.awn_angle,
            **common,
        )
    return CoverConfig(
        cover_type="tilt",
        slat_distance=scenario.slat_distance,
        slat_depth=scenario.slat_depth,
        tilt_mode=scenario.tilt_mode,
        **common,
    )


def _climate_inputs(scenario: Scenario) -> ClimateInputs:
    """Resolve the scenario's climate dict the way the adapter would."""
    cfg = scenario.climate
    temp = float(cfg["temp"])
    return ClimateInputs(
        presence=cfg["presence"] == "home",
        is_summer=temp > TEMP_HIGH,
        is_winter=temp < TEMP_LOW,
        is_sunny=cfg["weather"] in WEATHER_CONDITIONS,
        lux_dim=False,
        irradiance_dim=False,
        transparent_blind=False,
    )


def _solar_times(scenario: Scenario, sun_data: FakeSunData):
    """Start/end sun times over the day table (mirrors the adapter's rule)."""
    solpos = pd.DataFrame(
        {
            "azimuth": sun_data.solar_azimuth,
            "elevation": sun_data.solar_elevation,
        }
    ).set_index(sun_data.times)
    azi_min_abs = (scenario.win_azi - scenario.fov_left + 360) % 360
    azi_max_abs = (scenario.win_azi + scenario.fov_right + 360) % 360
    alpha = solpos["azimuth"]
    elevation_ok = solpos["elevation"].map(
        lambda elev: engine_geometry.valid_elevation(
            elev, scenario.min_elevation, scenario.max_elevation
        )
    )
    frame = (
        (alpha - azi_min_abs) % 360 <= (azi_max_abs - azi_min_abs) % 360
    ) & elevation_ok
    if solpos[frame].empty:
        return None, None
    return (
        solpos[frame].index[0].to_pydatetime(),
        solpos[frame].index[-1].to_pydatetime(),
    )


def _basic_reason(config: CoverConfig, sun: SunSnapshot, ctx: TimeContext) -> str:
    """Human-readable reason, byte-identical to get_state_reason()."""
    if engine_geometry.direct_sun_valid(config, sun, ctx):
        return f"Sun in window (azi {sun.azimuth:.0f}°, elev {sun.elevation:.0f}°)"
    if engine_geometry.sunset_valid(config, ctx):
        return "Sunset position"
    if sun.elevation < 0:
        return "Sun below horizon"
    if not engine_geometry.valid_elevation(
        sun.elevation, config.min_elevation, config.max_elevation
    ):
        return f"Elevation {sun.elevation:.0f}° outside configured range"
    if engine_geometry.in_blind_spot(config, sun):
        return "Sun in blind spot"
    if not engine_geometry.sun_in_fov(config, sun):
        g = engine_geometry.gamma(config.window_azimuth, sun.azimuth)
        return f"Sun outside field of view (gamma {g:.0f}°)"
    return "Default position"


def _climate_reason(
    config: CoverConfig,
    sun: SunSnapshot,
    ctx: TimeContext,
    inputs: ClimateInputs,
) -> str:
    """Climate-mode reason, byte-identical to _get_climate_reason()."""
    if not inputs.presence:
        if engine_geometry.sun_in_fov(config, sun):
            if inputs.is_summer:
                return "No presence, summer: blocking sun"
            if inputs.is_winter:
                return "No presence, winter: maximizing sun"
        return "No presence: default position"

    not_sunny = inputs.lux_dim or inputs.irradiance_dim or not inputs.is_sunny

    if not inputs.is_summer and not_sunny:
        if inputs.is_winter and engine_geometry.sun_in_fov(config, sun):
            return "Winter mode: maximizing sun"
        return "Not sunny weather: using default"

    if inputs.is_summer and inputs.transparent_blind:
        return "Summer mode: blocking sun (transparent blind)"

    if engine_geometry.direct_sun_valid(config, sun, ctx):
        return (
            f"Climate mode: sun in window "
            f"(azi {sun.azimuth:.0f}°, elev {sun.elevation:.0f}°)"
        )

    return _basic_reason(config, sun, ctx)


def render_scenario(scenario: Scenario) -> str:
    """Run one scenario through engine.evaluate(); return the schedule text."""
    loc = scenario.location
    date = pd.Timestamp(scenario.date)
    sun_data = FakeSunData(loc["lat"], loc["lon"], loc["tz"], date)

    config = _engine_config(scenario)
    inputs = _climate_inputs(scenario) if scenario.climate else None

    lines = [
        f"# scenario={scenario.name} date={scenario.date} "
        f"lat={loc['lat']} lon={loc['lon']} tz={loc['tz']}",
        f"# cover={scenario.cover_type} win_azi={scenario.win_azi} "
        f"fov={scenario.fov_left}/{scenario.fov_right} "
        f"elev_range={scenario.min_elevation}..{scenario.max_elevation} "
        f"climate={'on' if scenario.climate else 'off'}",
    ]

    start, end = _solar_times(scenario, sun_data)
    lines.append(f"# solar_times start={start} end={end}")

    sunrise_utc = sun_data.sunrise().replace(tzinfo=None)
    sunset_utc = sun_data.sunset().replace(tzinfo=None)

    for i, ts in enumerate(sun_data.times):
        sun = SunSnapshot(
            azimuth=sun_data.solar_azimuth[i],
            elevation=sun_data.solar_elevation[i],
        )
        ctx = TimeContext(
            now_utc=ts.tz_convert("UTC").tz_localize(None).to_pydatetime(),
            sunrise_utc=sunrise_utc,
            sunset_utc=sunset_utc,
        )
        decision = engine_evaluate(config, sun, ctx, inputs)
        pos = round(float(decision.position))
        if scenario.climate:
            reason = _climate_reason(config, sun, ctx, inputs)
        else:
            reason = _basic_reason(config, sun, ctx)
        lines.append(
            f"{ts.strftime('%H:%M')} pos={pos:>3} "
            f"azi={sun.azimuth:6.1f} elev={sun.elevation:5.1f} "
            f"reason={reason}"
        )
    return "\n".join(lines) + "\n"


def golden_path(scenario: Scenario) -> Path:
    return GOLDENS_DIR / f"{scenario.name}.txt"
