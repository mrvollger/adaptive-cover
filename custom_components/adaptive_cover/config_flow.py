"""Config flow for Adaptive Cover integration.

The wizard pages and the options form come from the option spec
(settings/spec.py, built by settings/schema.py); this module routes
between pages and runs the cross-field checks (settings/validate.py).
"""

from __future__ import annotations

import copy
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import selector

from .const import (
    _LOGGER,
    CONF_CLIMATE_MODE,
    CONF_ENABLE_BLIND_SPOT,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_INTERP,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MODE,
    CONF_SENSOR_TYPE,
    CONF_TRANSPARENT_BLIND,
    CONF_WEATHER_ENTITY,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SensorType,
)
from .settings.schema import (
    CLEARABLE_KEYS,
    WIZARD_OPTION_KEYS,
    options_section_fields,
    wizard_schema,
    wizard_type_schema,
)
from .settings.spec import OPTS_BY_KEY
from .settings.validate import blind_spot_order, elevation_order, interp_lengths

SENSOR_TYPE_MENU = [SensorType.BLIND, SensorType.AWNING, SensorType.TILT]

# The wizard page that collects each cover type's geometry.
TYPE_STEPS = {
    SensorType.BLIND: "vertical",
    SensorType.AWNING: "horizontal",
    SensorType.TILT: "tilt",
}

# First wizard page: the entry's identity (entry data, not options).
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required("name"): selector.TextSelector(),
        vol.Optional(CONF_MODE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=SENSOR_TYPE_MENU, translation_key="mode"
            )
        ),
    }
)

# Options the wizard fills with their default when their page did not run.
_WIZARD_FILLED_DEFAULTS = (
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_TRANSPARENT_BLIND,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
)


def _temperature_unit(hass: HomeAssistant) -> str:
    """HA's temperature unit: climate thresholds are stored in it."""
    return hass.config.units.temperature_unit


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle ConfigFlow."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    def __init__(self) -> None:  # noqa: D107
        super().__init__()
        self.type_blind: str | None = None
        self.config: dict[str, Any] = {}
        self.mode: str = "basic"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_import(self, import_data: dict[str, Any] | None = None):
        """Programmatic entry creation.

        Two shapes: {} bootstraps the singleton hub; {name, sensor_type,
        options} creates a regular entry (used by the add_entry service so
        new windows never require the wizard).
        """
        from .hub import CONF_IS_HUB, HUB_ENTRY_NAME, HUB_UNIQUE_ID

        if import_data and import_data.get("name") and not import_data.get(CONF_IS_HUB):
            return self.async_create_entry(
                title=import_data["name"],
                data={
                    "name": import_data["name"],
                    CONF_SENSOR_TYPE: import_data.get(
                        CONF_SENSOR_TYPE, SensorType.BLIND
                    ),
                },
                options=dict(import_data.get("options", {})),
            )

        await self.async_set_unique_id(HUB_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=HUB_ENTRY_NAME,
            data={"name": HUB_ENTRY_NAME, CONF_IS_HUB: True},
            options={},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        if user_input:
            self.config = user_input
            step = TYPE_STEPS.get(self.config[CONF_MODE])
            if step is not None:
                return await getattr(self, f"async_step_{step}")()
        return self.async_show_form(step_id="user", data_schema=CONFIG_SCHEMA)

    async def _async_step_cover_type(
        self, cover_type: str, user_input: dict[str, Any] | None
    ):
        """Show the cover-type page: geometry and sun behavior for one type."""
        self.type_blind = cover_type
        step_id = TYPE_STEPS[cover_type]
        schema = wizard_type_schema(cover_type, _temperature_unit(self.hass))
        if user_input is not None:
            if errors := elevation_order(user_input):
                return self.async_show_form(
                    step_id=step_id, data_schema=schema, errors=errors
                )
            self.config.update(user_input)
            if self.config[CONF_INTERP]:
                return await self.async_step_interp()
            if self.config[CONF_ENABLE_BLIND_SPOT]:
                return await self.async_step_blind_spot()
            return await self.async_step_automation()
        return self.async_show_form(step_id=step_id, data_schema=schema)

    async def async_step_vertical(self, user_input: dict[str, Any] | None = None):
        """Show basic config for vertical blinds."""
        return await self._async_step_cover_type(SensorType.BLIND, user_input)

    async def async_step_horizontal(self, user_input: dict[str, Any] | None = None):
        """Show basic config for horizontal blinds."""
        return await self._async_step_cover_type(SensorType.AWNING, user_input)

    async def async_step_tilt(self, user_input: dict[str, Any] | None = None):
        """Show basic config for tilted blinds."""
        return await self._async_step_cover_type(SensorType.TILT, user_input)

    async def async_step_interp(self, user_input: dict[str, Any] | None = None):
        """Show interpolation options."""
        schema = wizard_schema("interp")
        if user_input is not None:
            if errors := interp_lengths(user_input):
                return self.async_show_form(
                    step_id="interp", data_schema=schema, errors=errors
                )
            self.config.update(user_input)
            if self.config[CONF_ENABLE_BLIND_SPOT]:
                return await self.async_step_blind_spot()
            return await self.async_step_automation()
        return self.async_show_form(step_id="interp", data_schema=schema)

    async def async_step_blind_spot(self, user_input: dict[str, Any] | None = None):
        """Add blindspot to data."""
        schema = wizard_schema(
            "blind_spot",
            fov_span=self.config[CONF_FOV_LEFT] + self.config[CONF_FOV_RIGHT],
        )
        if user_input is not None:
            if errors := blind_spot_order(user_input):
                return self.async_show_form(
                    step_id="blind_spot", data_schema=schema, errors=errors
                )
            self.config.update(user_input)
            return await self.async_step_automation()
        return self.async_show_form(step_id="blind_spot", data_schema=schema)

    async def async_step_automation(self, user_input: dict[str, Any] | None = None):
        """Manage automation options."""
        if user_input is not None:
            self.config.update(user_input)
            if self.config[CONF_CLIMATE_MODE] is True:
                return await self.async_step_climate()
            return await self.async_step_update()
        return self.async_show_form(
            step_id="automation", data_schema=wizard_schema("automation")
        )

    async def async_step_climate(self, user_input: dict[str, Any] | None = None):
        """Manage climate options."""
        if user_input is not None:
            self.config.update(user_input)
            if self.config.get(CONF_WEATHER_ENTITY):
                return await self.async_step_weather()
            return await self.async_step_update()
        return self.async_show_form(
            step_id="climate",
            data_schema=wizard_schema(
                "climate", temperature_unit=_temperature_unit(self.hass)
            ),
        )

    async def async_step_weather(self, user_input: dict[str, Any] | None = None):
        """Manage weather conditions."""
        if user_input is not None:
            self.config.update(user_input)
            return await self.async_step_update()
        return self.async_show_form(
            step_id="weather", data_schema=wizard_schema("weather")
        )

    async def async_step_update(self, user_input: dict[str, Any] | None = None):
        """Create entry, persisting every option the wizard collected."""
        options = {key: self.config.get(key) for key in WIZARD_OPTION_KEYS}
        # CONF_MODE in self.config holds the sensor type picked on the first
        # page; in options it is the control mode ("basic").
        options[CONF_MODE] = self.mode
        # Defaults for keys whose collecting step may not have run.
        for key in _WIZARD_FILLED_DEFAULTS:
            options[key] = self.config.get(key, copy.deepcopy(OPTS_BY_KEY[key].default))
        return self.async_create_entry(
            title=self.config["name"],
            data={
                "name": self.config["name"],
                CONF_SENSOR_TYPE: self.type_blind,
            },
            options=options,
        )


class OptionsFlowHandler(OptionsFlow):
    """Single-page options flow.

    Every applicable setting on one form, grouped into collapsible
    sections, with current values pre-filled.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.current_config: dict = dict(config_entry.data)
        self.options = dict(config_entry.options)
        self.sensor_type: str = (
            self.current_config.get(CONF_SENSOR_TYPE) or SensorType.BLIND
        )
        self._shown_keys: set[str] = set()

    def _section_fields(self) -> dict[str, dict]:
        """Build {section_name: fields} for this entry's type and features."""
        return options_section_fields(
            self.sensor_type,
            climate_on=bool(self.options.get(CONF_CLIMATE_MODE)),
            options=self.options,
            temperature_unit=_temperature_unit(self.hass),
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show and process the single options page."""
        section_fields = self._section_fields()
        self._shown_keys = {
            marker.schema for fields in section_fields.values() for marker in fields
        }

        if user_input is not None:
            flat: dict = {}
            for section_data in user_input.values():
                if isinstance(section_data, dict):
                    flat.update(section_data)
            # Absent clearable fields were cleared by the user
            for key in CLEARABLE_KEYS & self._shown_keys:
                if key not in flat:
                    flat[key] = None
            if errors := elevation_order(flat):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_schema(section_fields),
                    errors={"base": next(iter(errors.values()))},
                )
            changed = {
                key: value
                for key, value in flat.items()
                if self.options.get(key) != value and value is not None
            }
            cleared = sorted(
                key
                for key, value in flat.items()
                if value is None and self.options.get(key) is not None
            )
            if changed or cleared:
                _LOGGER.info(
                    "Options updated for '%s': changed=%s cleared=%s",
                    self.current_config.get("name"),
                    sorted(changed),
                    cleared,
                )
            self.options.update(flat)
            return await self._update_options()

        return self.async_show_form(
            step_id="init", data_schema=self._build_schema(section_fields)
        )

    def _build_schema(self, section_fields: dict[str, dict]) -> vol.Schema:
        """Assemble the sectioned one-page schema."""
        return vol.Schema(
            {
                vol.Required(name): section(
                    vol.Schema(fields),
                    {"collapsed": name != "covers_geometry"},
                )
                for name, fields in section_fields.items()
            }
        )

    async def _update_options(self) -> FlowResult:
        """Update config entry options."""
        return self.async_create_entry(title="", data=self.options)
