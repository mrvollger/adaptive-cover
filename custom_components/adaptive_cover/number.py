"""Number platform: live tunables that skip the options-flow wizard.

Each number writes straight into the config entry's options; the entry
reloads and the new value takes effect within seconds. The wizard shows
the same values, so there is one source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CLIMATE_MODE,
    CONF_EYE_HEIGHT,
    CONF_OCCUPIED_DISTANCE,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_PRIVACY_OFFSET,
    CONF_SENSOR_TYPE,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    DOMAIN,
    SensorType,
)
from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info


@dataclass(frozen=True)
class TunableSpec:
    """One live-tunable option exposed as a number entity."""

    key: str
    name: str
    min_value: float
    max_value: float
    step: float
    unit: str | None
    icon: str
    blind_only: bool = False
    climate_only: bool = False
    default: float | None = None  # shown when the option is unset


# Persona-review scope: only knobs a resident should touch. Motor-protection
# settings (position delta, move cap) stay wizard-only on purpose - users
# tuning those makes things worse.
TUNABLES: tuple[TunableSpec, ...] = (
    TunableSpec(
        CONF_EYE_HEIGHT, "Eye height", 0.5, 3.0, 0.05, "m",
        "mdi:eye-arrow-left-outline", blind_only=True,
    ),
    TunableSpec(
        CONF_OCCUPIED_DISTANCE, "Seat distance from window", 0.1, 10.0, 0.1, "m",
        "mdi:sofa-single-outline", blind_only=True,
    ),
    TunableSpec(
        CONF_OVERHANG_DEPTH, "Overhang depth", 0.0, 5.0, 0.05, "m",
        "mdi:home-roof", blind_only=True,
    ),
    TunableSpec(
        CONF_OVERHANG_HEIGHT, "Overhang height above sill", 0.5, 10.0, 0.05, "m",
        "mdi:arrow-expand-up", blind_only=True,
    ),
    TunableSpec(
        CONF_TEMP_LOW, "Heating threshold", 5, 30, 0.5, "°C",
        "mdi:thermometer-chevron-down", climate_only=True, default=21,
    ),
    TunableSpec(
        CONF_TEMP_HIGH, "Cooling threshold", 10, 40, 0.5, "°C",
        "mdi:thermometer-chevron-up", climate_only=True, default=25,
    ),
    TunableSpec(
        CONF_PRIVACY_OFFSET, "Privacy delay after sunset", 0, 180, 5, "min",
        "mdi:weather-sunset-down", default=30,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for one config entry."""
    coordinator: AdaptiveDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    is_blind = config_entry.data.get(CONF_SENSOR_TYPE) == SensorType.BLIND
    is_climate = bool(config_entry.options.get(CONF_CLIMATE_MODE))

    entities = [
        AdaptiveCoverNumber(config_entry, coordinator, spec)
        for spec in TUNABLES
        if (not spec.blind_only or is_blind)
        and (not spec.climate_only or is_climate)
    ]
    async_add_entities(entities)


class AdaptiveCoverNumber(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], NumberEntity
):
    """A config-entry option exposed as a live-adjustable number."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: AdaptiveDataUpdateCoordinator,
        spec: TunableSpec,
    ) -> None:
        """Initialize the tunable."""
        super().__init__(coordinator=coordinator)
        self._config_entry = config_entry
        self._spec = spec
        self._attr_native_min_value = spec.min_value
        self._attr_native_max_value = spec.max_value
        self._attr_native_step = spec.step
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_icon = spec.icon
        self._attr_unique_id = f"{config_entry.entry_id}_number_{spec.key}"
        self._device_id = config_entry.entry_id
        self._name = config_entry.data["name"]
        self._attr_device_info = adaptive_cover_device_info(config_entry)

    @property
    def name(self):
        """Name of the entity."""
        return self._spec.name

    @property
    def native_value(self) -> float | None:
        """Current value from the config entry options.

        Falls back to the effective default so the entity never reads
        "unknown" for options that have one. Geometry options without a
        default (eye height, overhang) legitimately show empty until set -
        setting them is how the feature is enabled.
        """
        value = self._config_entry.options.get(self._spec.key)
        if value is None:
            return self._spec.default
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Persist into entry options; the update listener reloads the entry."""
        new_options = {**self._config_entry.options, self._spec.key: value}
        self.hass.config_entries.async_update_entry(
            self._config_entry, options=new_options
        )
