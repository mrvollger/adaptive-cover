"""Generate values for all types of covers.

The classes here are thin adapters over the pure engine in ``engine/``:
they hold Home Assistant context (hass, entity reads, wall clock) and
delegate every calculation to engine functions. All math lives in
``engine/geometry.py``; all strategy logic lives in ``engine/evaluate.py``.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cached_property
from typing import Any, ClassVar, Self

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_conversion import TemperatureConverter

from .config_context_adapter import ConfigContextAdapter
from .engine import evaluate as engine_evaluate
from .engine import geometry as engine_geometry
from .engine.numeric import clip
from .engine.models import (
    BlindSpot,
    ClimateInputs,
    CoverConfig,
    GlareModel,
    Overhang,
    PositionLimits,
    PrivacyConfig,
    SunSnapshot,
    TimeContext,
)
from .engine.season import Season, SeasonInputs, decide_season
from .helpers import get_domain, get_safe_attr, get_safe_state
from .runtime.clock import SYSTEM_CLOCK, Clock
from .runtime.shade_config import ClimateOptions, ControlState, CoverGeometry
from .sun import SunData

# Seam: how every cover adapter builds its solar day, called as
# ``sun_data_factory(timezone, hass, clock=clock)``. Production always uses
# the real SunData; tests assign a fake factory here instead of patching the
# import (see tests/characterization/golden_lib.patch_sun_data).
sun_data_factory = SunData


def get_state_reason(cover, climate_data=None):
    """Return human-readable reason for the cover's current position."""
    if climate_data is not None:
        return _get_climate_reason(cover, climate_data)

    if cover.direct_sun_valid:
        return f"Sun in window (azi {cover.sol_azi:.0f}°, elev {cover.sol_elev:.0f}°)"
    if cover.sunset_valid or cover.dusk_lead_active:
        return "Sunset position"
    if cover.sol_elev < 0:
        return "Sun below horizon"
    if not cover.valid_elevation:
        return f"Elevation {cover.sol_elev:.0f}° outside configured range"
    if cover.is_sun_in_blind_spot:
        return "Sun in blind spot"
    if not cover.valid:
        return f"Sun outside field of view (gamma {cover.gamma:.0f}°)"
    return "Default position"


def _get_climate_reason(cover, climate_data):
    """Return human-readable reason for climate mode position."""
    if not climate_data.is_presence:
        if cover.valid:
            if climate_data.is_summer:
                return "No presence, summer: blocking sun"
            if climate_data.is_winter:
                return "No presence, winter: maximizing sun"
        return "No presence: default position"

    is_summer = climate_data.is_summer
    not_sunny = climate_data.lux or climate_data.irradiance or not climate_data.is_sunny

    if not is_summer and not_sunny:
        if climate_data.is_winter and cover.valid:
            return "Winter mode: maximizing sun"
        return "Not sunny weather: using default"

    if is_summer and climate_data.transparent_blind:
        return "Summer mode: blocking sun (transparent blind)"

    if cover.direct_sun_valid:
        return f"Climate mode: sun in window (azi {cover.sol_azi:.0f}°, elev {cover.sol_elev:.0f}°)"

    return get_state_reason(cover)


def build_day_forecast(cover, climate_data=None) -> list[dict]:
    """Run the engine over today's 5-minute solar table.

    Returns change-points only: [{time, position, intent}, ...]. Climate
    readings are a snapshot of right now - the forecast assumes current
    temperature/presence/weather persist. Blocking (astral); call from an
    executor.
    """
    config = cover.engine_config()
    sun_data = cover.sun_data
    times = sun_data.times
    azimuths = sun_data.solar_azimuth
    elevations = sun_data.solar_elevation
    sunrise = sun_data.sunrise().replace(tzinfo=None)
    sunset = sun_data.sunset().replace(tzinfo=None)
    sun_at_dusk_lead = cover.sun_at_dusk_lead(sunset)
    inputs = climate_data.to_inputs() if climate_data is not None else None

    entries: list[dict] = []
    last_key = None
    for i, ts in enumerate(times):
        now_utc = ts.astimezone(UTC).replace(tzinfo=None)
        ctx = TimeContext(
            now_utc=now_utc,
            sunrise_utc=sunrise,
            sunset_utc=sunset,
            sun_at_dusk_lead=sun_at_dusk_lead,
        )
        decision = engine_evaluate(
            config,
            SunSnapshot(azimuth=azimuths[i], elevation=elevations[i]),
            ctx,
            inputs,
        )
        position = round(float(decision.position))
        key = (position, str(decision.intent))
        if key != last_key:
            entries.append(
                {
                    "time": ts.isoformat(),
                    "position": position,
                    "intent": str(decision.intent),
                }
            )
            last_key = key
    return entries


@dataclass(kw_only=True)
class AdaptiveGeneralCover(ABC):
    """Adapter between HA context and the pure engine (common data).

    Built from the window's options with :meth:`from_config` (the fields
    are keyword-only: the old 20-odd positional values were order-coupled
    to three option readers in the coordinator).
    """

    hass: HomeAssistant
    logger: ConfigContextAdapter
    sol_azi: float
    sol_elev: float
    sunset_pos: int
    sunset_off: int
    sunrise_off: int
    timezone: str
    fov_left: int
    fov_right: int
    win_azi: int
    h_def: int
    max_pos: int
    min_pos: int
    max_pos_bool: bool
    min_pos_bool: bool
    blind_spot_left: int
    blind_spot_right: int
    blind_spot_elevation: int
    blind_spot_on: bool
    min_elevation: int
    max_elevation: int
    sun_data: SunData = field(init=False)
    # Extended config, assigned by from_config after construction.
    overhang: Overhang | None = field(init=False, default=None)
    glare: GlareModel | None = field(init=False, default=None)
    privacy: PrivacyConfig | None = field(init=False, default=None)
    # Where "now" comes from (runtime/clock.py).
    clock: Clock = SYSTEM_CLOCK

    # Whether the overhang and glare options apply (vertical blinds only).
    _SHADING: ClassVar[bool] = False

    def __post_init__(self):
        """Add solar data to dataset."""
        self.sun_data = sun_data_factory(self.timezone, self.hass, clock=self.clock)

    @classmethod
    def from_config(
        cls,
        hass: HomeAssistant,
        logger: ConfigContextAdapter,
        geometry: CoverGeometry,
        *,
        sun: Sequence[Any],
        timezone: str,
        clock: Clock = SYSTEM_CLOCK,
    ) -> Self:
        """Build the adapter from the window's options.

        ``sun`` is the solar (azimuth, elevation) now; ``timezone`` is HA's
        configured time zone; ``clock`` is the coordinator's.
        """
        cover = cls(
            hass=hass,
            logger=logger,
            clock=clock,
            sol_azi=sun[0],
            sol_elev=sun[1],
            sunset_pos=geometry.sunset_pos,
            sunset_off=geometry.sunset_off,
            sunrise_off=geometry.sunrise_off,
            timezone=timezone,
            fov_left=geometry.fov_left,
            fov_right=geometry.fov_right,
            win_azi=geometry.win_azi,
            h_def=geometry.h_def,
            max_pos=geometry.max_pos,
            min_pos=geometry.min_pos,
            max_pos_bool=geometry.max_pos_bool,
            min_pos_bool=geometry.min_pos_bool,
            blind_spot_left=geometry.blind_spot_left,
            blind_spot_right=geometry.blind_spot_right,
            blind_spot_elevation=geometry.blind_spot_elevation,
            blind_spot_on=geometry.blind_spot_on,
            min_elevation=geometry.min_elevation,
            max_elevation=geometry.max_elevation,
            **cls._type_fields(geometry),
        )
        cover._attach_extended(geometry)
        return cover

    @classmethod
    def _type_fields(cls, geometry: CoverGeometry) -> dict[str, Any]:
        """Return the constructor fields of one cover type."""
        return {}

    def _attach_extended(self, geometry: CoverGeometry) -> None:
        """Attach the overhang, glare and privacy config."""
        depth = geometry.overhang_depth
        height = geometry.overhang_height
        if depth and height and self._SHADING:
            self.overhang = Overhang(depth=depth, height_above_sill=height)
        eye_height = geometry.eye_height
        occupied = geometry.occupied_distance
        if eye_height and occupied and self._SHADING:
            self.glare = GlareModel(eye_height=eye_height, occupied_distance=occupied)
        if geometry.privacy_mode:
            self.privacy = PrivacyConfig(
                enabled=True,
                offset_min=geometry.privacy_offset,
                position=geometry.privacy_position,
            )

    # --- engine input builders ---

    _COVER_TYPE = "vertical"

    def _extra_config(self) -> dict:
        """Cover-type-specific config fields."""
        return {}

    def engine_config(self) -> CoverConfig:
        """Build the pure engine config from this adapter's fields."""
        return CoverConfig(
            cover_type=self._COVER_TYPE,
            window_azimuth=self.win_azi,
            fov_left=self.fov_left,
            fov_right=self.fov_right,
            default_position=self.h_def,
            sunset_position=self.sunset_pos,
            sunset_offset_min=self.sunset_off,
            sunrise_offset_min=self.sunrise_off,
            min_elevation=self.min_elevation,
            max_elevation=self.max_elevation,
            blind_spot=BlindSpot(
                left=self.blind_spot_left,
                right=self.blind_spot_right,
                elevation=self.blind_spot_elevation,
                enabled=bool(self.blind_spot_on),
            ),
            limits=PositionLimits(
                min_position=self.min_pos,
                max_position=self.max_pos,
                min_only_when_sun=bool(self.min_pos_bool),
                max_only_when_sun=bool(self.max_pos_bool),
            ),
            overhang=self.overhang,
            glare=self.glare,
            privacy=self.privacy,
            **self._extra_config(),
        )

    def sun_snapshot(self) -> SunSnapshot:
        """Return the current solar position as an engine input."""
        return SunSnapshot(azimuth=self.sol_azi, elevation=self.sol_elev)

    def time_context(self) -> TimeContext:
        """Time inputs (naive UTC, matching historical arithmetic)."""
        sunset_utc = self.sun_data.sunset().replace(tzinfo=None)
        return TimeContext(
            now_utc=self.clock.utcnow().replace(tzinfo=None),
            sunrise_utc=self.sun_data.sunrise().replace(tzinfo=None),
            sunset_utc=sunset_utc,
            sun_at_dusk_lead=self.sun_at_dusk_lead(sunset_utc),
        )

    def sun_at_dusk_lead(self, sunset_utc: datetime) -> SunSnapshot | None:
        """Solar position DUSK_LEAD before the sunset position starts.

        The engine's dusk lead needs to know whether the sun was still in
        the window then. None when the sun provider cannot tell.
        """
        when = (
            sunset_utc
            + timedelta(minutes=self.sunset_off or 0)
            - engine_geometry.DUSK_LEAD
        ).replace(tzinfo=UTC)
        try:
            location = self.sun_data.location
            elevation = getattr(self.sun_data, "elevation", 0) or 0
            return SunSnapshot(
                azimuth=location.solar_azimuth(when, elevation),
                elevation=location.solar_elevation(when, elevation),
            )
        except (AttributeError, LookupError, ValueError):
            return None

    # --- solar day table ---

    def solar_times(self):
        """Determine start/end times.

        The first and last table points with the sun inside the azimuth
        window and the elevation band, or (None, None).
        """
        azi_min_abs = self.azi_min_abs
        span = (self.azi_max_abs - azi_min_abs) % 360
        # Use the same elevation predicate the engine enforces (min/max
        # elevation band) so the start/end sun-time sensors agree with
        # when control actually engages.
        in_window = [
            ts
            for ts, alpha, elev in zip(
                self.sun_data.times,
                self.sun_data.solar_azimuth,
                self.sun_data.solar_elevation,
                strict=True,
            )
            if (alpha - azi_min_abs) % 360 <= span
            and engine_geometry.valid_elevation(
                elev, self.min_elevation, self.max_elevation
            )
        ]
        if not in_window:
            return None, None
        return in_window[0], in_window[-1]

    # --- delegated geometry properties (public API preserved) ---

    @property
    def _get_azimuth_edges(self) -> float:
        """Calculate azimuth edges."""
        return self.fov_left + self.fov_right

    @property
    def is_sun_in_blind_spot(self) -> bool:
        """Check if sun is in blind spot."""
        result = engine_geometry.in_blind_spot(
            self.engine_config(), self.sun_snapshot()
        )
        if self.blind_spot_on:
            self.logger.debug("Is sun in blind spot? %s", result)
        return result

    @property
    def azi_min_abs(self) -> int:
        """Calculate min azimuth."""
        return (self.win_azi - self.fov_left + 360) % 360

    @property
    def azi_max_abs(self) -> int:
        """Calculate max azimuth."""
        return (self.win_azi + self.fov_right + 360) % 360

    @property
    def gamma(self) -> float:
        """Calculate Gamma."""
        return engine_geometry.gamma(self.win_azi, self.sol_azi)

    @property
    def valid_elevation(self) -> bool:
        """Check if elevation is within range."""
        return engine_geometry.valid_elevation(
            self.sol_elev, self.min_elevation, self.max_elevation
        )

    @property
    def valid(self) -> bool:
        """Determine if sun is in front of window."""
        valid = engine_geometry.sun_in_fov(self.engine_config(), self.sun_snapshot())
        self.logger.debug("Sun in front of window (ignoring blindspot)? %s", valid)
        return valid

    @property
    def sunset_valid(self) -> bool:
        """Determine if it is after sunset plus offset."""
        result = engine_geometry.sunset_valid(self.engine_config(), self.time_context())
        self.logger.debug("After sunset plus offset? %s", result)
        return result

    @property
    def dusk_lead_active(self) -> bool:
        """Check whether the sun left the window just before dusk (engine rule)."""
        return engine_geometry.dusk_lead_active(
            self.engine_config(), self.sun_snapshot(), self.time_context()
        )

    @property
    def default(self) -> float:
        """Change default position at sunset."""
        return engine_geometry.default_position(
            self.engine_config(), self.sun_snapshot(), self.time_context()
        )

    def fov(self) -> list:
        """Return field of view."""
        return [self.azi_min_abs, self.azi_max_abs]

    @property
    def apply_min_position(self) -> bool:
        """Check if min position is applied."""
        if self.min_pos is not None and self.min_pos != 0:
            if self.min_pos_bool:
                return self.direct_sun_valid
            return True
        return False

    @property
    def apply_max_position(self) -> bool:
        """Check if max position is applied."""
        if self.max_pos is not None and self.max_pos != 100:
            if self.max_pos_bool:
                return self.direct_sun_valid
            return True
        return False

    @property
    def direct_sun_valid(self) -> bool:
        """Check if sun is directly in front of window."""
        return engine_geometry.direct_sun_valid(
            self.engine_config(), self.sun_snapshot(), self.time_context()
        )

    def calculate_percentage_at(self, azi, elev):
        """Calculate position at a future solar position using geometry only.

        Bypasses sunset_valid/direct_sun_valid time-of-day checks since we're
        predicting for a future time, not the current wall-clock time.
        """
        config = self.engine_config()
        sun = SunSnapshot(azimuth=azi, elevation=elev)
        if engine_geometry.sun_in_fov(config, sun) and elev > 0:
            result = clip(engine_geometry.calculated_percentage(config, sun), 0, 100)
            if self.apply_max_position and result > self.max_pos:
                return self.max_pos
            if self.apply_min_position and result < self.min_pos:
                return self.min_pos
            return round(result)
        return int(self.h_def)

    def calculate_position(self) -> float:
        """Calculate the position of the blind."""
        raise NotImplementedError

    def calculate_percentage(self) -> float:
        """Calculate percentage from position."""
        return engine_geometry.calculated_percentage(
            self.engine_config(), self.sun_snapshot()
        )


@dataclass
class NormalCoverState:
    """Compute state for normal operation (delegates to the engine)."""

    cover: AdaptiveGeneralCover

    def get_decision(self):
        """Return the full engine Decision (position, intent, trace)."""
        decision = engine_evaluate(
            self.cover.engine_config(),
            self.cover.sun_snapshot(),
            self.cover.time_context(),
        )
        self.cover.logger.debug(
            "Normal state: %s (intent=%s, trace=%s)",
            decision.position,
            decision.intent,
            "; ".join(decision.trace),
        )
        return decision

    def get_state(self) -> float:
        """Return state."""
        return self.get_decision().position


@dataclass(kw_only=True)
class ClimateCoverData:
    """Resolve climate entity readings from HA (adapter for ClimateInputs).

    Built from the window's options with :meth:`from_config`, once per
    decision. The season is decided once (:attr:`season`), from the
    readings and the season the window's previous decision found
    (``previous_season``, the hysteresis memory the coordinator keeps).
    """

    hass: HomeAssistant
    logger: ConfigContextAdapter
    temp_entity: str
    temp_low: float
    temp_high: float
    presence_entity: str
    weather_entity: str
    weather_condition: list[str]
    outside_entity: str
    temp_switch: bool | None  # None until the switch restores
    blind_type: str | None
    transparent_blind: bool
    lux_entity: str
    irradiance_entity: str
    lux_threshold: int
    irradiance_threshold: int
    temp_summer_outside: float
    _use_lux: bool | None
    _use_irradiance: bool | None
    temp_hysteresis: float | None = 0
    """How far past a threshold the season must go to flip (None, 0: off)."""
    previous_season: Season | None = None
    """The season the window's previous decision found (None: plain rule)."""

    @classmethod
    def from_config(
        cls,
        hass: HomeAssistant,
        logger: ConfigContextAdapter,
        climate: ClimateOptions,
        controls: ControlState,
        blind_type: str | None,
        previous_season: Season | None = None,
    ) -> Self:
        """Build the adapter from the window's options and switch toggles.

        ``previous_season`` is the season the window's previous decision
        found: the season is sticky by the hysteresis from there.
        """
        return cls(
            hass=hass,
            logger=logger,
            temp_entity=climate.temp_entity,
            temp_low=climate.temp_low,
            temp_high=climate.temp_high,
            presence_entity=climate.presence_entity,
            weather_entity=climate.weather_entity,
            weather_condition=climate.weather_condition,
            outside_entity=climate.outside_entity,
            temp_switch=controls.outside_temp,
            blind_type=blind_type,
            transparent_blind=climate.transparent_blind,
            lux_entity=climate.lux_entity,
            irradiance_entity=climate.irradiance_entity,
            lux_threshold=climate.lux_threshold,
            irradiance_threshold=climate.irradiance_threshold,
            temp_summer_outside=climate.temp_summer_outside,
            _use_lux=controls.lux,
            _use_irradiance=controls.irradiance,
            temp_hysteresis=climate.temp_hysteresis,
            previous_season=previous_season,
        )

    @staticmethod
    def _as_float(value):
        """Coerce an entity reading to float; None for missing/non-numeric.

        Unavailable sensors surface as None (get_safe_state) and flaky ones
        as non-numeric strings; float() on either raised and killed every
        coordinator update.
        """
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _system_temperature_unit(self) -> str | None:
        """HA's configured temperature unit, or None if unavailable."""
        units = getattr(getattr(self.hass, "config", None), "units", None)
        unit = getattr(units, "temperature_unit", None)
        return unit if isinstance(unit, str) else None

    def _to_system_unit(self, value, from_unit) -> float | None:
        """Convert a reading into HA's configured temperature unit.

        Thresholds (temp_low/high, outside threshold) are interpreted in the
        system unit. Readings used to be compared raw, so a °F sensor
        against thresholds entered in °C pinned every entry in "summer".
        Unknown units pass through unchanged.
        """
        reading = self._as_float(value)
        if reading is None:
            return None
        to_unit = self._system_temperature_unit()
        if (
            not isinstance(from_unit, str)
            or to_unit is None
            or from_unit == to_unit
            or from_unit not in TemperatureConverter.VALID_UNITS
            or to_unit not in TemperatureConverter.VALID_UNITS
        ):
            return reading
        return TemperatureConverter.convert(reading, from_unit, to_unit)

    @property
    def outside_temperature(self):
        """Get outside temperature (in HA's configured unit)."""
        if self.outside_entity:
            return self._to_system_unit(
                get_safe_state(self.hass, self.outside_entity),
                get_safe_attr(self.hass, self.outside_entity, ATTR_UNIT_OF_MEASUREMENT),
            )
        if self.weather_entity:
            return self._to_system_unit(
                get_safe_attr(self.hass, self.weather_entity, "temperature"),
                get_safe_attr(self.hass, self.weather_entity, "temperature_unit"),
            )
        return None

    @property
    def inside_temperature(self):
        """Get inside temperature (in HA's configured unit)."""
        if self.temp_entity is None:
            return None
        if get_domain(self.temp_entity) != "climate":
            return self._to_system_unit(
                get_safe_state(self.hass, self.temp_entity),
                get_safe_attr(self.hass, self.temp_entity, ATTR_UNIT_OF_MEASUREMENT),
            )
        # Climate entities already report in the system unit.
        return self._as_float(
            get_safe_attr(self.hass, self.temp_entity, "current_temperature")
        )

    @property
    def get_current_temperature(self) -> float | None:
        """Get temperature."""
        if self.temp_switch:
            outside = self._as_float(self.outside_temperature)
            if outside is not None:
                return outside
        return self._as_float(self.inside_temperature)

    @property
    def is_presence(self):
        """Checks if people are present."""
        presence = None
        if self.presence_entity is not None:
            presence = get_safe_state(self.hass, self.presence_entity)
        # set to true if no sensor is defined
        if presence is not None:
            domain = get_domain(self.presence_entity)
            if domain == "device_tracker":
                return presence == "home"
            if domain == "zone":
                return int(presence) > 0
            if domain in ["binary_sensor", "input_boolean"]:
                return presence == "on"
        return True

    @cached_property
    def season(self) -> Season:
        """This decision's season, sticky by the hysteresis (engine/season.py).

        Decided once per adapter (one per refresh), so the position, the
        reason, the Control method and the forecast agree on it.
        """
        season = decide_season(
            SeasonInputs(
                temperature=self.get_current_temperature,
                temp_low=self.temp_low,
                temp_high=self.temp_high,
                hysteresis=self._as_float(self.temp_hysteresis) or 0.0,
                outside_high=self.outside_high,
            ),
            self.previous_season,
        )
        self.logger.debug(
            "season(): %s at %s (low %s, high %s, outside_high %s, "
            "hysteresis %s, previous %s)",
            season.name,
            self.get_current_temperature,
            self.temp_low,
            self.temp_high,
            self.outside_high,
            self.temp_hysteresis,
            None if self.previous_season is None else self.previous_season.name,
        )
        return season

    @property
    def is_winter(self) -> bool:
        """Check if temperature is below threshold (sticky by the hysteresis)."""
        return self.season.winter

    @property
    def outside_high(self) -> bool:
        """Check if outdoor temperature is above threshold."""
        outside = self._as_float(self.outside_temperature)
        if self.temp_summer_outside is not None and outside is not None:
            return outside > self.temp_summer_outside
        return True

    @property
    def is_summer(self) -> bool:
        """Check if temperature is over threshold (sticky by the hysteresis)."""
        return self.season.summer

    @property
    def is_sunny(self) -> bool | None:
        """Check if condition can contain radiation in winter (None: no sunny states)."""
        weather_state = None
        if self.weather_entity is not None:
            weather_state = get_safe_state(self.hass, self.weather_entity)
        else:
            self.logger.debug("is_sunny(): No weather entity defined")
            return True
        if self.weather_condition is not None:
            matches = weather_state in self.weather_condition
            self.logger.debug("is_sunny(): Weather: %s = %s", weather_state, matches)
            return matches
        return None

    @property
    def lux(self) -> bool:
        """Get lux value and compare to threshold."""
        if not self._use_lux:
            return False
        if self.lux_entity is not None and self.lux_threshold is not None:
            value = self._as_float(get_safe_state(self.hass, self.lux_entity))
            if value is None:
                return False
            return value <= self.lux_threshold
        return False

    @property
    def irradiance(self) -> bool:
        """Get irradiance value and compare to threshold."""
        if not self._use_irradiance:
            return False
        if self.irradiance_entity is not None and self.irradiance_threshold is not None:
            value = self._as_float(get_safe_state(self.hass, self.irradiance_entity))
            if value is None:
                return False
            return value <= self.irradiance_threshold
        return False

    def to_inputs(self) -> ClimateInputs:
        """Resolve all entity readings into pure engine inputs."""
        return ClimateInputs(
            presence=bool(self.is_presence),
            is_summer=bool(self.is_summer),
            is_winter=bool(self.is_winter),
            is_sunny=self.is_sunny,
            lux_dim=bool(self.lux),
            irradiance_dim=bool(self.irradiance),
            transparent_blind=bool(self.transparent_blind),
        )


@dataclass
class ClimateCoverState(NormalCoverState):
    """Compute state for climate control operation (delegates to the engine)."""

    climate_data: ClimateCoverData

    def get_decision(self):
        """Return the full engine Decision (position, intent, trace)."""
        decision = engine_evaluate(
            self.cover.engine_config(),
            self.cover.sun_snapshot(),
            self.cover.time_context(),
            self.climate_data.to_inputs(),
        )
        self.cover.logger.debug(
            "Climate state: %s (intent=%s, trace=%s)",
            decision.position,
            decision.intent,
            "; ".join(decision.trace),
        )
        return decision

    def get_state(self) -> float:
        """Return state."""
        return self.get_decision().position


@dataclass(kw_only=True)
class AdaptiveVerticalCover(AdaptiveGeneralCover):
    """Calculate state for Vertical blinds."""

    distance: float
    h_win: float

    _COVER_TYPE = "vertical"
    _SHADING: ClassVar[bool] = True

    @classmethod
    def _type_fields(cls, geometry: CoverGeometry) -> dict[str, Any]:
        return {"distance": geometry.distance, "h_win": geometry.h_win}

    def _extra_config(self) -> dict:
        return {
            "distance_shaded_area": self.distance,
            "window_height": self.h_win,
        }

    def calculate_position(self) -> float:
        """Calculate blind height."""
        return engine_geometry.vertical_blind_height(
            self.engine_config(), self.sun_snapshot()
        )


@dataclass(kw_only=True)
class AdaptiveHorizontalCover(AdaptiveVerticalCover):
    """Calculate state for Horizontal blinds."""

    awn_length: float
    awn_angle: float

    _COVER_TYPE = "awning"
    _SHADING: ClassVar[bool] = False

    @classmethod
    def _type_fields(cls, geometry: CoverGeometry) -> dict[str, Any]:
        return {
            **super()._type_fields(geometry),
            "awn_length": geometry.awn_length,
            "awn_angle": geometry.awn_angle,
        }

    def _extra_config(self) -> dict:
        return {
            "distance_shaded_area": self.distance,
            "window_height": self.h_win,
            "awning_length": self.awn_length,
            "awning_angle": self.awn_angle,
        }

    def calculate_position(self) -> float:
        """Calculate awn length from blind height."""
        return engine_geometry.awning_extension(
            self.engine_config(), self.sun_snapshot()
        )


@dataclass(kw_only=True)
class AdaptiveTiltCover(AdaptiveGeneralCover):
    """Calculate state for tilted blinds."""

    slat_distance: float
    depth: float
    mode: str

    _COVER_TYPE = "tilt"

    @classmethod
    def _type_fields(cls, geometry: CoverGeometry) -> dict[str, Any]:
        return {
            "slat_distance": geometry.slat_distance,
            "depth": geometry.slat_depth,
            "mode": geometry.tilt_mode,
        }

    def _extra_config(self) -> dict:
        return {
            "slat_distance": self.slat_distance,
            "slat_depth": self.depth,
            "tilt_mode": self.mode,
        }

    @property
    def beta(self):
        """Calculate beta."""
        return engine_geometry.tilt_beta(self.engine_config(), self.sun_snapshot())

    def calculate_position(self) -> float:
        """Calculate position of venetian blinds.

        https://www.mdpi.com/1996-1073/13/7/1731
        """
        return engine_geometry.tilt_slat_angle(
            self.engine_config(), self.sun_snapshot()
        )


# The adapter class for each cover type (entry data ``sensor_type``).
COVER_ADAPTERS: dict[str, type[AdaptiveGeneralCover]] = {
    "cover_blind": AdaptiveVerticalCover,
    "cover_awning": AdaptiveHorizontalCover,
    "cover_tilt": AdaptiveTiltCover,
}


def build_cover(
    cover_type: str | None,
    hass: HomeAssistant,
    logger: ConfigContextAdapter,
    geometry: CoverGeometry,
    *,
    sun: Sequence[Any],
    timezone: str,
    clock: Clock = SYSTEM_CLOCK,
) -> AdaptiveGeneralCover:
    """Build the adapter for ``cover_type`` from the window's options.

    ``clock`` is where the adapter and its solar day read "now": the
    coordinator passes its own.
    """
    adapter = COVER_ADAPTERS.get(cover_type or "")
    if adapter is None:
        raise ValueError(f"Unknown cover type {cover_type!r}")
    return adapter.from_config(
        hass, logger, geometry, sun=sun, timezone=timezone, clock=clock
    )
