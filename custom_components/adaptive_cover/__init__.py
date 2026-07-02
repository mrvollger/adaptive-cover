"""The Adaptive Cover integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import (
    async_track_state_change_event,
)

from .const import (
    CONF_END_ENTITY,
    CONF_ENTITIES,
    CONF_PRESENCE_ENTITY,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    _LOGGER,
)
from .coordinator import AdaptiveDataUpdateCoordinator

PLATFORMS = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
]
HUB_PLATFORMS = [Platform.COVER, Platform.SELECT, Platform.BUTTON]
CONF_SUN = ["sun.sun"]


def _hub_entry_exists(hass: HomeAssistant) -> bool:
    from .hub import is_hub_entry

    return any(
        is_hub_entry(entry)
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


async def _async_bootstrap_hub(hass: HomeAssistant) -> None:
    """Create the singleton All Shades hub entry if it doesn't exist."""
    from homeassistant.config_entries import SOURCE_IMPORT

    if _hub_entry_exists(hass):
        return
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data={}
    )

SERVICE_GET_FORECAST = "get_forecast"
SERVICE_CHANGE_SETTINGS = "change_settings"
GET_FORECAST_SCHEMA = vol.Schema({vol.Required("config_entry"): str})


def _resolve_entry(hass: HomeAssistant, reference: str) -> ConfigEntry:
    """Find a config entry by entry_id, title, or internal name."""
    entry = hass.config_entries.async_get_entry(reference)
    if entry and entry.domain == DOMAIN:
        return entry
    for entry_id in hass.data.get(DOMAIN, {}):
        candidate = hass.config_entries.async_get_entry(entry_id)
        if candidate and reference in (
            candidate.title,
            candidate.data.get("name"),
        ):
            return candidate
    raise ServiceValidationError(f"No Adaptive Cover config entry '{reference}'")


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_FORECAST):
        return

    async def handle_get_forecast(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data["config_entry"])
        coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if coordinator is None:
            raise ServiceValidationError(
                f"Entry '{entry.title}' is not loaded"
            )
        return {"forecast": coordinator.forecast or []}

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FORECAST,
        handle_get_forecast,
        schema=GET_FORECAST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    from .options_spec import (
        DEFAULT_OPTIONS,
        add_entry_schema,
        change_settings_schema,
    )

    async def handle_change_settings(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data["config_entry"])
        changes = {k: v for k, v in call.data.items() if k != "config_entry"}
        if not changes:
            raise ServiceValidationError("No settings provided to change")
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, **changes}
        )
        return {"entry": entry.title, "changed": sorted(changes)}

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHANGE_SETTINGS,
        handle_change_settings,
        schema=change_settings_schema(),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle_add_entry(call: ServiceCall) -> ServiceResponse:
        """Create a new entry without the wizard, optionally from a template."""
        from homeassistant.config_entries import SOURCE_IMPORT

        name = call.data["name"]
        covers = call.data["covers"]
        overrides = {
            key: value
            for key, value in call.data.items()
            if key not in ("name", "covers", "copy_from", "sensor_type")
        }
        if copy_from := call.data.get("copy_from"):
            source = _resolve_entry(hass, copy_from)
            options = dict(source.options)
            sensor_type = call.data.get(
                "sensor_type", source.data.get("sensor_type", "cover_blind")
            )
        else:
            options = dict(DEFAULT_OPTIONS)
            sensor_type = call.data.get("sensor_type", "cover_blind")
        options.update(overrides)
        options[CONF_ENTITIES] = covers

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={"name": name, "sensor_type": sensor_type, "options": options},
        )
        entry = result.get("result")
        if entry is None:
            raise ServiceValidationError(
                f"Entry creation failed: {result.get('reason', 'unknown')}"
            )
        return {"entry_id": entry.entry_id, "title": entry.title}

    hass.services.async_register(
        DOMAIN,
        "add_entry",
        handle_add_entry,
        schema=add_entry_schema(),
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_initialize_integration(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None = None,
) -> bool:
    """Initialize the integration."""

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Adaptive Cover from a config entry."""
    from .hub import is_hub_entry

    hass.data.setdefault(DOMAIN, {})

    if is_hub_entry(entry):
        await hass.config_entries.async_forward_entry_setups(entry, HUB_PLATFORMS)
        return True

    coordinator = AdaptiveDataUpdateCoordinator(hass)
    _temp_entity = entry.options.get(CONF_TEMP_ENTITY)
    _presence_entity = entry.options.get(CONF_PRESENCE_ENTITY)
    _weather_entity = entry.options.get(CONF_WEATHER_ENTITY)
    _cover_entities = entry.options.get(CONF_ENTITIES, [])
    _end_time_entity = entry.options.get(CONF_END_ENTITY)
    _entities = ["sun.sun"]
    for entity in [_temp_entity, _presence_entity, _weather_entity, _end_time_entity]:
        if entity is not None:
            _entities.append(entity)

    _LOGGER.debug("Setting up entry %s", entry.data.get("name"))

    entry.async_on_unload(
        async_track_state_change_event(
            hass,
            _entities,
            coordinator.async_check_entity_state_change,
        )
    )

    entry.async_on_unload(
        async_track_state_change_event(
            hass,
            _cover_entities,
            coordinator.async_check_cover_state_change,
        )
    )

    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    _async_register_services(hass)
    hass.async_create_task(_async_bootstrap_hub(hass))

    if not hass.data.get(f"{DOMAIN}_card_registered"):
        hass.data[f"{DOMAIN}_card_registered"] = True
        from homeassistant.loader import async_get_integration

        from .frontend import async_register_card

        integration = await async_get_integration(hass, DOMAIN)
        hass.async_create_task(
            async_register_card(hass, str(integration.version))
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .hub import is_hub_entry

    if is_hub_entry(entry):
        return await hass.config_entries.async_unload_platforms(
            entry, HUB_PLATFORMS
        )
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
