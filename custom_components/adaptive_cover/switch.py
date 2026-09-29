"""Switch platform for the Adaptive Cover integration.

P5 flip: the six per-window switches are hidden aliases (removed in P8).
They stay registered and enabled for one release so existing automations
keep working:

- **Toggle Control** writes through to the window's Mode (on: automatic
  control on, off: Mode off) and mirrors it. It no longer restores
  itself: the Mode select restores the control state, and reads this
  switch's last state on its first boot after the flip.
- **Manual Override, Climate Mode, Outside Temperature, Lux,
  Irradiance** are the window's value of the toggle settings
  ``manual_detection``, ``climate_on``, ``use_outside_temp``, ``use_lux``
  and ``use_irradiance`` (migration 1.4 recorded their states in the
  layered settings). A switch shows the value the window acts on and
  writes through to the window's own value (``layers.async_write_window``:
  none of these may be overridden by a window in the spec, so the value
  is a per-window legacy value, removed when it equals what the window
  inherits). Until the house is lifted a switch is the setting itself, as
  before the flip.

Which switches a window has follows its resolved settings (climate mode
and the outside-temperature, lux and irradiance entities).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CLIMATE_MODE,
    CONF_CLIMATE_ON,
    CONF_ENTITIES,
    CONF_IRRADIANCE_ENTITY,
    CONF_LUX_ENTITY,
    CONF_MANUAL_DETECTION,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_USE_IRRADIANCE,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
    CONF_WEATHER_ENTITY,
)
from .coordinator import AdaptiveDataUpdateCoordinator
from .entity_shared import adaptive_cover_device_info
from .entity_surface import apply_surface, window_surface
from .layers import async_write_window, is_layered

# The coordinator attribute each switch used to set -> the toggle setting.
TOGGLE_KEYS: dict[str, str] = {
    "manual_toggle": CONF_MANUAL_DETECTION,
    "switch_mode": CONF_CLIMATE_ON,
    "temp_toggle": CONF_USE_OUTSIDE_TEMP,
    "lux_toggle": CONF_USE_LUX,
    "irradiance_toggle": CONF_USE_IRRADIANCE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a window's switch aliases, or the hub's house switches."""
    from .hub import hub_device_info, is_hub_entry

    if is_hub_entry(config_entry):
        from .house_settings import house_switches

        async_add_entities(house_switches(hass, hub_device_info()))
        return
    coordinator: AdaptiveDataUpdateCoordinator = config_entry.runtime_data

    manual_switch = AdaptiveCoverSwitch(
        config_entry,
        config_entry.entry_id,
        "Manual Override",
        True,
        "manual_toggle",
        coordinator,
    )
    control_switch = ControlAliasSwitch(
        config_entry,
        config_entry.entry_id,
        "Toggle Control",
        True,
        "control_toggle",
        coordinator,
    )
    climate_switch = AdaptiveCoverSwitch(
        config_entry,
        config_entry.entry_id,
        "Climate Mode",
        True,
        "switch_mode",
        coordinator,
    )
    temp_switch = AdaptiveCoverSwitch(
        config_entry,
        config_entry.entry_id,
        "Outside Temperature",
        False,
        "temp_toggle",
        coordinator,
    )
    lux_switch = AdaptiveCoverSwitch(
        config_entry,
        config_entry.entry_id,
        "Lux",
        True,
        "lux_toggle",
        coordinator,
    )
    irradiance_switch = AdaptiveCoverSwitch(
        config_entry,
        config_entry.entry_id,
        "Irradiance",
        True,
        "irradiance_toggle",
        coordinator,
    )

    settings = coordinator.options
    climate_mode = settings.get(CONF_CLIMATE_MODE)
    weather_entity = settings.get(CONF_WEATHER_ENTITY)
    sensor_entity = settings.get(CONF_OUTSIDETEMP_ENTITY)
    lux_entity = settings.get(CONF_LUX_ENTITY)
    irradiance_entity = settings.get(CONF_IRRADIANCE_ENTITY)
    switches = []

    if len(config_entry.options.get(CONF_ENTITIES) or []) >= 1:
        switches = [control_switch, manual_switch]

    if climate_mode:
        switches.append(climate_switch)
        if weather_entity or sensor_entity:
            switches.append(temp_switch)
        if lux_entity:
            switches.append(lux_switch)
        if irradiance_entity:
            switches.append(irradiance_switch)

    async_add_entities(switches)


class AdaptiveCoverSwitch(
    CoordinatorEntity[AdaptiveDataUpdateCoordinator], SwitchEntity, RestoreEntity
):
    """A window's toggle setting as a (hidden) switch alias (P5 flip)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        config_entry,
        unique_id: str,
        switch_name: str,
        initial_state: bool,
        key: str,
        coordinator: AdaptiveDataUpdateCoordinator,
        device_class: SwitchDeviceClass | None = None,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator=coordinator)
        self._config_entry = config_entry
        self._name = config_entry.data["name"]
        self._state: bool | None = None
        self._key = key
        self._setting = TOGGLE_KEYS.get(key)
        self._switch_name = switch_name
        self._attr_device_class = device_class
        self._initial_state = initial_state
        self._attr_unique_id = f"{unique_id}_{switch_name}"
        apply_surface(self, window_surface("switch", switch_name))
        self._device_id = unique_id
        self._attr_device_info = adaptive_cover_device_info(config_entry)

        self.coordinator.logger.debug("Setup switch")

    def _layered_setting(self) -> str | None:
        """Return the toggle setting once the window acts on the layers, else None."""
        if self._setting is None or not is_layered(self.hass, self._config_entry):
            return None
        return self._setting

    @property
    def is_on(self) -> bool | None:
        """The value the window acts on (the switch's own state before the lift)."""
        if (setting := self._layered_setting()) is not None:
            return bool(self.coordinator.options.get(setting))
        return self._attr_is_on

    async def _set(self, on: bool) -> None:
        self.coordinator.logger.debug("Turning %s %s", self._switch_name, on)
        if (setting := self._layered_setting()) is not None:
            async_write_window(self.hass, self._config_entry, {setting: on})
            await self.coordinator.async_settings_changed()
        else:
            # Before the lift the switch is the setting: its state is what
            # the window reads (shadow.read_toggles).
            self._attr_is_on = on
            self.async_write_ha_state()
            await self.coordinator.async_refresh()
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on (for this window)."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off (for this window)."""
        await self._set(False)

    async def async_added_to_hass(self) -> None:
        """Follow the coordinator; before the lift, restore the switch's state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        self._attr_is_on = (
            last_state.state == STATE_ON
            if last_state is not None
            else self._initial_state
        )


class ControlAliasSwitch(AdaptiveCoverSwitch):
    """Toggle Control: a hidden alias of the window's Mode (P5 flip).

    On is automatic control (Mode auto or hold), off is Mode off. Turning
    it on works as it always did: control comes back on and the target
    position goes out now to every cover that is not held. Turning it off
    is Mode off (every hold ends). Its state follows the Mode select; it
    does not restore itself.
    """

    @property
    def is_on(self) -> bool | None:
        """Automatic control (unknown until the Mode select restores)."""
        return self.coordinator.control_toggle

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Automatic control on (Mode auto; holds are kept)."""
        await self.coordinator.modes.enable()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Mode off."""
        await self.coordinator.modes.off()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Follow the coordinator; the Mode select restores the state."""
        await super(AdaptiveCoverSwitch, self).async_added_to_hass()
