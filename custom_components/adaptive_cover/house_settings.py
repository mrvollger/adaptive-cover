"""The house's settings as entities on the hub device (P5 flip).

Each entity is one house-level value in the layered settings (the hub's
``house`` profile):

- switches: Climate (``climate_on``, primary), manual-move detection
  (``manual_detection``) and the outside-temperature, lux and irradiance
  use-flags (``use_outside_temp``, ``use_lux``, ``use_irradiance``);
- numbers: the heating and cooling thresholds (``temp_low``,
  ``temp_high``) and their hysteresis (``temp_hysteresis``; HA's
  temperature unit and ranges), the manual override duration (minutes),
  the eye height, the seat distance and the privacy delay after sunset;
- times: the end time and the quiet hours' start and end (``end_time``,
  ``quiet_start``, ``quiet_end``; stored as "HH:MM:SS").

Changing one stores it (``layers.async_set_profile``) and every window
acts on it at once, without a reload. Floors, rooms and windows can still
have their own value (``set_profile``, the options form); these entities
show and set the house's.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CLIMATE_ON,
    CONF_END_TIME,
    CONF_EYE_HEIGHT,
    CONF_MANUAL_DETECTION,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_OCCUPIED_DISTANCE,
    CONF_PRIVACY_OFFSET,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_TEMP_HIGH,
    CONF_TEMP_HYSTERESIS,
    CONF_TEMP_LOW,
    CONF_USE_IRRADIANCE,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
)
from .entity_surface import HUB_SURFACE, HUB_UNIQUE_ID, apply_surface
from .layers import (
    SIGNAL_SETTINGS_CHANGED,
    SPEC,
    ProfileError,
    async_set_profile,
    async_settings_changed,
    profile_values,
)
from .settings.resolve import spec_default
from .settings.schema import number_shape
from .settings.spec import Level
from .windows import house_entry

HOUSE_SWITCHES: tuple[str, ...] = (
    CONF_CLIMATE_ON,
    CONF_MANUAL_DETECTION,
    CONF_USE_OUTSIDE_TEMP,
    CONF_USE_LUX,
    CONF_USE_IRRADIANCE,
)
SWITCH_ICONS: dict[str, str] = {
    CONF_CLIMATE_ON: "mdi:home-thermometer-outline",
    CONF_MANUAL_DETECTION: "mdi:hand-back-right-outline",
    CONF_USE_OUTSIDE_TEMP: "mdi:thermometer",
    CONF_USE_LUX: "mdi:brightness-5",
    CONF_USE_IRRADIANCE: "mdi:sun-wireless-outline",
}


@dataclass(frozen=True)
class HouseNumberSpec:
    """One house number: its setting and icon."""

    key: str
    icon: str


HOUSE_NUMBERS: tuple[HouseNumberSpec, ...] = (
    HouseNumberSpec(CONF_TEMP_LOW, "mdi:thermometer-chevron-down"),
    HouseNumberSpec(CONF_TEMP_HIGH, "mdi:thermometer-chevron-up"),
    HouseNumberSpec(CONF_TEMP_HYSTERESIS, "mdi:thermometer-lines"),
    HouseNumberSpec(CONF_MANUAL_OVERRIDE_DURATION, "mdi:timer-outline"),
    HouseNumberSpec(CONF_EYE_HEIGHT, "mdi:eye-arrow-left-outline"),
    HouseNumberSpec(CONF_OCCUPIED_DISTANCE, "mdi:sofa-single-outline"),
    HouseNumberSpec(CONF_PRIVACY_OFFSET, "mdi:weather-sunset-down"),
)

# The override duration shows as minutes (it is stored as a duration).
DURATION_MAX_MINUTES = 24 * 60


def duration_minutes(value: Any) -> float | None:
    """Return a stored duration ({hours, minutes, seconds}) in minutes."""
    if not isinstance(value, dict):
        return None
    return (
        float(value.get("hours", 0) or 0) * 60
        + float(value.get("minutes", 0) or 0)
        + float(value.get("seconds", 0) or 0) / 60
    )


def minutes_duration(minutes: float) -> dict[str, int]:
    """Return the stored duration for ``minutes`` (whole seconds)."""
    total = round(minutes * 60)
    return {
        "hours": total // 3600,
        "minutes": (total % 3600) // 60,
        "seconds": total % 60,
    }


class HouseSetting(Entity):
    """One house-level setting on the hub device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        platform: str,
        key: str,
        device_info: Any,
    ) -> None:
        """Initialize the house setting ``key``."""
        self.hass = hass
        self._key = key
        self._attr_unique_id = f"{HUB_UNIQUE_ID}_{key}"
        apply_surface(self, HUB_SURFACE[(platform, key)])
        self._attr_device_info = device_info

    def _value(self) -> Any:
        """Return the house's value (the spec default when it stores none)."""
        hub = house_entry(self.hass)
        unit = self.hass.config.units.temperature_unit
        if hub is None:
            return spec_default(SPEC[self._key], unit)
        house = profile_values(hub.options, Level.HOUSE, None)
        if self._key in house:
            return house[self._key]
        return spec_default(SPEC[self._key], unit)

    async def _store(self, value: Any) -> None:
        """Store the house's value; every window acts on it at once."""
        try:
            async_set_profile(self.hass, Level.HOUSE, None, {self._key: value})
        except ProfileError as err:
            raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()
        await async_settings_changed(self.hass)

    async def async_added_to_hass(self) -> None:
        """Follow the layered settings (a profile, a lift)."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_SETTINGS_CHANGED, self._settings_changed
            )
        )

    @callback
    def _settings_changed(self) -> None:
        self.async_write_ha_state()


class HouseSettingSwitch(HouseSetting, SwitchEntity):
    """A house-level toggle (Climate, detection, the use-flags)."""

    def __init__(self, hass: HomeAssistant, key: str, device_info: Any) -> None:
        """Initialize the switch."""
        super().__init__(hass, "switch", key, device_info)
        self._attr_icon = SWITCH_ICONS[key]

    @property
    def is_on(self) -> bool:
        """The house's value."""
        return bool(self._value())

    async def async_turn_on(self, **kwargs: Any) -> None:
        """On for the house."""
        await self._store(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Off for the house."""
        await self._store(False)


class HouseSettingNumber(HouseSetting, NumberEntity):
    """A house-level number (thresholds, durations, distances)."""

    _attr_mode = NumberMode.BOX

    def __init__(
        self, hass: HomeAssistant, spec: HouseNumberSpec, device_info: Any
    ) -> None:
        """Initialize the number; ranges come from the option spec."""
        super().__init__(hass, "number", spec.key, device_info)
        self._attr_icon = spec.icon
        self._to_value: Callable[[float], Any] = lambda value: value
        self._from_value: Callable[[Any], float | None] = lambda value: (
            value if isinstance(value, int | float) else None
        )
        # Shown while the house has no value (the old window numbers did the
        # same): the thresholds and the privacy delay.
        self._default: float | None = None
        if spec.key == CONF_MANUAL_OVERRIDE_DURATION:
            self._attr_native_min_value = 1
            self._attr_native_max_value = DURATION_MAX_MINUTES
            self._attr_native_step = 1
            self._attr_native_unit_of_measurement = "min"
            self._to_value = minutes_duration
            self._from_value = duration_minutes
        else:
            # Thresholds show HA's temperature unit and its range.
            shape = number_shape(spec.key, hass.config.units.temperature_unit)
            self._attr_native_min_value = shape.min
            self._attr_native_max_value = shape.max
            self._attr_native_step = shape.step
            self._attr_native_unit_of_measurement = shape.unit
            self._default = shape.default

    @property
    def native_value(self) -> float | None:
        """The house's value (its shown default, else unknown, when it has none)."""
        value = self._from_value(self._value())
        return self._default if value is None else value

    async def async_set_native_value(self, value: float) -> None:
        """Store the house's value."""
        await self._store(self._to_value(value))


HOUSE_TIMES: dict[str, str] = {
    CONF_END_TIME: "mdi:clock-end",
    CONF_QUIET_START: "mdi:sleep",
    CONF_QUIET_END: "mdi:sleep-off",
}


class HouseSettingTime(HouseSetting, TimeEntity):
    """A house-level time of day (the end time, the quiet hours)."""

    def __init__(self, hass: HomeAssistant, key: str, device_info: Any) -> None:
        """Initialize the time."""
        super().__init__(hass, "time", key, device_info)
        self._attr_icon = HOUSE_TIMES[key]

    @property
    def native_value(self) -> dt.time | None:
        """The house's time (unknown when it has none, e.g. no quiet hours)."""
        value = self._value()
        return dt_util.parse_time(value) if isinstance(value, str) else None

    async def async_set_value(self, value: dt.time) -> None:
        """Store the house's time as "HH:MM:SS"."""
        await self._store(value.strftime("%H:%M:%S"))


def house_times(hass: HomeAssistant, device_info: Any) -> list[HouseSettingTime]:
    """Return the hub's house times."""
    return [HouseSettingTime(hass, key, device_info) for key in HOUSE_TIMES]


def house_switches(hass: HomeAssistant, device_info: Any) -> list[HouseSettingSwitch]:
    """Return the hub's house switches."""
    return [HouseSettingSwitch(hass, key, device_info) for key in HOUSE_SWITCHES]


def house_numbers(hass: HomeAssistant, device_info: Any) -> list[HouseSettingNumber]:
    """Return the hub's house numbers."""
    return [HouseSettingNumber(hass, spec, device_info) for spec in HOUSE_NUMBERS]
