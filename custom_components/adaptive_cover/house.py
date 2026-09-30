"""The house runtime: one coordinator per window subentry (ADR 0001).

The house entry (the hub, promoted) holds its windows as config subentries
of type ``window`` (windows.py). ``HouseRuntime`` is the house entry's
``runtime_data``:

- **Isolated windows.** Each window subentry gets its own coordinator,
  listeners and entities (``async_build_window``). A window that fails to
  set up gets a repair issue and a retry; the rest of the house keeps
  running.
- **Entities per window.** Each platform module hands the runtime a
  factory (``async_add_platform``); the runtime adds a window's entities
  with ``config_subentry_id`` set, so HA shows them under the window's
  subentry. The window device hangs off the house device (``via_device_id``).
- **Listener compares subentries** (``async_sync``, the house entry's
  update listener): a new subentry starts, a removed one stops, a changed
  one is rebuilt alone. A change that only wrote the window's sparse
  ``overrides`` rebuilds nothing: the window acts on it at once. A
  house-profile change (``set_profile``) touches no subentry:
  ``layers.async_settings_changed`` re-resolves every window in place.

The running windows' coordinators are found through the house entry's
``runtime_data`` (``window_coordinators``): the hub entities, the services
and ``layers`` use it. ``hass.data`` holds only the override store.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_platform
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import (
    _LOGGER,
    CONF_END_ENTITY,
    CONF_PRESENCE_ENTITY,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)
from .coordinator import AdaptiveDataUpdateCoordinator, cached_timezone
from .settings.window_record import OVERRIDES
from .windows import (
    WINDOW_SUBENTRY,
    WindowEntry,
    house_entry,
    subentry_window_key,
)

WindowFactory = Callable[
    [HomeAssistant, WindowEntry, AdaptiveDataUpdateCoordinator], list[Entity]
]
"""A platform's window entities (``<platform>.window_entities``)."""

WINDOW_FAILED_ISSUE: Final = "window_setup_failed"
RETRY_SECONDS: Final = 60
"""A failed window tries again after this long (and at every house change)."""


def window_failed_issue_id(window_key: str) -> str:
    """Return the repair issue id of a window that failed to set up."""
    return f"{WINDOW_FAILED_ISSUE}_{window_key}"


@callback
def async_window_failed_issue(
    hass: HomeAssistant, window_key: str, title: str, error: str
) -> None:
    """Raise the repair issue of a window subentry that failed to set up."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        window_failed_issue_id(window_key),
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=WINDOW_FAILED_ISSUE,
        translation_placeholders={"window": title, "error": error},
    )


# ------------------------------------------------------------ one window


async def async_build_window(
    hass: HomeAssistant, window: WindowEntry
) -> tuple[AdaptiveDataUpdateCoordinator, list[CALLBACK_TYPE]]:
    """Build one window's coordinator and listeners, and run its first refresh.

    The window acts on its resolved layered settings (layers.py). Returns
    the coordinator and the listeners to cancel on unload; on a failed
    first refresh everything is undone and ``ConfigEntryNotReady`` is
    raised.
    """
    # Prime the timezone cache off-loop: the first construction reads a
    # zoneinfo file, and schedule math needs it inside the loop.
    await hass.async_add_executor_job(cached_timezone, hass.config.time_zone)

    coordinator = AdaptiveDataUpdateCoordinator(hass, window=window)
    settings = coordinator.options
    watched = ["sun.sun"]
    for key in (CONF_TEMP_ENTITY, CONF_PRESENCE_ENTITY, CONF_WEATHER_ENTITY):
        if (entity := settings.get(key)) is not None:
            watched.append(entity)
    if (end_entity := settings.get(CONF_END_ENTITY)) is not None:
        watched.append(end_entity)
    covers = window.covers

    _LOGGER.debug("Setting up window %s", window.name)
    unsubs = [
        async_track_state_change_event(
            hass, watched, coordinator.async_check_entity_state_change
        ),
        async_track_state_change_event(
            hass, covers, coordinator.async_check_cover_state_change
        ),
    ]
    try:
        await coordinator.async_window_first_refresh()
    except BaseException:
        for unsub in unsubs:
            unsub()
        await coordinator.async_shutdown()
        raise
    return coordinator, unsubs


# ------------------------------------------------------------ the house


@dataclass
class WindowRuntime:
    """One running window subentry."""

    window: WindowEntry
    coordinator: AdaptiveDataUpdateCoordinator
    unsubs: list[CALLBACK_TYPE]
    seen: tuple[str, dict[str, Any]]
    """The (title, data) the window was built from: the listener compares."""
    entities: list[Entity] = field(default_factory=list)


def house_runtime(entry: ConfigEntry) -> HouseRuntime | None:
    """Return the house entry's runtime (None when it is not loaded)."""
    runtime = getattr(entry, "runtime_data", None)
    return runtime if isinstance(runtime, HouseRuntime) else None


def window_coordinators(
    hass: HomeAssistant,
) -> dict[str, AdaptiveDataUpdateCoordinator]:
    """Return the running windows' coordinators, by window key."""
    house = house_entry(hass)
    runtime = house_runtime(house) if house is not None else None
    if runtime is None:
        return {}
    return {
        window.window.window_key: window.coordinator
        for window in runtime.windows.values()
    }


def window_coordinator(
    hass: HomeAssistant, window_key: str
) -> AdaptiveDataUpdateCoordinator | None:
    """Return one running window's coordinator, or None."""
    return window_coordinators(hass).get(window_key)


def _without_overrides(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key != OVERRIDES}


class HouseRuntime:
    """The house entry's runtime: its window subentries (see the module)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Start empty; ``async_start`` runs the window subentries."""
        self.hass = hass
        self.entry = entry
        self.windows: dict[str, WindowRuntime] = {}
        """The running windows, by subentry_id."""
        self.failed: dict[str, str] = {}
        """Windows that failed to set up: subentry_id -> the error."""
        self._retries: dict[str, CALLBACK_TYPE] = {}
        self._platforms: dict[
            str, tuple[entity_platform.EntityPlatform, WindowFactory]
        ] = {}
        self._lock = asyncio.Lock()
        self._house_device_id: str | None = None
        self._closed = False

    # -------------------------------------------------------- the house

    @callback
    def async_ensure_house_device(self) -> str:
        """Create the house device (the window devices hang off it)."""
        from .hub import hub_device_info

        if self._house_device_id is None:
            device = dr.async_get(self.hass).async_get_or_create(
                config_entry_id=self.entry.entry_id, **hub_device_info()
            )
            self._house_device_id = device.id
        return self._house_device_id

    def _wanted(self) -> dict[str, Any]:
        """Return the window subentries the house runs."""
        return {
            subentry.subentry_id: subentry
            for subentry in self.entry.get_subentries_of_type(WINDOW_SUBENTRY)
        }

    def _seen(self, subentry_id: str) -> tuple[str, dict[str, Any]]:
        subentry = self.entry.subentries[subentry_id]
        return subentry.title, dict(subentry.data)

    async def async_start(self) -> None:
        """Run every window subentry (each in isolation)."""
        self.async_ensure_house_device()
        async with self._lock:
            for subentry_id in self._wanted():
                await self._async_start_window(subentry_id)

    @callback
    def async_copy_areas(self) -> None:
        """Give each window device its cover's area (after the platforms set up)."""
        from .entity_surface import async_copy_cover_area

        for runtime in self.windows.values():
            async_copy_cover_area(self.hass, runtime.window)

    async def async_unload(self) -> None:
        """Stop every window (the house entry unloads; its platforms are gone)."""
        self._closed = True
        async with self._lock:
            for cancel in self._retries.values():
                cancel()
            self._retries.clear()
            for subentry_id in list(self.windows):
                await self._async_stop_window(subentry_id, remove_entities=False)

    # -------------------------------------------------------- platforms

    async def async_add_platform(self, domain: str, factory: WindowFactory) -> None:
        """Register a platform (from its setup) and add the running windows' entities."""
        platform = entity_platform.async_get_current_platform()
        async with self._lock:
            self._platforms[domain] = (platform, factory)
            for runtime in list(self.windows.values()):
                await self._async_add_entities(runtime, domain)

    async def _async_add_entities(self, runtime: WindowRuntime, domain: str) -> None:
        platform, factory = self._platforms[domain]
        entities = factory(self.hass, runtime.window, runtime.coordinator)
        runtime.entities.extend(entities)
        await platform.async_add_entities(
            entities, config_subentry_id=runtime.window.subentry_id
        )

    # -------------------------------------------------------- windows

    async def _async_start_window(self, subentry_id: str) -> None:
        """Build and run one window; a failure is contained to it."""
        from .entity_surface import async_copy_cover_area

        if self._closed or subentry_id in self.windows:
            return
        self._cancel_retry(subentry_id)
        window = WindowEntry(
            self.entry, subentry_id, via_device_id=self.async_ensure_house_device()
        )
        try:
            coordinator, unsubs = await async_build_window(self.hass, window)
        except Exception as err:  # noqa: BLE001 - one window must not stop the house
            self._window_failed(subentry_id, window, err)
            return
        runtime = WindowRuntime(window, coordinator, unsubs, self._seen(subentry_id))
        self.windows[subentry_id] = runtime
        try:
            for domain in list(self._platforms):
                await self._async_add_entities(runtime, domain)
        except (HomeAssistantError, KeyError, ValueError) as err:
            await self._async_stop_window(subentry_id)
            self._window_failed(subentry_id, window, err)
            return
        if self._platforms:
            async_copy_cover_area(self.hass, window)
        self.failed.pop(subentry_id, None)
        ir.async_delete_issue(
            self.hass, DOMAIN, window_failed_issue_id(window.window_key)
        )

    async def _async_stop_window(
        self, subentry_id: str, *, remove_entities: bool = True
    ) -> None:
        """Stop one window: its entities, listeners and coordinator."""
        self._cancel_retry(subentry_id)
        self.failed.pop(subentry_id, None)
        runtime = self.windows.pop(subentry_id, None)
        if runtime is None:
            return
        if remove_entities:
            for entity in runtime.entities:
                if entity.hass is not None and entity.platform is not None:
                    await entity.async_remove()
        for unsub in runtime.unsubs:
            unsub()
        await runtime.coordinator.async_shutdown()

    def _window_failed(
        self, subentry_id: str, window: WindowEntry, err: BaseException
    ) -> None:
        """Record a window that failed to set up: repair issue, retry later."""
        key = window.window_key
        _LOGGER.error(
            "Window %s (%s) could not be set up: %s; the rest of the house "
            "keeps running, and it tries again in %s s",
            window.title,
            key,
            err,
            RETRY_SECONDS,
        )
        self.failed[subentry_id] = str(err) or type(err).__name__
        async_window_failed_issue(
            self.hass, key, window.title, self.failed[subentry_id]
        )
        if self._closed:
            return

        @callback
        def _retry(_now: Any) -> None:
            self._retries.pop(subentry_id, None)
            self.entry.async_create_background_task(
                self.hass, self.async_sync(), f"{DOMAIN} retry window {key}"
            )

        self._cancel_retry(subentry_id)
        self._retries[subentry_id] = async_call_later(self.hass, RETRY_SECONDS, _retry)

    def _cancel_retry(self, subentry_id: str) -> None:
        if (cancel := self._retries.pop(subentry_id, None)) is not None:
            cancel()

    # -------------------------------------------------------- changes

    async def async_sync(self) -> None:
        """Bring the running windows in line with the house's subentries.

        The house entry's update listener. A removed subentry stops, a new
        one (or one that failed before) starts, and a changed one is
        rebuilt alone. A change that only wrote the window's ``overrides``
        re-resolves the window in place (no rebuild); a subentry whose
        title and data are unchanged is left alone.
        """
        from .layers import async_settings_changed

        if self._closed:
            return
        async with self._lock:
            wanted = self._wanted()
            for subentry_id in [s for s in self.windows if s not in wanted]:
                await self._async_stop_window(subentry_id)
            for subentry_id in [s for s in self.failed if s not in wanted]:
                self._forget_failure(subentry_id)
            refresh: list[str] = []
            for subentry_id in wanted:
                runtime = self.windows.get(subentry_id)
                if runtime is None:
                    await self._async_start_window(subentry_id)
                    continue
                seen = self._seen(subentry_id)
                if runtime.seen == seen:
                    continue
                if runtime.seen[0] == seen[0] and _without_overrides(
                    runtime.seen[1]
                ) == _without_overrides(seen[1]):
                    # Only the window's overrides changed: it re-reads them.
                    runtime.seen = seen
                    refresh.append(runtime.window.window_key)
                    continue
                await self._async_stop_window(subentry_id)
                await self._async_start_window(subentry_id)
        if refresh:
            await async_settings_changed(self.hass, refresh)

    def _forget_failure(self, subentry_id: str) -> None:
        self._cancel_retry(subentry_id)
        self.failed.pop(subentry_id, None)
        subentry = self.entry.subentries.get(subentry_id)
        if subentry is not None:
            key = subentry_window_key(subentry)
        else:
            key = subentry_id
        ir.async_delete_issue(self.hass, DOMAIN, window_failed_issue_id(key))

    async def async_rebuild_window(self, subentry_id: str) -> None:
        """Rebuild one window (its settings need new entities or listeners)."""
        if self._closed:
            return
        async with self._lock:
            await self._async_stop_window(subentry_id)
            if subentry_id in self._wanted():
                await self._async_start_window(subentry_id)

    @callback
    def async_schedule_rebuild(self, subentry_id: str) -> None:
        """Rebuild one window soon (from inside its own refresh)."""
        self.entry.async_create_background_task(
            self.hass,
            self.async_rebuild_window(subentry_id),
            f"{DOMAIN} rebuild window {subentry_id}",
        )


async def async_setup_house_platform(
    hass: HomeAssistant, entry: ConfigEntry, domain: str, factory: WindowFactory
) -> None:
    """Add the house's window entities of one platform (from its setup)."""
    runtime = house_runtime(entry)
    if runtime is not None:
        await runtime.async_add_platform(domain, factory)
