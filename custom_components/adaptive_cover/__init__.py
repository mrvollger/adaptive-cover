"""The Adaptive Cover integration.

Two config models run side by side until the owner consolidates (P7,
ADR 0001; the legacy one goes in P8):

- **legacy**: each window is its own config entry (1.x), plus the hub
  entry ("All shades") with the house settings;
- **house**: the hub entry is the house (2.x) and each window is one of
  its config subentries (windows.py, house.py). A fresh install starts
  here; an existing house moves here when the owner fixes the
  "Consolidate" repair issue (consolidate.py).
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
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_platform_entity_service
from homeassistant.helpers.typing import VolDictType

from .const import (
    CONF_ENTITIES,
    DOMAIN,
    HOUSE_ENTRY_VERSION,
    _LOGGER,
)
from .coordinator import AdaptiveDataUpdateCoordinator
from .settings.normalize import normalize_cover
from .window_cover import ERROR_ONE_COVER, cover_problem, window_using_cover
from .windows import (
    WindowEntry,
    all_windows,
    as_window,
    async_update_window,
    find_window,
    house_entry,
    uses_subentries,
)

PLATFORMS = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
]
# The hub also carries the house settings (P5 flip: house_settings.py) and,
# as the house entry, its window subentries' entities (P7: house.py).
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
CONF_SUN = ["sun.sun"]


def _hub_entry_exists(hass: HomeAssistant) -> bool:
    return house_entry(hass) is not None


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
    """Return the coordinator of a loaded window, or None."""
    coordinator = hass.data.get(DOMAIN, {}).get(window.window_key)
    if isinstance(coordinator, AdaptiveDataUpdateCoordinator):
        return coordinator
    return None


def _resolve_entry(hass: HomeAssistant, reference: str) -> WindowEntry:
    """Find a window by its key (a window entry's entry_id), or a loaded one by title or name.

    The services' ``config_entry`` field names a window: its key is what a
    window entry's entry_id always was, before and after consolidation.
    """
    if (window := find_window(hass, reference)) is not None:
        return window
    for candidate in all_windows(hass):
        if _window_coordinator(hass, candidate) is not None and reference in (
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
        from .layers import window_options_after

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
            # P5 flip: one-time settings go to the options, recurring ones
            # to the window's overrides (sparse; layers.py).
            update_kwargs["options"] = window_options_after(hass, entry, changes)
        async_update_window(hass, entry, **update_kwargs)
        if new_name and not changes and not entry.is_subentry:
            # Options updates reload via the update listener; a pure rename
            # must reload explicitly so entities and device pick up the name.
            # (A window subentry's rename rebuilds it: house.async_sync.)
            await hass.config_entries.async_reload(entry.config_entry.entry_id)
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
        """Add a window without the form, optionally from a template.

        A window of the house (a subentry) once the house uses them
        (windows.uses_subentries); a window entry before. ``entry_id`` in
        the response is the window key either way.
        """
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
        from .layers import copied_options, new_window_values

        if copy_from := call.data.get("copy_from"):
            source = _resolve_entry(hass, copy_from)
            # What the source acts on (P5 flip: its resolved settings).
            options = copied_options(hass, source)
            sensor_type = call.data.get(
                "sensor_type", source.data.get("sensor_type", "cover_blind")
            )
        else:
            # The house's settings over the baseline: a new window inherits.
            options = {**add_entry_baseline(), **new_window_values(hass)}
            sensor_type = call.data.get("sensor_type", "cover_blind")
        options.update(overrides)
        options[CONF_ENTITIES] = covers
        options = normalize_cover(options)

        if uses_subentries(hass):
            from .config_flow import async_add_window_subentry

            house = house_entry(hass)
            assert house is not None  # uses_subentries
            window = async_add_window_subentry(
                hass, house, {"name": name, "sensor_type": sensor_type}, options
            )
            return {"entry_id": window.window_key, "title": window.title}

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

    1.3 -> 1.4 (P5 shadow): the hub lifts every enabled window into house,
    floor and area profiles in its options and writes each window's sparse
    ``overrides``, recording the states of the switches P5 drops (see
    shadow.py). Windows only get the version bump; their legacy keys stay.

    1.4 -> 1.5 (P5 flip): the window's six switches become hidden aliases
    (hidden_by integration, still enabled) of the Mode select and the
    house toggles, unless the user already chose their visibility (see
    entity_surface). The hub only gets the version bump. The Mode select
    needs no migration: on its first boot it restores from the Toggle
    Control switch's last state (select.py).

    2.x (P7): the house entry with window subentries (consolidated, or a
    fresh install). The flow's version is 2, so Home Assistant asks to
    migrate every 1.x entry at each start: window entries and a legacy hub
    stay at 1.x (they only get the minor steps above), so a downgrade
    before consolidation keeps working. Only consolidation moves the hub
    to 2.x (consolidate.py).

    A newer MINOR version (after a downgrade) loads as is. A newer MAJOR
    version is refused (Home Assistant does that before calling this).
    """
    from .const import CONFIG_ENTRY_VERSION
    from .entity_surface import async_apply_surface_to_registry
    from .hub import is_hub_entry

    if entry.version >= HOUSE_ENTRY_VERSION:
        if is_hub_entry(entry):
            return True  # a house at an older 2.x minor: nothing to migrate yet
        _LOGGER.error(
            "Cannot load %s: a window entry at version %s.%s (windows are 1.x "
            "entries or subentries of the house)",
            entry.title,
            entry.version,
            entry.minor_version,
        )
        return False
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
        from .migration import async_migrate_1_3

        if is_hub_entry(entry):
            hass.config_entries.async_update_entry(entry, minor_version=3)
        else:
            async_migrate_1_3(hass, entry)
    if entry.minor_version < 4:
        from .shadow import async_migrate_hub_1_4

        if is_hub_entry(entry):
            async_migrate_hub_1_4(hass, entry)
        else:
            hass.config_entries.async_update_entry(entry, minor_version=4)
    if entry.minor_version < 5:
        updated = async_apply_surface_to_registry(hass, entry)
        _LOGGER.debug(
            "Migrated %s to 1.5: %s registry rows updated (switch aliases hidden)",
            entry.title,
            updated,
        )
        hass.config_entries.async_update_entry(entry, minor_version=5)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve and register the bundled Lovelace card (once)."""
    if not hass.data.get(f"{DOMAIN}_card_registered"):
        hass.data[f"{DOMAIN}_card_registered"] = True
        from homeassistant.loader import async_get_integration

        from .frontend import async_register_card

        integration = await async_get_integration(hass, DOMAIN)
        hass.async_create_task(async_register_card(hass, str(integration.version)))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Adaptive Cover from a config entry (the house, or a legacy window)."""
    from .consolidate import async_check_consolidate_issue
    from .hub import is_hub_entry

    hass.data.setdefault(DOMAIN, {})

    if is_hub_entry(entry):
        return await _async_setup_house(hass, entry)

    # One cover per window (ADR 0002): the unique_id follows the cover, and
    # an entry from before P3 with several covers gets a "split" issue.
    from .migration import async_sync_unique_id
    from .window_cover import async_check_split_issue

    async_sync_unique_id(hass, entry)
    async_check_split_issue(hass, entry)
    # P5 flip: the window numbers are house settings and layered edits now.
    from .entity_surface import async_remove_window_numbers

    async_remove_window_numbers(hass, entry)

    from .house import async_build_window

    coordinator, unsubs = await async_build_window(hass, as_window(entry))
    for unsub in unsubs:
        entry.async_on_unload(unsub)
    entry.runtime_data = coordinator
    _async_register_services(hass)
    hass.async_create_task(_async_bootstrap_hub(hass))
    await _async_register_card(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # The window device exists now (the platforms created it): give it the
    # physical cover's area unless the user already chose one.
    from .entity_surface import async_copy_cover_area

    async_copy_cover_area(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # A house with legacy windows is offered the move to subentries (P7).
    async_check_consolidate_issue(hass)
    return True


async def _async_setup_house(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the house: its settings entities and its window subentries."""
    from .consolidate import async_check_consolidate_issue
    from .house import HouseRuntime

    # A house that was never lifted (a hub created at 1.4 or later)
    # lifts itself; its windows act on the same values afterwards.
    from .shadow import async_ensure_lifted

    async_ensure_lifted(hass)
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
    async_check_consolidate_issue(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .house import async_forget_window, house_runtime
    from .hub import is_hub_entry

    if is_hub_entry(entry):
        unload_ok = await hass.config_entries.async_unload_platforms(
            entry, HUB_PLATFORMS
        )
        if unload_ok and (runtime := house_runtime(entry)) is not None:
            await runtime.async_unload()
        return unload_ok
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        async_forget_window(hass, entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop a removed window's repair issues (split; the retired settings differ)."""
    from homeassistant.helpers import issue_registry as ir

    from .consolidate import async_check_consolidate_issue
    from .shadow import diff_issue_id
    from .window_cover import split_issue_id

    ir.async_delete_issue(hass, DOMAIN, split_issue_id(entry.entry_id))
    ir.async_delete_issue(hass, DOMAIN, diff_issue_id(entry.entry_id))
    async_check_consolidate_issue(hass)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update.

    An update that only wrote the window's ``overrides`` (the lift, an
    adoption, a recurring edit) needs no reload: the window re-reads its
    settings on every refresh, so it acts on them now. Anything else (a
    one-time setting, the name) reloads the window.
    """
    from .layers import async_settings_changed
    from .shadow import only_overrides_changed

    if only_overrides_changed(hass, entry):
        await async_settings_changed(hass, [entry.entry_id])
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_house_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Bring the house's running windows in line with its subentries.

    A new subentry starts, a removed one stops, a changed one is rebuilt
    alone (house.HouseRuntime.async_sync). The house's own options (the
    profiles) are acted on where they are written.
    """
    from .house import house_runtime

    if (runtime := house_runtime(entry)) is not None:
        await runtime.async_sync()
