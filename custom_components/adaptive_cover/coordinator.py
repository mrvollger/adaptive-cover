"""The Coordinator for Adaptive Cover."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_SET_COVER_POSITION,
    SERVICE_SET_COVER_TILT_POSITION,
    STATE_UNAVAILABLE,
)
from homeassistant.core import (
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .config_context_adapter import ConfigContextAdapter
from .engine.season import Season
from .runtime.clock import SYSTEM_CLOCK, Clock
from .runtime.command_tracker import CommandTracker
from .runtime.decider import Decider
from .runtime.end_of_day import EndOfDay
from .runtime.events import RefreshEvent, RefreshQueue
from .runtime.explainer import Explainer
from .runtime.gates import CoverFacts, GatePolicy
from .runtime.manual_detector import ManualDetector
from .runtime.mode import ModeControl
from .runtime.override_tracker import OverrideTracker
from .runtime.schedule import Schedule
from .runtime.shade_config import ControlState, ControlToggle, ShadeConfig

from .calculation import (
    ClimateCoverData,
    ClimateCoverState,
    NormalCoverState,
    build_cover,
    build_day_forecast,
    get_state_reason,
)
from .const import (
    _LOGGER,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CONF_CLIMATE_MODE,
    CONF_CLIMATE_ON,
    CONF_INTERP,
    CONF_INVERSE_STATE,
    CONF_MANUAL_DETECTION,
    CONF_SUNSET_POS,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_USE_IRRADIANCE,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
    DOMAIN,
    LOGGER,
)
from .helpers import (
    get_safe_attr,
    get_safe_state,
)
from .layers import SETUP_KEYS, effective_settings
from .windows import WindowEntry
from .settings.lift import same_value


# Seam: the clock a coordinator reads when none is passed in. Production
# keeps Home Assistant's clock (dt_util, which the tests' freezer fixture
# freezes); a test may assign a fake here, like calculation.sun_data_factory.
default_clock: Clock = SYSTEM_CLOCK


def cached_timezone(name: str) -> dt.tzinfo:
    """Return the time zone by name, cached (``dt_util.get_time_zone``).

    The first construction reads a zoneinfo file: blocking I/O that must
    not run in the event loop. async_setup_entry primes this cache from an
    executor; every later call is a dict lookup.

    Raises
    ------
    KeyError
        For an unknown name, like pytz's UnknownTimeZoneError (a KeyError)
        before P2. Home Assistant validates its configured zone, so this
        does not happen in practice.

    """
    zone = dt_util.get_time_zone(name)
    if zone is None:
        raise KeyError(name)
    return zone


def localize_standard(naive: dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    """Attach ``tz`` to a naive local time, standard time where it is ambiguous.

    What pytz's ``localize()`` did (``is_dst=False``): a repeated wall time
    (the hour DST ends) takes the standard-time reading, a skipped one (the
    hour DST starts) the offset from before the jump.
    """
    first = naive.replace(tzinfo=tz, fold=0)
    second = naive.replace(tzinfo=tz, fold=1)
    if first.utcoffset() == second.utcoffset():
        return first
    return first if not first.dst() else second


def async_schedule_window_reload(hass: HomeAssistant, window: WindowEntry) -> None:
    """Rebuild one window alone (its subentry; the rest of the house runs on)."""
    from .house import house_runtime

    runtime = house_runtime(window.config_entry)
    if runtime is not None:
        runtime.async_schedule_rebuild(window.subentry_id)


@dataclass
class StateChangedData:
    """StateChangedData class."""

    entity_id: str
    old_state: State | None
    new_state: State | None


@dataclass
class AdaptiveCoverData:
    """AdaptiveCoverData class."""

    climate_mode_toggle: bool
    states: dict
    attributes: dict


class AdaptiveDataUpdateCoordinator(DataUpdateCoordinator[AdaptiveCoverData]):
    """Adaptive cover data update coordinator."""

    config_entry: ConfigEntry
    MOVE_LOG_LIMIT = Explainer.MOVE_LOG_LIMIT
    # The travel-time upper bound (the reset button waits at most this long).
    TARGET_TIMEOUT = CommandTracker.TARGET_TIMEOUT

    def __init__(
        self,
        hass: HomeAssistant,
        clock: Clock | None = None,
        *,
        window: WindowEntry,
    ) -> None:
        """Initialize the coordinator of one window.

        ``window`` is the window (a subentry of the house, windows.py).
        ``clock`` is where every "now" comes from (see runtime/clock.py);
        None means the module's ``default_clock``.
        """
        self.window: WindowEntry = window
        # What the window acts on: its resolved settings (layers.py),
        # re-read on every refresh (_read_settings). Read first: a window
        # whose stored settings cannot be read fails here, before the
        # house entry holds anything of it.
        settings = effective_settings(hass, window)
        # The owning entry: its unload shuts the coordinator down.
        super().__init__(
            hass, LOGGER, config_entry=self.window.config_entry, name=DOMAIN
        )
        self.clock: Clock = clock if clock is not None else default_clock

        self.logger = ConfigContextAdapter(_LOGGER)
        self.logger.set_config_name(self.window.name)
        self._cover_type = self.window.cover_type
        self.options: dict[str, Any] = settings.options
        self.provenance: dict[str, str] = settings.provenance
        # Read once: they decide the window's entities and listeners; a
        # change reloads the window (SETUP_KEYS).
        self._setup_values = {key: self.options.get(key) for key in SETUP_KEYS}
        self._climate_mode = self.options.get(CONF_CLIMATE_MODE, False)
        self.controls = ControlState(climate=True if self._climate_mode else False)
        self._apply_toggles(self.options)
        self.decider = Decider(
            self.options.get(CONF_INTERP, False),
            self.options.get(CONF_INVERSE_STATE, False),
            self.logger,
        )
        self._sun_end_time = None
        self._sun_start_time = None
        self.config = ShadeConfig.from_options(self.options)
        self.schedule = Schedule(
            lambda entity_id: get_safe_state(self.hass, entity_id),
            self.logger,
            local_zone=lambda: cached_timezone(self.hass.config.time_zone),
        )
        self.gates = GatePolicy(self.logger)
        # Why the next refresh runs (entity change, cover report, startup,
        # end-of-day timer).
        self.events: RefreshQueue[StateChangedData] = RefreshQueue()
        self.climate_state = None
        self.control_method = "intermediate"
        self.state_change_data: StateChangedData | None = None
        # Override bookkeeping lives in hass.data so options reloads (which
        # rebuild the coordinator) do not silently wipe active overrides.
        _manual_store = self.hass.data.setdefault(f"{DOMAIN}_manual_state", {})
        self.manager = OverrideTracker(
            self.config.manual_duration,
            self.logger,
            persisted_state=_manual_store.setdefault(self.window.window_key, {}),
            clock=self.clock,
        )
        self.commands = CommandTracker(
            self.clock,
            lambda delay, action: async_call_later(self.hass, delay, action),
            self._force_poll,
            self.logger,
        )
        self.detector = ManualDetector(self.manager, self.commands, self.logger)
        # The window's Mode (auto / hold / off): the Mode select, its
        # Toggle Control alias, the Return to auto button and the hold
        # service change it here.
        self.modes = ModeControl(self, self.logger)
        self._sun_table = None
        self._missing_warned: set[str] = set()
        self.end_of_day = EndOfDay(
            lambda action, point: async_track_point_in_time(self.hass, action, point),
            self._now_local,
            lambda: self._end_time,
            self._request_end_close,
            self.logger,
        )

        self._basic_decision = None
        self._climate_decision = None
        # This refresh's climate snapshot (climate_mode_data builds it once).
        self._climate: ClimateCoverData | None = None
        # The season the last climate decision found: the temp_hysteresis
        # memory (engine/season.py). In memory only: a restart or reload
        # starts from None, so its first decision uses the plain rule.
        self._season: Season | None = None
        self._gate_blocks: dict[str, str | None] = {}
        self.explainer = Explainer(self.logger)

    async def async_config_entry_first_refresh(self) -> None:
        """Config entry first refresh."""
        self.events.push(RefreshEvent.STARTUP)
        await super().async_config_entry_first_refresh()
        self.logger.debug("Config entry first refresh")

    async def async_window_first_refresh(self) -> None:
        """Run the window's first refresh, while its entry sets up or later.

        A window subentry added or rebuilt while the house runs sets up
        after the house entry finished setting up, where HA's
        ``async_config_entry_first_refresh`` refuses to run.

        Raises
        ------
        ConfigEntryNotReady
            The first refresh failed.

        """
        if self.config_entry.state is ConfigEntryState.SETUP_IN_PROGRESS:
            await self.async_config_entry_first_refresh()
            return
        self.events.push(RefreshEvent.STARTUP)
        await self.async_refresh()
        if not self.last_update_success:
            raise ConfigEntryNotReady(str(self.last_exception)) from (
                self.last_exception
            )
        self.logger.debug("Window first refresh")

    @property
    def _track_end_time(self) -> bool | None:
        """Close at the end time (``return_sunset``), as this refresh reads it."""
        return self.config.return_sunset

    @property
    def ignore_intermediate_states(self) -> bool:
        """Skip opening/closing reports (``manual_ignore_intermediate``)."""
        return bool(self.config.ignore_intermediate)

    def _apply_toggles(self, options: Mapping[str, Any]) -> None:
        """Set the switch-era toggles from the resolved settings (P5 flip).

        Climate needs climate mode as well: a window without it had no
        Climate Mode switch, and its toggle followed the option.
        """
        self.controls.climate = bool(
            options.get(CONF_CLIMATE_MODE) and options.get(CONF_CLIMATE_ON)
        )
        self.controls.outside_temp = bool(options.get(CONF_USE_OUTSIDE_TEMP))
        self.controls.lux = bool(options.get(CONF_USE_LUX))
        self.controls.irradiance = bool(options.get(CONF_USE_IRRADIANCE))
        self.controls.manual = bool(options.get(CONF_MANUAL_DETECTION))

    def _read_settings(self) -> dict[str, Any]:
        """Re-read the window's resolved settings (every refresh).

        A change to what the window read at setup (its listeners and which
        entities it has) reloads it.
        """
        settings = effective_settings(self.hass, self.window)
        self.options = settings.options
        self.provenance = settings.provenance
        changed = sorted(
            key
            for key in SETUP_KEYS
            if not same_value(self.options.get(key), self._setup_values[key])
        )
        if changed:
            self.logger.info("Settings %s changed: reloading the window", changed)
            self._setup_values = {key: self.options.get(key) for key in SETUP_KEYS}
            async_schedule_window_reload(self.hass, self.window)
        return self.options

    async def async_settings_changed(self) -> None:
        """Act on changed settings now (layers.async_settings_changed).

        The refresh re-reads the settings; a target that changed goes out
        through the usual gates, as after a sensor change.
        """
        self.events.push(RefreshEvent.ENTITY_CHANGED)
        await self.async_refresh()

    async def _request_end_close(self) -> None:
        """Run the end-of-day close on a refresh (EndOfDay calls this)."""
        self.events.push(RefreshEvent.END_TIME)
        self.logger.debug("Timed refresh triggered")
        await self.async_refresh()

    async def async_check_entity_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Fetch and process state change event."""
        self.logger.debug("Entity state change")
        self.events.push(RefreshEvent.ENTITY_CHANGED)
        await self.async_request_refresh()

    def is_own_context(self, context: Context | None) -> bool:
        """Return True when ``context`` belongs to a cover command WE issued.

        Every command this coordinator sends carries a fresh Context whose
        id is remembered; an echo of that command (the cover's intermediate
        state written inside the service call) carries the same context.
        """
        return context is not None and self.commands.is_own_context_id(context.id)

    @property
    def wait_for_target(self) -> dict[str, bool]:
        """The per-cover travel latch (the reset button reads and clears it)."""
        return self.commands.wait_for_target

    @property
    def target_call_time(self) -> dict[str, dt.datetime]:
        """When each cover was last commanded (the reset button reads it)."""
        return self.commands.target_call_time

    async def async_check_cover_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Fetch and process state change event."""
        self.logger.debug("Cover state change")
        data = event.data
        old_state = data["old_state"]
        new_state = data["new_state"]
        if old_state is None:
            self.logger.debug("Old state is None")
            if new_state is not None:
                # The cover's first state: its integration finished starting
                # after ours (boot) or it was just added. Decide now instead
                # of waiting for the next sun update, which is slow at night;
                # the usual gates still decide whether anything moves.
                self.events.push(RefreshEvent.ENTITY_CHANGED)
                await self.async_refresh()
            return
        if new_state is None:
            self.logger.debug("New state is None")
            return
        self.state_change_data = StateChangedData(
            data["entity_id"], old_state, new_state
        )
        if old_state.state in ("unknown", "unavailable"):
            self.logger.debug("Old state is %s, not processing", old_state.state)
            # Device just came back: deliver any end-of-day close that
            # could not be sent while it was away.
            pending = self.end_of_day.take_retry(data["entity_id"], self.control_toggle)
            if pending is not None:
                self.logger.debug(
                    "Retrying missed end-of-day close for %s", data["entity_id"]
                )
                await self.async_set_manual_position(
                    data["entity_id"],
                    pending,
                    source="end_time",
                    reason="retry after cover returned",
                )
            return
        if new_state.state in ("unknown", "unavailable"):
            self.logger.debug("New state is %s, not processing", new_state.state)
            return
        entity_id = data["entity_id"]
        # Our own command echoing back (service context preserved):
        # bookkeeping only - never manual, never a full refresh.
        if self.is_own_context(event.context):
            self.process_entity_state_change(own_context=True)
            return
        # A change carrying a user id is a HUMAN act (dashboard click,
        # user-run service): it always counts as manual - clear any travel
        # window so it can never be swallowed as a motor echo.
        if event.context is not None and event.context.user_id is not None:
            self.commands.release(entity_id)
        # Foreign movement STARTING (opening/closing we didn't command) is a
        # human act the moment the motor spins. These shades report position
        # only at journey end, so waiting for the landing report leaves a
        # 1-3 minute window where the cover reads as auto-controlled while a
        # person is actively moving it.
        if new_state.state in ("opening", "closing") and not self.wait_for_target.get(
            entity_id
        ):
            self._adopt_late_delivery(entity_id)
        # A cover starting to move AGAINST our in-flight command is a human
        # act even inside the travel window: our motor cannot reverse on its
        # own. Clear the travel latch so the motion-start latch below fires.
        self.commands.release_if_against(
            entity_id,
            new_state.state,
            old_state.attributes.get(
                "current_tilt_position"
                if self._cover_type == "cover_tilt"
                else "current_position"
            ),
        )
        if self.detector.motion_started(
            entity_id,
            new_state,
            self.controls,
            self.config,
            self.ignore_intermediate_states,
        ):
            self.record_move_provenance(
                entity_id,
                new_state.attributes.get(
                    "current_tilt_position"
                    if self._cover_type == "cover_tilt"
                    else "current_position"
                ),
                "manual",
                "manual movement started",
            )
        # Foreign event. Update the travel latch (tolerance/expiry); if the
        # cover is still mid-travel this is a device position echo: skip
        # the full refresh so bursts don't queue-storm the pipeline.
        status = self.process_entity_state_change()
        # Someone stopped or redirected the cover mid-travel.
        if self.detector.redirected(
            entity_id, status, new_state, self.controls, self.config
        ):
            self.record_move_provenance(
                entity_id,
                new_state.attributes.get(
                    "current_tilt_position"
                    if self._cover_type == "cover_tilt"
                    else "current_position"
                ),
                "manual",
                "manual redirect during travel",
            )
        if self.wait_for_target.get(entity_id):
            return
        # Cover events queue up per refresh: a single mutable slot dropped
        # events when two covers (room-group remote) moved simultaneously.
        self.events.push_cover(self.state_change_data)
        await self.async_refresh()

    def process_entity_state_change(self, own_context: bool = False) -> str | None:
        """Process state change event.

        Returns a classification of the event relative to an in-flight
        command: None (no wait active / nothing notable), "arrived",
        "expired", "in_travel" (intermediate state while waiting), or
        "foreign_landing" (a definitive position report inside the travel
        window that is NOT our target — someone redirected the cover).
        """
        event = self.state_change_data
        self.logger.debug("Processing state change event: %s", event)
        if event is None or event.new_state is None:
            return None
        entity_id = event.entity_id
        new_state = event.new_state
        if self.ignore_intermediate_states and new_state.state in [
            "opening",
            "closing",
        ]:
            self.logger.debug("Ignoring intermediate state change for %s", entity_id)
            return None
        return self.commands.classify_report(
            entity_id,
            new_state.state,
            new_state.attributes.get(
                "current_position"
                if self._cover_type != "cover_tilt"
                else "current_tilt_position"
            ),
            own_context,
        )

    async def async_shutdown(self) -> None:
        """Cancel every timer this coordinator armed (entry unload).

        HA calls this on unload. Arrival polls and the end-of-day tracker
        used to outlive the entry and fire against a dead coordinator.
        """
        self.commands.cancel_polls()
        self.end_of_day.shutdown()
        await super().async_shutdown()

    @property
    def forecast(self) -> list[dict] | None:
        """Today's forecast (the get_forecast service reads it)."""
        return self.explainer.forecast

    @property
    def move_log(self) -> dict[str, list[dict]]:
        """The per-cover move log."""
        return self.explainer.move_log

    def _compute_next_event(self, cover_data, start, end):
        """Find the next significant cover state change event."""
        configured_end = None
        # Configured end time (_end_time is naive local time from config)
        if self._end_time is not None and self._track_end_time:
            configured_end = self._end_time
            if configured_end.tzinfo is None:
                local_tz = cached_timezone(self.hass.config.time_zone)
                configured_end = localize_standard(configured_end, local_tz)
        return self.explainer.next_event(
            cover_data,
            now=self.clock.utcnow(),
            tomorrow=self._now_local().date() + dt.timedelta(days=1),
            start=start,
            end=end,
            sun_table=self._sun_table,
            configured_end=configured_end,
            end_position=self.options.get(CONF_SUNSET_POS, cover_data.sunset_pos),
            override_expiries=[
                expiry
                for cover in list(self.manager.manual_control_time)
                if (expiry := self.manager.expires_at(cover)) is not None
            ],
        )

    async def _async_update_data(self) -> AdaptiveCoverData:
        self.logger.debug("Updating data")
        options = self._read_settings()
        self._update_options(options)
        self._apply_toggles(options)

        # Get data for the blind
        cover_data = self.get_blind_data()

        # Update manager with covers
        self._update_manager_and_covers()

        # Access climate data if climate mode is enabled
        if self._climate_mode:
            self.climate_mode_data(options, cover_data)
        else:
            self.logger.debug("Control method is %s", self.control_method)

        # calculate the state of the cover
        self.normal_cover_state = NormalCoverState(cover_data)
        self.logger.debug(
            "Determined normal cover state to be %s", self.normal_cover_state
        )

        self._basic_decision = self.normal_cover_state.get_decision()
        self.default_state = round(self._basic_decision.position)
        self.logger.debug("Determined default state to be %s", self.default_state)
        state = self.state

        await self.manager.reset_if_needed()

        self.end_of_day.ensure_armed(self._end_time, self._track_end_time)

        # Capture flags before handlers reset them
        had_cover_state_change = self.events.pending(RefreshEvent.COVER_CHANGED)

        # Handle types of changes
        if self.events.pending(RefreshEvent.ENTITY_CHANGED):
            await self.async_handle_state_change(state)
        if self.events.pending(RefreshEvent.COVER_CHANGED):
            # Drain ALL queued cover events: concurrent moves (a room-group
            # remote driving several covers) each deserve manual detection.
            pending = self.events.take_covers()
            if not pending and self.state_change_data is not None:
                pending = [self.state_change_data]
            for cover_event in pending:
                self.state_change_data = cover_event
                await self.async_handle_cover_state_change(state)
        if self.events.pending(RefreshEvent.STARTUP):
            await self.async_handle_first_refresh(state)
        if self.events.pending(RefreshEvent.END_TIME):
            await self.async_handle_timed_refresh(options)

        normal_cover = self.normal_cover_state.cover
        # Climate snapshot used for reasons, forecasting, and trace: the one
        # the climate decision used (built once, in climate_mode_data).
        climate_data_for_reason = None
        if self._climate_mode and self.controls.climate:
            climate_data_for_reason = self._climate

        # Run the solar_times method in a separate thread.
        # Compare CONFIGURED-local dates: the UTC date rolls over mid-evening
        # for western timezones (18:00 in Denver), which regenerated the sun
        # table 6 hours early.
        _local_date = self._now_local().date()
        starting = self.events.pending(RefreshEvent.STARTUP)
        solar_day_stale = (
            starting
            or self._sun_start_time is None
            or _local_date != self._sun_start_time.date()
        )
        if (
            not starting
            and self._sun_start_time is not None
            and _local_date != self._sun_start_time.date()
        ):
            # New solar day: the natural boundary where deliberate
            # (reset=False) overrides end and auto control resumes. A
            # requested hold keeps its own end.
            self.logger.debug("New solar day: clearing manual overrides")
            self.manager.reset_detected()
        if solar_day_stale:
            self.logger.debug("Calculating solar times")
            loop = asyncio.get_event_loop()

            def _load_solar_day(cover=normal_cover):
                span = cover.solar_times()
                sun_data = cover.sun_data
                return span, (
                    sun_data.times,
                    sun_data.solar_azimuth,
                    sun_data.solar_elevation,
                )

            (start, end), self._sun_table = await loop.run_in_executor(
                None, _load_solar_day
            )
            self._sun_start_time = start
            self._sun_end_time = end
            self.logger.debug("Sun start time: %s, Sun end time: %s", start, end)
        else:
            start, end = self._sun_start_time, self._sun_end_time

        # Rebuild the day forecast when the solar day rolls over or the
        # climate snapshot changes (it is baked into the schedule).
        loop = asyncio.get_event_loop()
        await self.explainer.refresh_forecast(
            solar_day_stale,
            climate_data_for_reason,
            lambda: loop.run_in_executor(
                None, build_day_forecast, cover_data, climate_data_for_reason
            ),
            self._transform_state,
        )

        # Compute state reason
        reason = get_state_reason(cover_data, climate_data_for_reason)
        if self.manager.binary_cover_manual:
            reason = "Manual override"

        # Active decision (intent + trace) for explanations
        active_decision = (
            self._climate_decision if self.controls.climate else self._basic_decision
        )

        # Compute next event
        next_event = self._compute_next_event(cover_data, start, end)
        next_event_name = next_event[0] if next_event else None
        next_event_time = next_event[1] if next_event else None
        next_event_pos = next_event[2] if next_event else None
        # For manual override expiry, the cover returns to the computed state
        if next_event_pos is None and next_event_name:
            next_event_pos = state

        # Track last state change (computed position changes)
        self.explainer.note_state(state, reason, self.clock.utcnow())

        # Track cover state changes (manual or integration-initiated)
        if had_cover_state_change and self.state_change_data:
            event = self.state_change_data
            if event and event.new_state:
                pos_attr = (
                    "current_tilt_position"
                    if self._cover_type == "cover_tilt"
                    else "current_position"
                )
                self.explainer.note_cover_report(
                    event.new_state.attributes.get(pos_attr),
                    event.old_state.attributes.get(pos_attr)
                    if event.old_state
                    else None,
                    state,
                    "Manual override" if self.manager.binary_cover_manual else reason,
                    self.clock.utcnow(),
                )

        last_change = self.explainer.last_change
        return AdaptiveCoverData(
            climate_mode_toggle=self.switch_mode,
            states={
                "state": state,
                "start": start,
                "end": end,
                "control": self.control_method,
                "sun_motion": normal_cover.valid,
                "manual_override": self.manager.binary_cover_manual,
                "manual_list": self.manager.manual_controlled,
                "state_reason": reason,
                "next_change_event": next_event_name,
                "next_change_time": next_event_time,
                "next_change_position": next_event_pos,
                "last_change_old": last_change["old_position"],
                "last_change_new": last_change["new_position"],
                "last_change_time": last_change["time"],
                "last_change_reason": last_change["reason"],
            },
            attributes=self.explainer.attributes(
                options,
                active_decision,
                self._gate_blocks,
                self.entities,
                {
                    "azimuth": cover_data.sol_azi,
                    "elevation": cover_data.sol_elev,
                    "gamma": cover_data.gamma,
                    "in_fov": bool(cover_data.valid),
                    "window_azimuth": cover_data.win_azi,
                    "fov_left": cover_data.fov_left,
                    "fov_right": cover_data.fov_right,
                    "min_elevation": cover_data.min_elevation,
                    "max_elevation": cover_data.max_elevation,
                },
                cached_timezone(self.hass.config.time_zone),
            ),
        )

    async def async_handle_state_change(self, state: int):
        """Handle state change from tracked entities (Mode off: no moves)."""
        if self.control_toggle:
            for cover in self.entities:
                await self.async_handle_call_service(cover, state)
        else:
            self.logger.debug("State change but control toggle is off")
        self.events.done(RefreshEvent.ENTITY_CHANGED)
        self.logger.debug("State change handled")

    async def async_handle_cover_state_change(self, state: int):
        """Handle state change from assigned covers."""
        event = self.state_change_data
        if event is not None and event.new_state is not None:
            pos_attr = (
                "current_tilt_position"
                if self._cover_type == "cover_tilt"
                else "current_position"
            )
            new_position = event.new_state.attributes.get(pos_attr)
            # A human just took over: record it with provenance
            if self.detector.landed(
                event.entity_id,
                event.new_state,
                new_position,
                state,
                self.controls,
                self.config,
            ):
                self.record_move_provenance(
                    event.entity_id,
                    new_position,
                    "manual",
                    "manual change detected",
                )
        self.events.done(RefreshEvent.COVER_CHANGED)
        self.logger.debug("Cover state change handled")

    async def async_handle_first_refresh(self, state: int):
        """Handle first refresh."""
        if self.control_toggle is None:
            # The first refresh runs before the switch platform restores,
            # so the toggle is not known yet. Consuming the one-shot flag
            # here silently skipped startup positioning; keep it pending —
            # the switch's restore triggers another refresh that lands
            # here with the toggle resolved.
            self.logger.debug("First refresh deferred: control switch not restored yet")
            return
        if self.control_toggle:
            for cover in self.entities:
                if (
                    self.check_adaptive_time
                    and not self.manager.is_cover_manual(cover)
                    and self.gates.position_delta_ok(
                        cover, self._get_current_position(cover), state, self.config
                    )
                ):
                    await self.async_set_position(
                        cover, state, source="startup", reason=self._active_intent()
                    )
        else:
            self.logger.debug("First refresh but control toggle is off")
        self.events.done(RefreshEvent.STARTUP)
        self.logger.debug("First refresh handled")

    async def async_handle_timed_refresh(self, options):
        """Handle timed refresh."""
        self.logger.debug(
            "This is a timed refresh, using sunset position: %s",
            options.get(CONF_SUNSET_POS),
        )
        if self.control_toggle is None:
            # Startup/reload race: the timed close (or its catch-up) fired
            # before the switch platform restored the control toggle.
            # Keep END_TIME and the catch-up flag pending — the
            # switch's restore refresh completes the close.
            self.logger.debug("Timed refresh deferred: control switch not restored yet")
            return
        if self.control_toggle:
            await self.end_of_day.close(
                self.entities,
                options.get(CONF_SUNSET_POS),
                self._transform_state,
                self.manager.is_cover_manual,
                self._send_end_close,
            )
        else:
            self.logger.debug("Timed refresh but control toggle is off")
        self.end_of_day.finish()
        self.events.done(RefreshEvent.END_TIME)
        self.logger.debug("Timed refresh handled")

    async def _send_end_close(self, cover: str, target: int) -> bool:
        """Send the end-of-day close to one cover; False when undelivered."""
        return await self.async_set_manual_position(
            cover,
            target,
            source="end_time",
            reason="configured end time reached",
        )

    async def async_handle_call_service(self, entity, state: int):
        """Handle call service."""
        gate = self.gates.first_blocking_gate(
            entity,
            state,
            self.config,
            CoverFacts(
                is_manual=lambda: self.manager.is_cover_manual(entity),
                awaiting_target=lambda: self.commands.awaiting_target(entity),
                in_time_window=lambda: self.check_adaptive_time,
                position=lambda: self._get_current_position(entity),
                last_command=lambda: self.commands.target_call_time.get(entity),
            ),
            now=self.clock.utcnow(),
            now_local=self._now_local(),
        )
        self._gate_blocks[entity] = gate
        if gate is None:
            await self.async_set_position(
                entity, state, source="adaptive", reason=self._active_intent()
            )
        else:
            self.logger.debug(
                "Move of %s to %s blocked by gate: %s", entity, state, gate
            )

    async def async_force_apply(
        self, source: str = "user", reason: str | None = None
    ) -> None:
        """Apply calculated positions NOW, bypassing all rate gates.

        Human-initiated actions (reset buttons, mode changes, control
        toggles) are never throttled: deltas, time throttle, quiet hours,
        and move budget do not apply. Manual overrides and the timing
        window are still respected.
        """
        if not self.control_toggle:
            return
        for entity in self.entities:
            if not self.manager.is_cover_manual(entity) and self.check_adaptive_time:
                await self.async_set_position(
                    entity, self.state, source=source, reason=reason
                )

    async def async_set_position(
        self, entity, state: int, source: str = "adaptive", reason: str | None = None
    ):
        """Call service to set cover position."""
        await self.async_set_manual_position(entity, state, source, reason)

    async def async_set_manual_position(
        self, entity, state, source: str = "integration", reason: str | None = None
    ) -> bool:
        """Call service to set cover position.

        Returns True when the command was delivered (or the cover is
        already in position), False when delivery failed — e.g. the device
        is unavailable — so one-shot moves (end-of-day close) can retry.
        """
        # get_safe_state() maps unknown/unavailable/missing all to None, so
        # the old `in ("unavailable", "unknown")` check never fired: missing
        # covers (renamed or removed) were commanded on every tick. Read the
        # raw state. "unknown" stays commandable - a shade that has not
        # reported since a restart must still get the end-of-day close.
        current = self.hass.states.get(entity)
        if current is None and er.async_get(self.hass).async_get(entity):
            # Registered but not set up yet (e.g. Zigbee still starting at
            # boot): not an error. Command it when its first state arrives.
            self.logger.debug("%s has no state yet; waiting for it", entity)
            return False
        if current is None:
            if entity not in self._missing_warned:
                self._missing_warned.add(entity)
                self.logger.warning(
                    "Cannot command %s: no such entity (renamed or removed? "
                    "update this window's cover)",
                    entity,
                )
            return False
        self._missing_warned.discard(entity)
        if current.state == STATE_UNAVAILABLE:
            self.logger.warning(
                "Cannot command %s to %s: entity is unavailable", entity, state
            )
            return False
        if self.check_position(entity, state):
            service = SERVICE_SET_COVER_POSITION
            service_data = {}
            service_data[ATTR_ENTITY_ID] = entity

            if self._cover_type == "cover_tilt":
                service = SERVICE_SET_COVER_TILT_POSITION
                service_data[ATTR_TILT_POSITION] = state
            else:
                service_data[ATTR_POSITION] = state

            self.commands.start(entity, state)
            self.logger.debug("Run %s with data %s", service, service_data)
            ctx = Context()
            self.commands.remember_context(ctx.id)
            try:
                # blocking=True so a failing device raises HERE, not in a
                # fire-and-forget background task we can never observe.
                await self.hass.services.async_call(
                    COVER_DOMAIN, service, service_data, context=ctx, blocking=True
                )
            except Exception:  # noqa: BLE001 - a dead device must not kill the loop
                self.logger.warning(
                    "Could not deliver %s=%s to %s (device unavailable?)",
                    service,
                    state,
                    entity,
                )
                self.commands.failed(entity, state, source, reason)
                return False
            self.commands.delivered(entity)
            self.gates.record_move(entity, self.clock.utcnow(), self.config)
            self.record_move_provenance(entity, state, source, reason)
            self.commands.schedule_arrival_poll(entity)
        return True

    def _adopt_late_delivery(self, entity_id: str) -> bool:
        """Adopt motion toward a send that raised as our own travel.

        See CommandTracker.adopt_late_delivery; an adopted send is logged
        and polled like a delivered command. Returns True when adopted.
        """
        change = self.state_change_data
        if change is None or change.new_state is None or change.old_state is None:
            return False
        sent = self.commands.adopt_late_delivery(
            entity_id,
            change.new_state.state,
            change.old_state.attributes.get(
                "current_tilt_position"
                if self._cover_type == "cover_tilt"
                else "current_position"
            ),
        )
        if sent is None:
            return False
        self.gates.record_move(entity_id, self.clock.utcnow(), self.config)
        self.record_move_provenance(
            entity_id,
            sent.target,
            sent.source,
            f"{sent.reason} (delivered late)" if sent.reason else "delivered late",
        )
        self.commands.schedule_arrival_poll(entity_id)
        return True

    async def _force_poll(self, entity: str) -> None:
        """Ask Home Assistant for a fresh state of ``entity`` (best effort)."""
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "update_entity",
                {ATTR_ENTITY_ID: entity},
            )
        except Exception:  # noqa: BLE001 - poll is best-effort
            self.logger.debug("Forced poll failed for %s", entity)

    def record_move_provenance(
        self, entity, position, source: str, reason: str | None = None
    ) -> None:
        """Append to the per-cover move log and fire a logbook event.

        Answers "what moved this cover and why": source is adaptive /
        startup / end_time / control_enabled / all_covers / hold / manual, with
        the driving intent as reason where known.
        """
        entry = self.explainer.record(
            entity, position, source, reason, self.clock.utcnow()
        )
        bus = getattr(self.hass, "bus", None)
        if bus is not None:  # bare test harnesses have no event bus
            bus.async_fire("adaptive_cover_moved", {"entity_id": entity, **entry})

    def _active_intent(self) -> str | None:
        """Intent of the currently-active decision, for provenance."""
        decision = (
            self._climate_decision if self.controls.climate else self._basic_decision
        )
        return str(decision.intent) if decision else None

    def _update_options(self, options):
        """Re-read the options this refresh uses."""
        self.config = ShadeConfig.from_options(options)
        self._warn_if_threshold_unit_looks_wrong(options)

    @property
    def entities(self) -> list[str]:
        """The covers this window drives (the hub reads this too)."""
        return self.config.entities

    def _warn_if_threshold_unit_looks_wrong(self, options) -> None:
        """Warn once when climate thresholds look like the other unit.

        Thresholds are read in HA's configured temperature unit. 21 in a
        °F house (or 72 in a °C house) silently pins the season.
        """
        if getattr(self, "_threshold_unit_warned", False):
            return
        if not options.get(CONF_CLIMATE_MODE):
            return
        units = getattr(getattr(self.hass, "config", None), "units", None)
        unit = getattr(units, "temperature_unit", None)
        suspicious = []
        for key in (CONF_TEMP_LOW, CONF_TEMP_HIGH):
            value = options.get(key)
            if value is None:
                continue
            if unit == "°F" and value < 45:
                suspicious.append(f"{key}={value}")
            elif unit == "°C" and value > 45:
                suspicious.append(f"{key}={value}")
        if suspicious:
            self._threshold_unit_warned = True
            self.logger.warning(
                "Climate thresholds %s look like the wrong unit: they are "
                "compared in Home Assistant's unit (%s). Update them in the "
                "options or with adaptive_cover.change_settings.",
                ", ".join(suspicious),
                unit,
            )

    def _update_manager_and_covers(self):
        self.manager.set_duration(self.config.manual_duration)
        self.manager.add_covers(self.entities)
        # Only an EXPLICIT off clears overrides. During startup/reload the
        # toggle is still None (switches restore after the first refresh),
        # and treating that as off wiped overrides on every options edit.
        # A requested hold (Mode hold, the hold service) is not a detected
        # move, so it survives detection being off.
        if self.controls.clears_overrides:
            self.logger.debug("Manual toggle is off, clearing all manual overrides")
            self.manager.reset_detected()

    def get_blind_data(self, options=None):
        """Build the cover adapter for this window's type.

        From this refresh's options, or from ``options`` when given.
        """
        geometry = (
            self.config.geometry
            if options is None
            else ShadeConfig.from_options(options).geometry
        )
        return build_cover(
            self._cover_type,
            self.hass,
            self.logger,
            geometry,
            sun=self.pos_sun,
            timezone=self.hass.config.time_zone,
            clock=self.clock,
        )

    def _now_local(self) -> dt.datetime:
        """Naive wall time in HA's CONFIGURED timezone.

        Never use bare datetime.now() for schedule math: it reads the
        PROCESS timezone, which differs from HA's configured one on
        common deployments (docker defaults to UTC) and silently shifts
        every start/end/quiet window by the offset.
        """
        tz = cached_timezone(self.hass.config.time_zone)
        return self.clock.now(tz).replace(tzinfo=None)

    @property
    def check_adaptive_time(self):
        """Check if time is within start and end times."""
        return self.schedule.in_window(self.config, self._now_local())

    @property
    def _end_time(self) -> dt.datetime | None:
        """Get end time (naive, in HA's configured timezone, today)."""
        return self.schedule.end_time(self.config, self._now_local().date())

    def _get_current_position(self, entity) -> int | None:
        """Get current position of cover."""
        if self._cover_type == "cover_tilt":
            return get_safe_attr(self.hass, entity, "current_tilt_position")
        return get_safe_attr(self.hass, entity, "current_position")

    def check_position(self, entity, state):
        """Check if position is different as state.

        Unknown position (unavailable device, missing attribute) means we
        cannot prove the cover is in place — send the command. Returning
        False here silently dropped one-shot moves like the end-of-day
        close whenever a device napped at the wrong moment.
        """
        position = self._get_current_position(entity)
        if position is not None:
            return position != state
        self.logger.debug("Position of %s unknown; commanding %s anyway", entity, state)
        return True

    @property
    def pos_sun(self):
        """Fetch information for sun position."""
        return [
            get_safe_attr(self.hass, "sun.sun", "azimuth"),
            get_safe_attr(self.hass, "sun.sun", "elevation"),
        ]

    def _climate_data(self) -> ClimateCoverData:
        """Build the climate adapter from the options and switch toggles.

        The season is sticky from the one the previous decision found.
        """
        return ClimateCoverData.from_config(
            self.hass,
            self.logger,
            self.config.climate,
            self.controls,
            self._cover_type,
            previous_season=self._season,
        )

    def climate_mode_data(self, options, cover_data):
        """Update climate mode data and control method."""
        climate = self._climate = self._climate_data()
        self._season = climate.season
        self._climate_decision = ClimateCoverState(cover_data, climate).get_decision()
        self.climate_state = round(self._climate_decision.position)
        # Winter wins if both held (it was the later assignment); neither,
        # or the climate switch off, is intermediate again.
        if climate.is_winter and self.switch_mode:
            self.control_method = "winter"
        elif climate.is_summer and self.switch_mode:
            self.control_method = "summer"
        else:
            self.control_method = "intermediate"
        self.logger.debug(
            "Climate mode control method was set to %s", self.control_method
        )

    @property
    def state(self) -> int:
        """Handle the output of the state based on mode."""
        # An interpolated position is a float, as it always was; callers
        # treat it as int (tracked in the pyright baseline before P4).
        return self.decider.position(  # pyright: ignore[reportReturnType]
            self.default_state, self.climate_state, self.controls.climate, self.config
        )

    def _transform_state(self, state):
        """Apply interpolation / inversion output transforms."""
        return self.decider.transform(state, self.config)

    # The switch platform sets these by name (setattr); the state lives in
    # self.controls.
    switch_mode = ControlToggle[bool]("climate")
    """Let switch toggle climate mode."""
    temp_toggle = ControlToggle[bool | None]("outside_temp")
    """Let switch toggle between inside or outside temperature."""
    control_toggle = ControlToggle[bool | None]("control")
    """Automatic control: False is Mode off (the Mode select sets it)."""
    manual_toggle = ControlToggle[bool | None]("manual")
    """Toggle manual-override detection."""
    lux_toggle = ControlToggle[bool | None]("lux")
    irradiance_toggle = ControlToggle[bool | None]("irradiance")
