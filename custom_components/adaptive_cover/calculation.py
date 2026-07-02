"""Generate values for all types of covers.

The classes here are thin adapters over the pure engine in ``engine/``:
they hold Home Assistant context (hass, entity reads, wall clock) and
delegate every calculation to engine functions. All math lives in
``engine/geometry.py``; all strategy logic lives in ``engine/evaluate.py``.
"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
from homeassistant.core import HomeAssistant

from .config_context_adapter import ConfigContextAdapter
from .engine import evaluate as engine_evaluate
from .engine import geometry as engine_geometry
from .engine.models import (
    BlindSpot,
    ClimateInputs,
    CoverConfig,
    PositionLimits,
    SunSnapshot,
    TimeContext,
)
from .helpers import get_domain, get_safe_attr, get_safe_state
from .sun import SunData


def get_state_reason(cover, climate_data=None):
    """Return human-readable reason for the cover's current position."""
    if climate_data is not None:
        return _get_climate_reason(cover, climate_data)

    if cover.direct_sun_valid:
        return f"Sun in window (azi {cover.sol_azi:.0f}°, elev {cover.sol_elev:.0f}°)"
    if cover.sunset_valid:
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
    not_sunny = (
        climate_data.lux
        or climate_data.irradiance
        or not climate_data.is_sunny
    )

    if not is_summer and not_sunny:
        if climate_data.is_winter and cover.valid:
            return "Winter mode: maximizing sun"
        return "Not sunny weather: using default"

    if is_summer and climate_data.transparent_blind:
        return "Summer mode: blocking sun (transparent blind)"

    if cover.direct_sun_valid:
        return f"Climate mode: sun in window (azi {cover.sol_azi:.0f}°, elev {cover.sol_elev:.0f}°)"

    return get_state_reason(cover)


@dataclass
class AdaptiveGeneralCover(ABC):
    """Adapter between HA context and the pure engine (common data)."""

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

    def __post_init__(self):
        """Add solar data to dataset."""
        self.sun_data = SunData(self.timezone, self.hass)

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
            **self._extra_config(),
        )

    def sun_snapshot(self) -> SunSnapshot:
        """Current solar position as an engine input."""
        return SunSnapshot(azimuth=self.sol_azi, elevation=self.sol_elev)

    def time_context(self) -> TimeContext:
        """Time inputs (naive UTC, matching historical arithmetic)."""
        return TimeContext(
            now_utc=datetime.utcnow(),  # noqa: DTZ003
            sunrise_utc=self.sun_data.sunrise().replace(tzinfo=None),
            sunset_utc=self.sun_data.sunset().replace(tzinfo=None),
        )

    # --- solar day table ---

    def solar_times(self):
        """Determine start/end times."""
        df_today = pd.DataFrame(
            {
                "azimuth": self.sun_data.solar_azimuth,
                "elevation": self.sun_data.solar_elevation,
            }
        )
        solpos = df_today.set_index(self.sun_data.times)

        alpha = solpos["azimuth"]
        frame = (
            (alpha - self.azi_min_abs) % 360
            <= (self.azi_max_abs - self.azi_min_abs) % 360
        ) & (solpos["elevation"] > 0)

        if solpos[frame].empty:
            return None, None
        else:
            return (
                solpos[frame].index[0].to_pydatetime(),
                solpos[frame].index[-1].to_pydatetime(),
            )

    # --- delegated geometry properties (public API preserved) ---

    @property
    def _get_azimuth_edges(self) -> tuple[int, int]:
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
        result = engine_geometry.sunset_valid(
            self.engine_config(), self.time_context()
        )
        self.logger.debug("After sunset plus offset? %s", result)
        return result

    @property
    def default(self) -> float:
        """Change default position at sunset."""
        return engine_geometry.default_position(
            self.engine_config(), self.time_context()
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
            result = np.clip(engine_geometry.calculated_percentage(config, sun), 0, 100)
            if self.apply_max_position and result > self.max_pos:
                return self.max_pos
            if self.apply_min_position and result < self.min_pos:
                return self.min_pos
            return round(result)
        return int(self.h_def)

    def calculate_position(self) -> float:
        """Calculate the position of the blind."""
        raise NotImplementedError

    def calculate_percentage(self) -> int:
        """Calculate percentage from position."""
        return engine_geometry.calculated_percentage(
            self.engine_config(), self.sun_snapshot()
        )


@dataclass
class NormalCoverState:
    """Compute state for normal operation (delegates to the engine)."""

    cover: AdaptiveGeneralCover

    def get_state(self) -> int:
        """Return state."""
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
        return decision.position


@dataclass
class ClimateCoverData:
    """Resolve climate entity readings from HA (adapter for ClimateInputs)."""

    hass: HomeAssistant
    logger: ConfigContextAdapter
    temp_entity: str
    temp_low: float
    temp_high: float
    presence_entity: str
    weather_entity: str
    weather_condition: list[str]
    outside_entity: str
    temp_switch: bool
    blind_type: str
    transparent_blind: bool
    lux_entity: str
    irradiance_entity: str
    lux_threshold: int
    irradiance_threshold: int
    temp_summer_outside: float
    _use_lux: bool
    _use_irradiance: bool

    @property
    def outside_temperature(self):
        """Get outside temperature."""
        temp = None
        if self.outside_entity:
            temp = get_safe_state(
                self.hass,
                self.outside_entity,
            )
        elif self.weather_entity:
            temp = get_safe_attr(self.hass, self.weather_entity, "temperature")
        return temp

    @property
    def inside_temperature(self):
        """Get inside temp from entity."""
        if self.temp_entity is not None:
            if get_domain(self.temp_entity) != "climate":
                temp = get_safe_state(
                    self.hass,
                    self.temp_entity,
                )
            else:
                temp = get_safe_attr(
                    self.hass, self.temp_entity, "current_temperature"
                )
            return temp

    @property
    def get_current_temperature(self) -> float:
        """Get temperature."""
        if self.temp_switch:
            if self.outside_temperature:
                return float(self.outside_temperature)
        if self.inside_temperature:
            return float(self.inside_temperature)

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

    @property
    def is_winter(self) -> bool:
        """Check if temperature is below threshold."""
        if self.temp_low is not None and self.get_current_temperature is not None:
            is_it = self.get_current_temperature < self.temp_low
        else:
            is_it = False

        self.logger.debug(
            "is_winter(): current_temperature < temp_low: %s < %s = %s",
            self.get_current_temperature,
            self.temp_low,
            is_it,
        )
        return is_it

    @property
    def outside_high(self) -> bool:
        """Check if outdoor temperature is above threshold."""
        if (
            self.temp_summer_outside is not None
            and self.outside_temperature is not None
        ):
            return float(self.outside_temperature) > self.temp_summer_outside
        return True

    @property
    def is_summer(self) -> bool:
        """Check if temperature is over threshold."""
        if self.temp_high is not None and self.get_current_temperature is not None:
            is_it = self.get_current_temperature > self.temp_high and self.outside_high
        else:
            is_it = False

        self.logger.debug(
            "is_summer(): current_temp > temp_high and outside_high?: %s > %s and %s = %s",
            self.get_current_temperature,
            self.temp_high,
            self.outside_high,
            is_it,
        )
        return is_it

    @property
    def is_sunny(self) -> bool:
        """Check if condition can contain radiation in winter."""
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

    @property
    def lux(self) -> bool:
        """Get lux value and compare to threshold."""
        if not self._use_lux:
            return False
        if self.lux_entity is not None and self.lux_threshold is not None:
            value = get_safe_state(self.hass, self.lux_entity)
            return float(value) <= self.lux_threshold
        return False

    @property
    def irradiance(self) -> bool:
        """Get irradiance value and compare to threshold."""
        if not self._use_irradiance:
            return False
        if self.irradiance_entity is not None and self.irradiance_threshold is not None:
            value = get_safe_state(self.hass, self.irradiance_entity)
            return float(value) <= self.irradiance_threshold
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

    def get_state(self) -> int:
        """Return state."""
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
        return decision.position


@dataclass
class AdaptiveVerticalCover(AdaptiveGeneralCover):
    """Calculate state for Vertical blinds."""

    distance: float
    h_win: float

    _COVER_TYPE = "vertical"

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


@dataclass
class AdaptiveHorizontalCover(AdaptiveVerticalCover):
    """Calculate state for Horizontal blinds."""

    awn_length: float
    awn_angle: float

    _COVER_TYPE = "awning"

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


@dataclass
class AdaptiveTiltCover(AdaptiveGeneralCover):
    """Calculate state for tilted blinds."""

    slat_distance: float
    depth: float
    mode: str

    _COVER_TYPE = "tilt"

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
