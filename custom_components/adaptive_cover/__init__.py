"""The Adaptive Cover integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
from .settings.normalize import normalize_cover
from .window_cover import ERROR_ONE_COVER, cover_problem, window_using_cover

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
        is_hub_entry(entry) for entry in hass.config_entries.async_entries(DOMAIN)
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


def _window_coordinator(entry: ConfigEntry) -> AdaptiveDataUpdateCoordinator | None:
    """Return the coordinator of a loaded window entry, or None.

    HA drops ``runtime_data`` when the entry unloads; the hub entry never
    has one.
    """
    coordinator = getattr(entry, "runtime_data", None)
    if isinstance(coordinator, AdaptiveDataUpdateCoordinator):
        return coordinator
    return None


def _resolve_entry(hass: HomeAssistant, reference: str) -> ConfigEntry:
    """Find a config entry by entry_id, or a loaded window by title or name."""
    entry = hass.config_entries.async_get_entry(reference)
    if entry and entry.domain == DOMAIN:
        return entry
    for candidate in hass.config_entries.async_entries(DOMAIN):
        if _window_coordinator(candidate) is not None and reference in (
            candidate.title,
            candidate.data.get("name"),
        ):
            return candidate
    raise ServiceValidationError(f"No Adaptive Cover config entry '{reference}'")


def _requested_covers(data: Mapping[str, Any]) -> list[str]:
    """Return the add_entry call's covers: ``cover``, or the older ``covers``."""
    if "cover" in data and "covers" in data:
        raise ServiceValidationError(
            "add_entry takes cover (one entity) or covers (a list), not both"
        )
    if "cover" in data:
        return [data["cover"]]
    covers = list(data.get("covers") or [])
    if not covers:
        raise ServiceValidationError("add_entry needs the window's cover (cover)")
    return covers


def _cover_problem_message(hass: HomeAssistant, problem: str, covers: list[str]) -> str:
    """Explain why add_entry refused ``covers``."""
    if problem == ERROR_ONE_COVER:
        return (
            f"A window drives exactly one cover; got {len(covers)} "
            f"({', '.join(covers)}). Call add_entry once per cover."
        )
    owner = window_using_cover(hass, covers[0])
    title = owner.title if owner is not None else "another window"
    return f"{covers[0]} is already driven by the window '{title}'"


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_FORECAST):
        return

    async def handle_get_forecast(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data["config_entry"])
        coordinator = _window_coordinator(entry)
        if coordinator is None:
            raise ServiceValidationError(f"Entry '{entry.title}' is not loaded")
        forecast: list[Any] = coordinator.forecast or []  # JSON-shaped entries
        return {"forecast": forecast}

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FORECAST,
        handle_get_forecast,
        schema=GET_FORECAST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    from .settings.schema import (
        add_entry_baseline,
        add_entry_schema,
        change_settings_schema,
    )

    # Climate thresholds are validated in HA's temperature unit.
    temperature_unit = hass.config.units.temperature_unit

    async def handle_change_settings(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data["config_entry"])
        changes = {k: v for k, v in call.data.items() if k != "config_entry"}
        if not changes:
            raise ServiceValidationError("No settings provided to change")
        # "name" lives in entry data (drives title, device name, and log
        # prefix), not options - handle it separately so entries can be
        # renamed without recreating them.
        new_name = changes.pop("name", None)
        update_kwargs: dict = {}
        if new_name:
            update_kwargs["data"] = {**entry.data, "name": new_name}
            update_kwargs["title"] = new_name
        if changes:
            update_kwargs["options"] = {**entry.options, **changes}
        hass.config_entries.async_update_entry(entry, **update_kwargs)
        if new_name and not changes:
            # Options updates reload via the update listener; a pure rename
            # must reload explicitly so entities and device pick up the name.
            await hass.config_entries.async_reload(entry.entry_id)
        changed = sorted([*changes, *(["name"] if new_name else [])])
        return {"entry": entry.title, "changed": changed}

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHANGE_SETTINGS,
        handle_change_settings,
        schema=change_settings_schema(temperature_unit),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle_add_entry(call: ServiceCall) -> ServiceResponse:
        """Create a new entry without the wizard, optionally from a template."""
        from homeassistant.config_entries import SOURCE_IMPORT

        name = call.data["name"]
        covers = _requested_covers(call.data)
        if problem := cover_problem(hass, covers):
            raise ServiceValidationError(_cover_problem_message(hass, problem, covers))
        overrides = {
            key: value
            for key, value in call.data.items()
            if key not in ("name", "cover", "covers", "copy_from", "sensor_type")
        }
        if copy_from := call.data.get("copy_from"):
            source = _resolve_entry(hass, copy_from)
            options = dict(source.options)
            sensor_type = call.data.get(
                "sensor_type", source.data.get("sensor_type", "cover_blind")
            )
        else:
            options = add_entry_baseline()
            sensor_type = call.data.get("sensor_type", "cover_blind")
        options.update(overrides)
        options[CONF_ENTITIES] = covers
        options = normalize_cover(options)

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
        schema=add_entry_schema(temperature_unit),
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_initialize_integration(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None = None,
) -> bool:
    """Initialize the integration."""

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a config entry to the current schema version.

    1.1 -> 1.2 (P1): apply the entity surface (categories and disabled
    defaults) to the entry's existing registry rows; new rows get it from
    the entity classes. User choices are kept (see entity_surface).

    1.2 -> 1.3 (P3): write the options' fallback values, the cover as
    cover_entity_id, and the cover's registry id as unique_id (see
    migration.py). The hub only gets the version bump.

    A newer MINOR version (after a downgrade) loads as is. A newer MAJOR
    version is refused.
    """
    from .const import CONFIG_ENTRY_VERSION
    from .entity_surface import async_apply_surface_to_registry

    if entry.version > CONFIG_ENTRY_VERSION:
        _LOGGER.error(
            "Cannot load %s: config entry version %s.%s is newer than this "
            "integration supports",
            entry.title,
            entry.version,
            entry.minor_version,
        )
        return False
    if entry.minor_version < 2:
        updated = async_apply_surface_to_registry(hass, entry)
        _LOGGER.debug(
            "Migrated %s to 1.2: %s registry rows updated", entry.title, updated
        )
        hass.config_entries.async_update_entry(entry, minor_version=2)
    if entry.minor_version < 3:
        from .hub import is_hub_entry
        from .migration import async_migrate_1_3

        if is_hub_entry(entry):
            hass.config_entries.async_update_entry(entry, minor_version=3)
        else:
            async_migrate_1_3(hass, entry)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Adaptive Cover from a config entry."""
    from .hub import is_hub_entry

    hass.data.setdefault(DOMAIN, {})

    if is_hub_entry(entry):
        await hass.config_entries.async_forward_entry_setups(entry, HUB_PLATFORMS)
        return True

    # One cover per window (ADR 0002): the unique_id follows the cover, and
    # an entry from before P3 with several covers gets a "split" issue.
    from .migration import async_sync_unique_id
    from .window_cover import async_check_split_issue

    async_sync_unique_id(hass, entry)
    async_check_split_issue(hass, entry)

    # Prime the timezone cache off-loop: the first construction reads a
    # zoneinfo file, and schedule math needs it inside the loop.
    from .coordinator import cached_timezone

    await hass.async_add_executor_job(cached_timezone, hass.config.time_zone)

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
    entry.runtime_data = coordinator
    # Index of the loaded windows' coordinators, for the hub and the Mode
    # select, which still look them up here (P4 moves them next).
    hass.data[DOMAIN][entry.entry_id] = coordinator
    _async_register_services(hass)
    hass.async_create_task(_async_bootstrap_hub(hass))

    if not hass.data.get(f"{DOMAIN}_card_registered"):
        hass.data[f"{DOMAIN}_card_registered"] = True
        from homeassistant.loader import async_get_integration

        from .frontend import async_register_card

        integration = await async_get_integration(hass, DOMAIN)
        hass.async_create_task(async_register_card(hass, str(integration.version)))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # The window device exists now (the platforms created it): give it the
    # physical cover's area unless the user already chose one.
    from .entity_surface import async_copy_cover_area

    async_copy_cover_area(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .hub import is_hub_entry

    if is_hub_entry(entry):
        return await hass.config_entries.async_unload_platforms(entry, HUB_PLATFORMS)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop a removed window's split issue, if it had one."""
    from homeassistant.helpers import issue_registry as ir

    from .window_cover import split_issue_id

    ir.async_delete_issue(hass, DOMAIN, split_issue_id(entry.entry_id))


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
