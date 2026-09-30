"""WindowHandle: the test suite's door into one window's PUBLIC surface.

A window is addressed by its cover entity id (or by its window key, which
today is the config entry id). Its entities are found by ROLE through the
entity registry; reads go through ``hass.states`` and event-bus records;
actions go through real service calls. WindowHandle never reads
``hass.data``, the coordinator, or entity objects, so a backend rewrite
does not touch the tests that use it.

    window = WindowHandle(hass, "cover.office")   # before setup: records
    await hass.config_entries.async_setup(entry.entry_id)
    assert window.target == 24                    # Position sensor
    assert window.last_command == 24              # what we told the cover
    assert window.moves[0]["source"] == "startup" # adaptive_cover_moved
    assert not window.is_manual                   # Manual override sensor

Build the handle BEFORE the entry is set up when a test needs the startup
command or its provenance: commands and moves are recorded from the bus
from construction on. Entity lookups are lazy, so they work either way.

Since v2.1 (P8) every window is a ``window`` subentry of the house entry;
repointing to it (refactor plan P7, P8) changed only ``window_configs`` and
``_entity_rows``; the role vocabulary and every read helper stayed put.

``internal_coordinator`` is deliberately NOT a WindowHandle feature: it is
the one sanctioned way to reach an internal fact no public surface exposes,
and every call site is marked ``# contract: internal (<reason>)``.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, Event, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er

from custom_components.adaptive_cover.const import CONF_COVER_ENTITY, DOMAIN

# role -> (platform, unique-id suffix). Suffixes are the legacy unique-id
# tails, which the refactor contract freezes.
ROLES: dict[str, tuple[str, str]] = {
    "position": ("sensor", "Cover Position"),
    "start_sun": ("sensor", "Start Sun"),
    "end_sun": ("sensor", "End Sun"),
    "control_method": ("sensor", "Control Method"),
    "next_change": ("sensor", "Next State Change"),
    "last_change": ("sensor", "Last State Change"),
    "sun_in_front": ("binary_sensor", "Sun Infront"),
    "manual_override": ("binary_sensor", "Manual Override"),
    "mode": ("select", "mode_select"),
    "return_to_auto": ("button", "Reset Manual Override"),
}

MOVED_EVENT = "adaptive_cover_moved"
_COVER_POSITION_SERVICES = {
    "set_cover_position": "position",
    "set_cover_tilt_position": "tilt_position",
}


def window_configs(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Every window's stored data, by window key, from the house entry.

    A window is a ``window`` subentry of the house entry: its key is the
    old entry_id it stores, else its subentry_id. Window entries left from
    1.x do not run and are not windows.
    """
    windows: dict[str, dict[str, Any]] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not entry.data.get("is_hub"):
            continue
        for subentry in entry.subentries.values():
            if subentry.subentry_type != "window":
                continue
            key = subentry.data.get("window_key") or subentry.subentry_id
            windows[key] = dict(subentry.data)
    return windows


def _find_window_key(hass: HomeAssistant, cover: str) -> str:
    """The window key of the window driving ``cover``."""
    for key, data in window_configs(hass).items():
        if data.get(CONF_COVER_ENTITY) == cover:
            return key
    raise LookupError(f"No adaptive_cover window drives {cover}")


def _entity_rows(hass: HomeAssistant, window_key: str) -> list[er.RegistryEntry]:
    """Registry rows of one window: its unique_id prefix (frozen, P7-proof)."""
    prefix = f"{window_key}_"
    return [
        row
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN and row.unique_id.startswith(prefix)
    ]


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


class WindowHandle:
    """Role-based, public-surface-only access to one window."""

    def __init__(
        self,
        hass: HomeAssistant,
        cover: str | None = None,
        *,
        window_key: str | None = None,
    ) -> None:
        if cover is None and window_key is None:
            raise ValueError("WindowHandle needs a cover or a window_key")
        self.hass = hass
        self.cover = cover
        self._window_key = window_key
        self._commands: list[tuple[int, Context]] = []
        self._moves: list[dict[str, Any]] = []
        self._teardowns = 0
        self._unsubs = [
            hass.bus.async_listen(EVENT_CALL_SERVICE, self._on_call_service),
            hass.bus.async_listen(MOVED_EVENT, self._on_moved),
            hass.bus.async_listen(EVENT_STATE_CHANGED, self._on_state_changed),
        ]

    @classmethod
    def by_key(cls, hass: HomeAssistant, window_key: str) -> WindowHandle:
        """A handle for a window addressed by its key (no cover needed)."""
        return cls(hass, window_key=window_key)

    def close(self) -> None:
        """Stop recording (optional; the hass fixture tears the bus down)."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    # ---------------------------------------------------------- recorders

    @callback
    def _on_call_service(self, event: Event) -> None:
        if self.cover is None or event.data.get("domain") != "cover":
            return
        field = _COVER_POSITION_SERVICES.get(event.data.get("service"))
        if field is None:
            return
        data = event.data.get("service_data") or {}
        if self.cover in _as_list(data.get("entity_id")) and field in data:
            self._commands.append((int(data[field]), event.context))

    @callback
    def _on_moved(self, event: Event) -> None:
        if self.cover is not None and event.data.get("entity_id") == self.cover:
            self._moves.append(dict(event.data))

    @callback
    def _on_state_changed(self, event: Event) -> None:
        # Unloading a window writes its registered entities 'unavailable'
        # with restored=True (or removes them): one teardown per unload.
        new_state = event.data.get("new_state")
        if new_state is not None and not (
            new_state.state == "unavailable" and new_state.attributes.get("restored")
        ):
            return
        try:
            position_eid = self.entity_id("position")
        except LookupError:
            return
        if event.data.get("entity_id") == position_eid:
            self._teardowns += 1

    # -------------------------------------------------------------- lookup

    @property
    def window_key(self) -> str:
        """The window's key (a migrated window's old entry_id, else its subentry_id)."""
        if self._window_key is None:
            self._window_key = _find_window_key(self.hass, self.cover)
        return self._window_key

    def entity_id(self, role: str) -> str:
        """Entity id of this window's entity playing ``role``."""
        platform, suffix = ROLES[role]
        unique_id = f"{self.window_key}_{suffix}"
        for row in _entity_rows(self.hass, self.window_key):
            if row.domain == platform and row.unique_id == unique_id:
                return row.entity_id
        raise LookupError(f"{self.window_key} has no {role} entity")

    def has(self, role: str) -> bool:
        """Whether this window has an entity playing ``role``."""
        try:
            self.entity_id(role)
        except LookupError:
            return False
        return True

    def state(self, role: str) -> State | None:
        """Current State of the entity playing ``role``."""
        return self.hass.states.get(self.entity_id(role))

    # ------------------------------------------------------------- reads

    @property
    def attributes(self) -> dict[str, Any]:
        """Attributes of the Position sensor."""
        state = self.state("position")
        return dict(state.attributes) if state is not None else {}

    @property
    def target(self) -> int | None:
        """The Position sensor: the position the window currently wants."""
        state = self.state("position")
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        return int(float(state.state))

    @property
    def available(self) -> bool:
        """The window is running and its last update succeeded."""
        state = self.state("position")
        return state is not None and state.state != "unavailable"

    @property
    def mode(self) -> str | None:
        """The window's Mode: the Mode select's state (auto / hold / off)."""
        state = self.state("mode")
        return state.state if state is not None else None

    @property
    def hold_until(self) -> str | None:
        """When the window's hold ends: the Mode select's ``until`` (local ISO)."""
        state = self.state("mode")
        return state.attributes.get("until") if state is not None else None

    @property
    def manual_override(self) -> bool:
        """The Manual override binary sensor is on (any of its covers)."""
        state = self.state("manual_override")
        return state is not None and state.state == "on"

    @property
    def is_manual(self) -> bool:
        """THIS cover is listed as manually controlled."""
        state = self.state("manual_override")
        if state is None:
            return False
        return self.cover in (state.attributes.get("manual_controlled") or [])

    @property
    def move_blocked_by(self) -> str | None:
        """The gate that blocked this cover's last evaluated move, if any."""
        return (self.attributes.get("move_blocked_by") or {}).get(self.cover)

    @property
    def last_move_line(self) -> str | None:
        """This cover's 'HH:MM -> N% (source: reason)' last-move line."""
        return (self.attributes.get("last_moves") or {}).get(self.cover)

    @property
    def forecast(self) -> list[dict[str, Any]] | None:
        """Today's change-point forecast (Position ``forecast_today``)."""
        return self.attributes.get("forecast_today")

    @property
    def cover_position(self) -> int | None:
        """The physical cover's reported ``current_position``."""
        state = self.hass.states.get(self.cover)
        if state is None:
            return None
        return state.attributes.get("current_position")

    @property
    def commands(self) -> list[int]:
        """Every position commanded to this cover since the handle was built.

        Recorded from HA's ``call_service`` bus event, so it sees the
        command whichever handler (a test mock or the real cover
        component) serves it. Tests drive humans through state writes,
        so in practice these are the integration's commands.
        """
        return [position for position, _ctx in self._commands]

    @property
    def last_command(self) -> int | None:
        """The most recent position commanded to this cover, if any."""
        return self._commands[-1][0] if self._commands else None

    @property
    def moves(self) -> list[dict[str, Any]]:
        """Delivered moves with provenance (``adaptive_cover_moved`` events).

        Each is ``{entity_id, time, position, source, reason}``; source is
        startup / adaptive / end_time / control_enabled / all_covers /
        manual.
        """
        return list(self._moves)

    @property
    def teardowns(self) -> int:
        """How many times the window's entities were unloaded (reloads)."""
        return self._teardowns

    async def settings(self) -> dict[str, Any]:
        """What the window acts on: its resolved settings (P5 flip).

        Read through the integration's diagnostics, the public surface
        that shows them.
        """
        return await window_settings(self.hass, self.window_key)

    # ------------------------------------------------------------ actions

    async def press(
        self, role: str = "return_to_auto", *, context: Context | None = None
    ) -> None:
        """Press one of the window's buttons via a real service call."""
        await self.hass.services.async_call(
            "button",
            "press",
            {"entity_id": self.entity_id(role)},
            blocking=True,
            context=context,
        )
        await self.hass.async_block_till_done()

    async def select_mode(self, option: str, *, context: Context | None = None) -> None:
        """Set the window's Mode select via a real service call."""
        await self.hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": self.entity_id("mode"), "option": option},
            blocking=True,
            context=context,
        )
        await self.hass.async_block_till_done()


def _house(hass: HomeAssistant):
    return next(
        e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("is_hub")
    )


async def window_settings(hass: HomeAssistant, window_key: str) -> dict[str, Any]:
    """A running window's resolved settings, from the diagnostics download.

    The house entry's download lists each window under ``windows``.
    """
    from custom_components.adaptive_cover.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    house_diagnostics = await async_get_config_entry_diagnostics(hass, _house(hass))
    settings = house_diagnostics["windows"][window_key]["settings"]
    assert settings is not None, f"{window_key} is not loaded"
    return settings


def internal_coordinator(hass: HomeAssistant, window_key: str):
    """The window's live coordinator object. NOT a public surface.

    contract: internal. The single place the test suite knows where the
    integration keeps its runtime objects: the house entry's
    ``runtime_data`` (``house.HouseRuntime``), which runs one coordinator
    per window subentry. Use it only for a fact no entity, event, or
    service exposes, and mark the call site ``# contract: internal
    (<reason>)``.
    """
    runtime = getattr(_house(hass), "runtime_data", None)
    if runtime is None:
        return None
    for window in runtime.windows.values():
        if window.window.window_key == window_key:
            return window.coordinator
    return None
