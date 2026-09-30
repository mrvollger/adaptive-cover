"""The Adaptive Cover integration.

One config entry, the house (the hub entry, 3.x), holds every window as a
config subentry of type ``window`` (ADR 0001; windows.py, house.py). A
fresh install creates it with its first window.

Window config entries from 1.x, and a house that still has them, do not
run: they must be consolidated on v2.0.x first (upgrade.py). A house
consolidated on v2.0.x (2.1) migrates to 3.1 at its first start, and a
3.1 house to 3.2 (one Climate switch).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_platform_entity_service
from homeassistant.helpers.typing import UNDEFINED, VolDictType

from .const import CONF_COVER_ENTITY, CONF_ENTITIES, DOMAIN
from .coordinator import AdaptiveDataUpdateCoordinator
from .window_cover import (
    ERROR_ONE_COVER,
    cover_problem,
    cover_registry_id,
    window_using_cover,
)
from .windows import (
    WindowEntry,
    all_windows,
    async_update_window,
    find_window,
    house_entry,
)

# The house entry carries the house's entities (the aggregate cover, the
# house Mode, Return all, the house settings: house_settings.py) and its
# window subentries' entities (house.py).
HUB_PLATFORMS = [
    Platform.COVER,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.TIME,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

SERVICE_GET_FORECAST = "get_forecast"
SERVICE_CHANGE_SETTINGS = "change_settings"
SERVICE_HOLD = "hold"
SERVICE_SET_PROFILE = "set_profile"
GET_FORECAST_SCHEMA = vol.Schema({vol.Required("config_entry"): str})
# adaptive_cover.hold: an entity service on the Mode selects (and the house
# select), so it targets entities, areas and floors (P5 flip).
HOLD_SCHEMA: VolDictType = {
    vol.Optional("duration"): vol.All(cv.time_period, cv.positive_timedelta),
    vol.Optional("position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
}


def _window_coordinator(
    hass: HomeAssistant, window: WindowEntry
) -> AdaptiveDataUpdateCoordinator | None:
    """Return the coordinator of a running window, or None."""
    from .house import window_coordinator

    return window_coordinator(hass, window.window_key)


def _resolve_entry(hass: HomeAssistant, reference: str) -> WindowEntry:
    """Find a window by its key, or a running one by title or name.

    The services' ``config_entry`` field names a window: its key is what a
    window entry's entry_id always was, before and after consolidation.
    """
    if (window := find_window(hass, reference)) is not None:
        return window
    for candidate in all_windows(hass):
        if _window_coordinator(hass, candidate) is not None and reference in (
            candidate.title,
            candidate.name,
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
        coordinator = _window_coordinator(hass, entry)
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
        set_profile_schema,
    )

    # Climate thresholds are validated in HA's temperature unit.
    temperature_unit = hass.config.units.temperature_unit

    async def handle_change_settings(call: ServiceCall) -> ServiceResponse:
        from .layers import window_record_after

        entry = _resolve_entry(hass, call.data["config_entry"])
        changes = {k: v for k, v in call.data.items() if k != "config_entry"}
        if not changes:
            raise ServiceValidationError("No settings provided to change")
        # "name" names the window (its title, device and log prefix).
        new_name = changes.pop("name", None)
        # One-time settings go to the geometry, recurring ones to the
        # window's overrides (sparse; layers.py). The house's update
        # listener rebuilds the window, or re-reads only its overrides.
        record = window_record_after(hass, entry, changes)
        if new_name:
            record = record.with_changes(name=new_name)
        moved = CONF_COVER_ENTITY in changes or CONF_ENTITIES in changes
        async_update_window(
            hass,
            entry,
            record,
            title=new_name or UNDEFINED,
            unique_id=cover_registry_id(hass, record.cover) if moved else UNDEFINED,
        )
        changed = sorted([*changes, *(["name"] if new_name else [])])
        return cast(ServiceResponse, {"entry": entry.title, "changed": changed})

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHANGE_SETTINGS,
        handle_change_settings,
        schema=change_settings_schema(temperature_unit),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle_add_entry(call: ServiceCall) -> ServiceResponse:
        """Add a window to the house without the form, optionally from a template.

        ``entry_id`` in the response is the new window's key.
        """
        from .config_flow import async_add_window_subentry
        from .layers import copied_options, new_window_values

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
            # What the source acts on: its resolved settings.
            options = copied_options(hass, source)
            sensor_type = call.data.get("sensor_type", source.cover_type)
        else:
            # The house's settings over the baseline: a new window inherits.
            options = {**add_entry_baseline(), **new_window_values(hass)}
            sensor_type = call.data.get("sensor_type", "cover_blind")
        options.update(overrides)
        options[CONF_ENTITIES] = covers
        options[CONF_COVER_ENTITY] = covers[0]
        house = house_entry(hass)
        if house is None:
            raise ServiceValidationError("There is no Adaptive Cover house")
        window = async_add_window_subentry(hass, house, name, sensor_type, options)
        return {"entry_id": window.window_key, "title": window.title}

    hass.services.async_register(
        DOMAIN,
        "add_entry",
        handle_add_entry,
        schema=add_entry_schema(temperature_unit),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle_set_profile(call: ServiceCall) -> ServiceResponse:
        """Store house, floor or area settings; every window acts on them."""
        from .layers import ProfileError, async_set_profile, async_settings_changed
        from .settings.spec import Level

        scope = call.data["scope"]
        scope_id = call.data.get("id")
        changes = {k: v for k, v in call.data.items() if k not in ("scope", "id")}
        if not changes:
            raise ServiceValidationError("No settings provided to set")
        try:
            changed = async_set_profile(hass, Level(scope), scope_id, changes)
        except ProfileError as err:
            raise ServiceValidationError(str(err)) from err
        if changed:
            await async_settings_changed(hass)
        response: dict[str, Any] = {"scope": scope, "id": scope_id, "changed": changed}
        return cast(ServiceResponse, response)

    from .settings.shadow import SHADOW_SPEC

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PROFILE,
        handle_set_profile,
        schema=set_profile_schema(SHADOW_SPEC, temperature_unit),
        supports_response=SupportsResponse.OPTIONAL,
    )
    from .profile_service import async_register_get_profile

    async_register_get_profile(hass)

    # hold(duration?, position?) on a window's Mode select (area and floor
    # targets resolve to those), or on the house select (every window).
    async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_HOLD,
        entity_domain=Platform.SELECT,
        schema=HOLD_SCHEMA,
        func="async_hold",
    )


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a config entry to the current version (upgrade.py).

    A house consolidated on v2.0.x (2.1) becomes 3.1: its window
    subentries store only what they use, the switch aliases go and the
    house options keep only the layers. A 3.1 house becomes 3.2: one
    Climate switch (``climate_mode`` goes; a window it was off for
    ignores climate control). Window entries (1.x), a 1.x house
    and a house that still has window entries are left as they are (their
    setup then fails with the ``consolidate_first`` message; v2.0.x
    consolidates them). A newer MAJOR version is refused by Home Assistant
    before this runs; a newer minor loads as is.
    """
    from .upgrade import async_migrate

    return await async_migrate(hass, entry)


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve and register the bundled Lovelace card (once)."""
    if not hass.data.get(f"{DOMAIN}_card_registered"):
        hass.data[f"{DOMAIN}_card_registered"] = True
        from homeassistant.loader import async_get_integration

        from .frontend import async_register_card

        integration = await async_get_integration(hass, DOMAIN)
        hass.async_create_task(async_register_card(hass, str(integration.version)))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the house (a window entry, or a house not at 3.x, refuses).

    Raises
    ------
    ConfigEntryError
        A window entry, or a house that still has window entries
        (``consolidate_first``: consolidate on v2.0.x first), or a house
        whose migration to 3.1 was refused (``house_not_migrated``).

    """
    from .hub import is_hub_entry
    from .upgrade import (
        async_check_consolidate_issue,
        consolidate_first_error,
        is_current_house,
    )

    if not is_hub_entry(entry):
        async_check_consolidate_issue(hass)
        raise consolidate_first_error(hass)
    if not is_current_house(entry):
        if async_check_consolidate_issue(hass):
            raise consolidate_first_error(hass)
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="house_not_migrated",
            translation_placeholders={
                "version": f"{entry.version}.{entry.minor_version}"
            },
        )
    return await _async_setup_house(hass, entry)


async def _async_setup_house(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the house: its settings entities and its window subentries."""
    from .house import HouseRuntime
    from .upgrade import async_check_consolidate_issue

    runtime = HouseRuntime(hass, entry)
    entry.runtime_data = runtime
    # Each window subentry sets up in isolation (a failing one gets a
    # repair issue); its entities come with the platforms below.
    await runtime.async_start()
    _async_register_services(hass)
    await _async_register_card(hass)
    await hass.config_entries.async_forward_entry_setups(entry, HUB_PLATFORMS)
    # The window devices exist now: each gets its cover's area unless the
    # user chose one.
    runtime.async_copy_areas()
    entry.async_on_unload(entry.add_update_listener(_async_house_update_listener))
    # A window entry enabled again later cannot run: say so.
    async_check_consolidate_issue(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the house (a window entry never loads)."""
    from .house import house_runtime
    from .hub import is_hub_entry

    if not is_hub_entry(entry):
        return True
    unload_ok = await hass.config_entries.async_unload_platforms(entry, HUB_PLATFORMS)
    if unload_ok and (runtime := house_runtime(entry)) is not None:
        await runtime.async_unload()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear the ``consolidate_first`` issue once no window entry is left."""
    from .upgrade import async_check_consolidate_issue

    async_check_consolidate_issue(hass)


async def _async_house_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Bring the house's running windows in line with its subentries.

    A new subentry starts, a removed one stops, a changed one is rebuilt
    alone (house.HouseRuntime.async_sync). The house's own options (the
    profiles) are acted on where they are written.
    """
    from .house import house_runtime

    if (runtime := house_runtime(entry)) is not None:
        await runtime.async_sync()
