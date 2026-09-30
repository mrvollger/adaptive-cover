"""Constants for integration_blueprint."""

import logging

DOMAIN = "adaptive_cover"

# Config-entry versions. Home Assistant refuses an entry whose major
# version is above the config flow's, and loads a newer minor as is.
#   1.x: a window config entry, or the hub of window entries (before P7).
#        v2.1 runs neither: they must be consolidated on v2.0.x first
#        (upgrade.py).
#   2.1 (P7, v2.0): the house entry with its windows as subentries of type
#        "window", each storing its entry's data and options verbatim.
#   3.1 (P8, v2.1): the same house; each window subentry stores only what
#        it uses (settings/window_record.py), the switch aliases are gone
#        and the house options keep only the layers. The major bump makes
#        v2.0.x refuse the house instead of running windows it cannot read.
V2_0_HOUSE_VERSION = 2
HOUSE_ENTRY_VERSION = 3
HOUSE_ENTRY_MINOR_VERSION = 1
LOGGER = logging.getLogger(__package__)
_LOGGER = logging.getLogger(__name__)

ATTR_POSITION = "position"
ATTR_TILT_POSITION = "tilt_position"

CONF_AZIMUTH = "set_azimuth"
CONF_BLUEPRINT = "blueprint"
CONF_HEIGHT_WIN = "window_height"
CONF_DISTANCE = "distance_shaded_area"
CONF_DEFAULT_HEIGHT = "default_percentage"
CONF_FOV_LEFT = "fov_left"
CONF_FOV_RIGHT = "fov_right"
# The window's cover (one per window, ADR 0002). The runtime's flat
# options also carry it as CONF_ENTITIES = [cover]; nothing stores that.
CONF_COVER_ENTITY = "cover_entity_id"
CONF_ENTITIES = "group"
CONF_HEIGHT_AWNING = "height_awning"
CONF_LENGTH_AWNING = "length_awning"
CONF_AWNING_ANGLE = "angle"
CONF_SENSOR_TYPE = "sensor_type"
CONF_INVERSE_STATE = "inverse_state"
CONF_SUNSET_POS = "sunset_position"
CONF_SUNSET_OFFSET = "sunset_offset"
CONF_TILT_DEPTH = "slat_depth"
CONF_TILT_DISTANCE = "slat_distance"
CONF_TILT_MODE = "tilt_mode"
CONF_SUNSET_POS = "sunset_position"
CONF_SUNSET_OFFSET = "sunset_offset"
CONF_SUNRISE_OFFSET = "sunrise_offset"
CONF_TEMP_ENTITY = "temp_entity"
CONF_PRESENCE_ENTITY = "presence_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_TEMP_LOW = "temp_low"
CONF_TEMP_HIGH = "temp_high"
CONF_MODE = "mode"
CONF_CLIMATE_MODE = "climate_mode"
CONF_WEATHER_STATE = "weather_state"
CONF_MAX_POSITION = "max_position"
CONF_MIN_POSITION = "min_position"
CONF_ENABLE_MAX_POSITION = "enable_max_position"
CONF_ENABLE_MIN_POSITION = "enable_min_position"
CONF_OUTSIDETEMP_ENTITY = "outside_temp"
CONF_ENABLE_BLIND_SPOT = "blind_spot"
CONF_BLIND_SPOT_RIGHT = "blind_spot_right"
CONF_BLIND_SPOT_LEFT = "blind_spot_left"
CONF_BLIND_SPOT_ELEVATION = "blind_spot_elevation"
CONF_MIN_ELEVATION = "min_elevation"
CONF_MAX_ELEVATION = "max_elevation"
CONF_TRANSPARENT_BLIND = "transparent_blind"
CONF_INTERP_START = "interp_start"
CONF_INTERP_END = "interp_end"
CONF_INTERP_LIST = "interp_list"
CONF_INTERP_LIST_NEW = "interp_list_new"
CONF_INTERP = "interp"
CONF_LUX_ENTITY = "lux_entity"
CONF_LUX_THRESHOLD = "lux_threshold"
CONF_IRRADIANCE_ENTITY = "irradiance_entity"
CONF_IRRADIANCE_THRESHOLD = "irradiance_threshold"
CONF_OUTSIDE_THRESHOLD = "outside_threshold"


# Overhang / glare-band geometry (vertical covers)
CONF_OVERHANG_DEPTH = "overhang_depth"
CONF_OVERHANG_HEIGHT = "overhang_height"
CONF_EYE_HEIGHT = "eye_height"
CONF_OCCUPIED_DISTANCE = "occupied_distance"

# Privacy after dusk
CONF_PRIVACY_MODE = "privacy_mode"
CONF_PRIVACY_OFFSET = "privacy_offset"
CONF_PRIVACY_POSITION = "privacy_position"

# Movement smoothing
CONF_QUIET_START = "quiet_start"
CONF_QUIET_END = "quiet_end"
CONF_MAX_MOVES_HOUR = "max_moves_hour"

CONF_DELTA_POSITION = "delta_position"
CONF_DELTA_TIME = "delta_time"
CONF_START_TIME = "start_time"
CONF_START_ENTITY = "start_entity"
CONF_END_TIME = "end_time"
CONF_END_ENTITY = "end_entity"
CONF_RETURN_SUNSET = "return_sunset"
CONF_MANUAL_OVERRIDE_DURATION = "manual_override_duration"
CONF_MANUAL_OVERRIDE_RESET = "manual_override_reset"
CONF_MANUAL_THRESHOLD = "manual_threshold"
CONF_MANUAL_IGNORE_INTERMEDIATE = "manual_ignore_intermediate"

# The toggles that replaced the per-window switches (P5), as layered
# settings (plan: "Climate on/off", the outside temp / lux / irradiance
# "use-flags", "Manual-move detection"); the house has them as switches.
CONF_CLIMATE_ON = "climate_on"
CONF_USE_OUTSIDE_TEMP = "use_outside_temp"
CONF_USE_LUX = "use_lux"
CONF_USE_IRRADIANCE = "use_irradiance"
CONF_MANUAL_DETECTION = "manual_detection"

STRATEGY_MODE_BASIC = "basic"
STRATEGY_MODE_CLIMATE = "climate"
STRATEGY_MODES = [
    STRATEGY_MODE_BASIC,
    STRATEGY_MODE_CLIMATE,
]


class SensorType:
    """Possible modes for a number selector."""

    BLIND = "cover_blind"
    AWNING = "cover_awning"
    TILT = "cover_tilt"


# Shared defaults: the wizard, the add_entry service baseline, and the
# coordinator fallbacks must agree (they drifted before: 60% vs 100%).
DEFAULT_DEFAULT_HEIGHT = 100
DEFAULT_MANUAL_OVERRIDE_DURATION = {"hours": 2, "minutes": 0, "seconds": 0}
DEFAULT_WEATHER_STATE = ["sunny", "partlycloudy", "clear", "windy", "windy-variant"]
DEFAULT_EYE_HEIGHT = 1.2  # m, seated eyes above the sill
DEFAULT_OCCUPIED_DISTANCE = 2.0  # m from glass to the nearest seat
# Climate thresholds per HA temperature unit: (winter below, summer above)
DEFAULT_TEMP_THRESHOLDS = {"°F": (72, 75), "°C": (22, 24)}
