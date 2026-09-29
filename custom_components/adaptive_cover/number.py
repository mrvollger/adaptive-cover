"""Number platform: live tunables that skip the options-flow wizard.

Each number writes straight into the config entry's options; the entry
reloads and the new value takes effect within seconds. The wizard shows
the same values, so there is one source of truth.

Range, step, unit and unset-default come from the option spec
(settings/spec.py); this module owns only each number's name, icon and
which entries get it.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    SensorType,
)
from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info
from .entity_surface import apply_surface, window_surface
from .settings.schema import NumberShape, number_shape


@dataclass(frozen=True)
class TunableSpec:
    """One live-tunable option exposed as a number entity."""

    key: str
    name: str  # English name; strings.json entity.number.<key>.name shows it
    icon: str
    blind_only: bool = False
    climate_only: bool = False


# Persona-review scope: only knobs a resident should touch. Motor-protection
# settings (position delta, move cap) stay wizard-only on purpose - users
# tuning those makes things worse.
TUNABLES: tuple[TunableSpec, ...] = (
    TunableSpec(
        CONF_EYE_HEIGHT, "Eye height", "mdi:eye-arrow-left-outline", blind_only=True
    ),
    TunableSpec(
        CONF_OCCUPIED_DISTANCE,
        "Seat distance from window",
        "mdi:sofa-single-outline",
        blind_only=True,
    ),
    TunableSpec(
        CONF_OVERHANG_DEPTH, "Overhang depth", "mdi:home-roof", blind_only=True
    ),
    TunableSpec(
        CONF_OVERHANG_HEIGHT,
        "Overhang height above sill",
        "mdi:arrow-expand-up",
        blind_only=True,
    ),
    TunableSpec(
        CONF_TEMP_LOW,
        "Heating threshold",
        "mdi:thermometer-chevron-down",
        climate_only=True,
    ),
    TunableSpec(
        CONF_TEMP_HIGH,
        "Cooling threshold",
        "mdi:thermometer-chevron-up",
        climate_only=True,
    ),
    TunableSpec(
        CONF_PRIVACY_OFFSET, "Privacy delay after sunset", "mdi:weather-sunset-down"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for one config entry."""
    coordinator: AdaptiveDataUpdateCoordinator = config_entry.runtime_data
    is_blind = config_entry.data.get(CONF_SENSOR_TYPE) == SensorType.BLIND
    is_climate = bool(config_entry.options.get(CONF_CLIMATE_MODE))
    # Climate thresholds are stored and compared in HA's temperature unit,
    # so their numbers show that unit with a range that fits it.
    temperature_unit = hass.config.units.temperature_unit

    entities = [
        AdaptiveCoverNumber(
            config_entry, coordinator, spec, number_shape(spec.key, temperature_unit)
        )
        for spec in TUNABLES
        if (not spec.blind_only or is_blind) and (not spec.climate_only or is_climate)
    ]
    async_add_entities(entities)


class AdaptiveCoverNumber(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], NumberEntity
):
    """A config-entry option exposed as a live-adjustable number."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: AdaptiveDataUpdateCoordinator,
        spec: TunableSpec,
        shape: NumberShape,
    ) -> None:
        """Initialize the tunable."""
        super().__init__(coordinator=coordinator)
        self._config_entry = config_entry
        self._spec = spec
        self._default = shape.default
        self._attr_native_min_value = shape.min
        self._attr_native_max_value = shape.max
        self._attr_native_step = shape.step
        self._attr_native_unit_of_measurement = shape.unit
        self._attr_icon = spec.icon
        self._attr_unique_id = f"{config_entry.entry_id}_number_{spec.key}"
        apply_surface(self, window_surface("number", f"number_{spec.key}"))
        self._device_id = config_entry.entry_id
        self._name = config_entry.data["name"]
        self._attr_device_info = adaptive_cover_device_info(config_entry)

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
            return self._default
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Persist into entry options; the update listener reloads the entry."""
        new_options = {**self._config_entry.options, self._spec.key: value}
        self.hass.config_entries.async_update_entry(
            self._config_entry, options=new_options
        )
