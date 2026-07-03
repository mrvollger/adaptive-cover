"""The Coordinator for Adaptive Cover."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import deque
from dataclasses import dataclass

import numpy as np
import pytz
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_SET_COVER_POSITION,
    SERVICE_SET_COVER_TILT_POSITION,
)
from homeassistant.core import (
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config_context_adapter import ConfigContextAdapter

from .calculation import (
    AdaptiveHorizontalCover,
    AdaptiveTiltCover,
    AdaptiveVerticalCover,
    ClimateCoverData,
    ClimateCoverState,
    NormalCoverState,
    build_day_forecast,
    get_state_reason,
)
from .engine.models import GlareModel, Overhang, PrivacyConfig
from .const import (
    _LOGGER,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_BLIND_SPOT_ELEVATION,
    CONF_BLIND_SPOT_LEFT,
    CONF_BLIND_SPOT_RIGHT,
    CONF_CLIMATE_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENABLE_BLIND_SPOT,
    CONF_ENABLE_MAX_POSITION,
    CONF_ENABLE_MIN_POSITION,
    CONF_END_ENTITY,
    CONF_END_TIME,
    CONF_ENTITIES,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_INTERP,
    CONF_INTERP_END,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
    CONF_INTERP_START,
    CONF_INVERSE_STATE,
    CONF_IRRADIANCE_ENTITY,
    CONF_IRRADIANCE_THRESHOLD,
    CONF_LENGTH_AWNING,
    CONF_LUX_ENTITY,
    CONF_LUX_THRESHOLD,
    CONF_MANUAL_IGNORE_INTERMEDIATE,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MANUAL_THRESHOLD,
    CONF_MAX_ELEVATION,
    CONF_MAX_MOVES_HOUR,
    CONF_MAX_POSITION,
    CONF_MIN_ELEVATION,
    CONF_MIN_POSITION,
    CONF_OCCUPIED_DISTANCE,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_EYE_HEIGHT,
    CONF_PRIVACY_MODE,
    CONF_PRIVACY_OFFSET,
    CONF_PRIVACY_POSITION,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_OUTSIDE_THRESHOLD,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_PRESENCE_ENTITY,
    CONF_RETURN_SUNSET,
    CONF_START_ENTITY,
    CONF_START_TIME,
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    CONF_TRANSPARENT_BLIND,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_STATE,
    DOMAIN,
    LOGGER,
)
from .helpers import (
    get_datetime_from_str,
    get_last_updated,
    get_safe_attr,
    get_safe_state,
)


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
    MOVE_LOG_LIMIT = 10
    # Wait-for-target: covers rarely land exactly on the commanded value
    # (99 when told 100), and a latch that never clears swallows every
    # subsequent HUMAN move - adaptive then reverts people within minutes.
    TARGET_TOLERANCE = 3  # percent: close enough counts as arrived
    TARGET_TIMEOUT = dt.timedelta(seconds=120)  # travel-time upper bound

    def __init__(self, hass: HomeAssistant) -> None:  # noqa: D107
        super().__init__(hass, LOGGER, name=DOMAIN)

        self.logger = ConfigContextAdapter(_LOGGER)
        self.logger.set_config_name(self.config_entry.data.get("name"))
        self._cover_type = self.config_entry.data.get("sensor_type")
        self._climate_mode = self.config_entry.options.get(CONF_CLIMATE_MODE, False)
        self._switch_mode = True if self._climate_mode else False
        self._inverse_state = self.config_entry.options.get(CONF_INVERSE_STATE, False)
        self._use_interpolation = self.config_entry.options.get(CONF_INTERP, False)
        self._track_end_time = self.config_entry.options.get(CONF_RETURN_SUNSET)
        self._temp_toggle = None
        self._control_toggle = None
        self._manual_toggle = None
        self._lux_toggle = None
        self._irradiance_toggle = None
        self._start_time = None
        self._sun_end_time = None
        self._sun_start_time = None
        # self._end_time = None
        self.manual_reset = self.config_entry.options.get(
            CONF_MANUAL_OVERRIDE_RESET, False
        )
        self.manual_duration = self.config_entry.options.get(
            CONF_MANUAL_OVERRIDE_DURATION, {"minutes": 15}
        )
        self.state_change = False
        self.cover_state_change = False
        self.first_refresh = False
        self.timed_refresh = False
        self.climate_state = None
        self.control_method = "intermediate"
        self.state_change_data: StateChangedData | None = None
        self.manager = AdaptiveCoverManager(self.manual_duration, self.logger)
        self.wait_for_target = {}
        self.target_call = {}
        self.target_call_time: dict[str, dt.datetime] = {}
        self._our_context_ids: deque[str] = deque(maxlen=64)
        self._sun_table = None
        self._poll_cancels: dict[str, object] = {}
        self.ignore_intermediate_states = self.config_entry.options.get(
            CONF_MANUAL_IGNORE_INTERMEDIATE, False
        )
        self._update_listener = None
        self._scheduled_time = dt.datetime.now()

        self._cached_options = None
        self._previous_state = None
        self._move_history: dict[str, list[dt.datetime]] = {}
        self._basic_decision = None
        self._climate_decision = None
        self.forecast: list[dict] | None = None
        self._forecast_key = "___unset___"
        self._gate_blocks: dict[str, str | None] = {}
        self.move_log: dict[str, list[dict]] = {}
        self._last_change_data = {
            "old_position": None,
            "new_position": None,
            "time": None,
            "reason": None,
        }

    async def async_config_entry_first_refresh(self) -> None:
        """Config entry first refresh."""
        self.first_refresh = True
        await super().async_config_entry_first_refresh()
        self.logger.debug("Config entry first refresh")

    async def async_timed_refresh(self, event) -> None:
        """Control state at end time."""

        now = dt.datetime.now()
        if self.end_time is not None:
            time = self.end_time
        if self.end_time_entity is not None:
            time = get_safe_state(self.hass, self.end_time_entity)

        self.logger.debug("Checking timed refresh. End time: %s, now: %s", time, now)

        time_check = now - get_datetime_from_str(time)
        if time is not None and (time_check <= dt.timedelta(seconds=1)):
            self.timed_refresh = True
            self.logger.debug("Timed refresh triggered")
            await self.async_refresh()
        else:
            self.logger.debug("Timed refresh, but: not equal to end time")

    async def async_check_entity_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Fetch and process state change event."""
        self.logger.debug("Entity state change")
        self.state_change = True
        await self.async_request_refresh()

    async def async_check_cover_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Fetch and process state change event."""
        self.logger.debug("Cover state change")
        data = event.data
        if data["old_state"] is None:
            self.logger.debug("Old state is None")
            return
        if data["new_state"] is None:
            self.logger.debug("New state is None")
            return
        self.state_change_data = StateChangedData(
            data["entity_id"], data["old_state"], data["new_state"]
        )
        if self.state_change_data.old_state.state in ("unknown", "unavailable"):
            self.logger.debug("Old state is %s, not processing", self.state_change_data.old_state.state)
            return
        if self.state_change_data.new_state.state in ("unknown", "unavailable"):
            self.logger.debug("New state is %s, not processing", self.state_change_data.new_state.state)
            return
        entity_id = data["entity_id"]
        # Our own command echoing back (service context preserved):
        # bookkeeping only - never manual, never a full refresh.
        if (
            event.context is not None
            and event.context.id in self._our_context_ids
        ):
            self.process_entity_state_change()
            return
        # A change carrying a user id is a HUMAN act (dashboard click,
        # user-run service): it always counts as manual - clear any travel
        # window so it can never be swallowed as a motor echo.
        if event.context is not None and event.context.user_id is not None:
            self.wait_for_target[entity_id] = False
        # Foreign movement STARTING (opening/closing we didn't command) is a
        # human act the moment the motor spins. These shades report position
        # only at journey end, so waiting for the landing report leaves a
        # 1-3 minute window where the cover reads as auto-controlled while a
        # person is actively moving it.
        new_state = self.state_change_data.new_state
        if (
            new_state.state in ("opening", "closing")
            and not self.ignore_intermediate_states
            and not self.wait_for_target.get(entity_id)
            and self.manual_toggle
            and self.control_toggle
            and entity_id in self.manager.covers
            and not self.manager.is_cover_manual(entity_id)
        ):
            self.logger.debug(
                "Foreign %s movement started for %s: latching manual immediately",
                new_state.state,
                entity_id,
            )
            self.manager.mark_manual_control(entity_id)
            self.manager.set_last_updated(entity_id, new_state, self.manual_reset)
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
        self.process_entity_state_change()
        if self.wait_for_target.get(entity_id):
            return
        self.cover_state_change = True
        await self.async_refresh()

    def process_entity_state_change(self):
        """Process state change event."""
        event = self.state_change_data
        self.logger.debug("Processing state change event: %s", event)
        entity_id = event.entity_id
        if self.ignore_intermediate_states and event.new_state.state in [
            "opening",
            "closing",
        ]:
            self.logger.debug("Ignoring intermediate state change for %s", entity_id)
            return
        if self.wait_for_target.get(entity_id):
            position = event.new_state.attributes.get(
                "current_position"
                if self._cover_type != "cover_tilt"
                else "current_tilt_position"
            )
            target = self.target_call.get(entity_id)
            arrived = (
                position is not None
                and target is not None
                and abs(position - target) <= self.TARGET_TOLERANCE
            )
            sent_at = self.target_call_time.get(entity_id)
            expired = (
                sent_at is None
                or dt.datetime.now(dt.UTC) - sent_at > self.TARGET_TIMEOUT
            )
            if arrived:
                self.wait_for_target[entity_id] = False
                self.logger.debug(
                    "Position %s within tolerance of target %s for %s",
                    position,
                    target,
                    entity_id,
                )
            elif expired:
                # Motor had ample time; whatever moves now is a human.
                self.wait_for_target[entity_id] = False
                self.logger.debug(
                    "Target wait expired for %s (at %s, wanted %s); "
                    "treating changes as manual",
                    entity_id,
                    position,
                    target,
                )
            self.logger.debug("Wait for target: %s", self.wait_for_target)
        else:
            self.logger.debug("No wait for target call for %s", entity_id)

    @callback
    def _async_cancel_update_listener(self) -> None:
        """Cancel the scheduled update."""
        if self._update_listener:
            self._update_listener()
            self._update_listener = None

    async def async_timed_end_time(self) -> None:
        """Control state at end time."""
        self.logger.debug("Scheduling end time update at %s", self._end_time)
        self._async_cancel_update_listener()
        self.logger.debug(
            "End time: %s, Track end time: %s, Scheduled time: %s, Condition: %s",
            self._end_time,
            self._track_end_time,
            self._scheduled_time,
            self._end_time > self._scheduled_time,
        )
        self._update_listener = async_track_point_in_time(
            self.hass, self.async_timed_refresh, self._end_time
        )
        self._scheduled_time = self._end_time

    def _predict_position_at_time(self, cover_data, target_time):
        """Predict cover position at a specific future time using sun data."""
        if self._sun_table is not None:
            times, azimuths, elevations = self._sun_table
        else:
            sun_data = cover_data.sun_data
            times = sun_data.times
            azimuths = sun_data.solar_azimuth
            elevations = sun_data.solar_elevation
        _ = times
        # Convert target_time to same timezone as sun data times for correct indexing
        target_tz = target_time
        if times.tz is not None and target_time.tzinfo is not None:
            target_tz = target_time.astimezone(times.tz)
        idx = times.get_indexer([target_tz], method="nearest")[0]
        if idx < 0 or idx >= len(times):
            return int(cover_data.h_def)
        return cover_data.calculate_percentage_at(azimuths[idx], elevations[idx])

    def _make_utc(self, time):
        """Ensure a datetime is UTC-aware."""
        if time is None:
            return None
        if time.tzinfo is None:
            return time.replace(tzinfo=pytz.UTC)
        return time

    def _compute_next_event(self, cover_data, start, end):
        """Find the next significant cover state change event."""
        now = dt.datetime.now(pytz.UTC)
        tomorrow = now.date() + dt.timedelta(days=1)
        location = cover_data.sun_data.location
        events = []

        # Sun enters FOV
        if start is not None:
            start_utc = self._make_utc(start)
            if start_utc > now:
                predicted_pos = self._predict_position_at_time(cover_data, start_utc)
                events.append(("Sun enters window", start_utc, predicted_pos))

        # Sun leaves FOV
        if end is not None:
            end_utc = self._make_utc(end)
            if end_utc > now:
                events.append(("Sun leaves window", end_utc, int(cover_data.h_def)))

        # Sunset + offset (today, then tomorrow if past)
        try:
            sunset_raw = cover_data.sun_data.sunset()
            sunset_utc = self._make_utc(sunset_raw)
            sunset_time = sunset_utc + dt.timedelta(minutes=cover_data.sunset_off)
            if sunset_time <= now:
                sunset_raw = location.sunset(tomorrow, local=False)
                sunset_utc = self._make_utc(sunset_raw)
                sunset_time = sunset_utc + dt.timedelta(minutes=cover_data.sunset_off)
            if sunset_time > now:
                events.append(("Sunset + offset", sunset_time, int(cover_data.sunset_pos)))
        except Exception:  # noqa: BLE001
            self.logger.debug("Could not compute sunset event", exc_info=True)

        # Sunrise + offset (today, then tomorrow if past)
        try:
            sunrise_raw = cover_data.sun_data.sunrise()
            sunrise_utc = self._make_utc(sunrise_raw)
            sunrise_time = sunrise_utc + dt.timedelta(minutes=cover_data.sunrise_off)
            if sunrise_time <= now:
                sunrise_raw = location.sunrise(tomorrow, local=False)
                sunrise_utc = self._make_utc(sunrise_raw)
                sunrise_time = sunrise_utc + dt.timedelta(minutes=cover_data.sunrise_off)
            if sunrise_time > now:
                events.append(("Sunrise + offset", sunrise_time, int(cover_data.h_def)))
        except Exception:  # noqa: BLE001
            self.logger.debug("Could not compute sunrise event", exc_info=True)

        # Configured end time (_end_time is naive local time from config)
        if self._end_time is not None and self._track_end_time:
            end_t = self._end_time
            if end_t.tzinfo is None:
                local_tz = pytz.timezone(self.hass.config.time_zone)
                end_t = local_tz.localize(end_t)
            if end_t > now:
                events.append((
                    "Configured end time",
                    end_t,
                    self.config_entry.options.get(CONF_SUNSET_POS, cover_data.sunset_pos),
                ))

        # Manual override expires
        if self.manager.binary_cover_manual:
            for override_time in self.manager.manual_control_time.values():
                expire_time = override_time + self.manager.reset_duration
                if expire_time > now:
                    events.append((
                        "Manual override expires",
                        expire_time,
                        None,  # position will be the current computed state
                    ))

        if not events:
            return None

        events.sort(key=lambda e: e[1])
        return events[0]

    async def _async_update_data(self) -> AdaptiveCoverData:
        self.logger.debug("Updating data")
        if self.first_refresh:
            self._cached_options = self.config_entry.options

        options = self.config_entry.options
        self._update_options(options)

        # Get data for the blind
        cover_data = self.get_blind_data(options=options)

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

        if (
            self._end_time
            and self._track_end_time
            and self._end_time > self._scheduled_time
        ):
            await self.async_timed_end_time()

        # Capture flags before handlers reset them
        had_cover_state_change = self.cover_state_change

        # Handle types of changes
        if self.state_change:
            await self.async_handle_state_change(state, options)
        if self.cover_state_change:
            await self.async_handle_cover_state_change(state)
        if self.first_refresh:
            await self.async_handle_first_refresh(state, options)
        if self.timed_refresh:
            await self.async_handle_timed_refresh(options)

        normal_cover = self.normal_cover_state.cover
        # Climate snapshot used for reasons, forecasting, and trace
        climate_data_for_reason = None
        if self._climate_mode and self._switch_mode:
            try:
                climate_data_for_reason = ClimateCoverData(
                    *self.get_climate_data(options)
                )
            except Exception:  # noqa: BLE001
                climate_data_for_reason = None

        # Run the solar_times method in a separate thread
        solar_day_stale = (
            self.first_refresh
            or self._sun_start_time is None
            or dt.datetime.now(pytz.UTC).date() != self._sun_start_time.date()
        )
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
        forecast_key = None
        if climate_data_for_reason is not None:
            try:
                forecast_key = repr(climate_data_for_reason.to_inputs())
            except Exception:  # noqa: BLE001
                forecast_key = None
        if solar_day_stale or forecast_key != self._forecast_key:
            loop = asyncio.get_event_loop()
            try:
                raw_forecast = await loop.run_in_executor(
                    None, build_day_forecast, cover_data, climate_data_for_reason
                )
                self.forecast = [
                    {**entry, "position": int(self._transform_state(entry["position"]))}
                    for entry in raw_forecast
                ]
            except Exception:  # noqa: BLE001
                self.logger.debug("Forecast build failed", exc_info=True)
                self.forecast = None
            self._forecast_key = forecast_key

        # Compute state reason
        reason = get_state_reason(cover_data, climate_data_for_reason)
        if self.manager.binary_cover_manual:
            reason = "Manual override"

        # Active decision (intent + trace) for explanations
        active_decision = (
            self._climate_decision if self._switch_mode else self._basic_decision
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
        if self._previous_state is not None and self._previous_state != state:
            self._last_change_data = {
                "old_position": self._previous_state,
                "new_position": state,
                "time": dt.datetime.now(pytz.UTC),
                "reason": reason,
            }
        self._previous_state = state

        # Track cover state changes (manual or integration-initiated)
        if had_cover_state_change and self.state_change_data:
            event = self.state_change_data
            if event and event.new_state:
                pos_attr = (
                    "current_tilt_position"
                    if self._cover_type == "cover_tilt"
                    else "current_position"
                )
                new_pos = event.new_state.attributes.get(pos_attr)
                old_pos = (
                    event.old_state.attributes.get(pos_attr)
                    if event.old_state
                    else None
                )
                if new_pos is not None:
                    change_reason = (
                        "Manual override"
                        if self.manager.binary_cover_manual
                        else reason
                    )
                    self._last_change_data = {
                        "old_position": old_pos if old_pos is not None else state,
                        "new_position": new_pos,
                        "time": dt.datetime.now(pytz.UTC),
                        "reason": change_reason,
                    }

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
                "last_change_old": self._last_change_data["old_position"],
                "last_change_new": self._last_change_data["new_position"],
                "last_change_time": self._last_change_data["time"],
                "last_change_reason": self._last_change_data["reason"],
            },
            attributes={
                "default": options.get(CONF_DEFAULT_HEIGHT),
                "sunset_default": options.get(CONF_SUNSET_POS),
                "sunset_offset": options.get(CONF_SUNSET_OFFSET),
                "azimuth_window": options.get(CONF_AZIMUTH),
                "field_of_view": [
                    options.get(CONF_FOV_LEFT),
                    options.get(CONF_FOV_RIGHT),
                ],
                "blind_spot": options.get(CONF_BLIND_SPOT_ELEVATION),
                "intent": str(active_decision.intent) if active_decision else None,
                "decision_trace": list(active_decision.trace)
                if active_decision
                else None,
                "forecast_today": self.forecast,
                "move_blocked_by": {
                    entity: gate
                    for entity, gate in self._gate_blocks.items()
                    if gate
                },
                "last_moves": {
                    entity: line
                    for entity in self.entities
                    if (line := self._format_last_move(entity)) is not None
                },
                "sun": {
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
            },
        )

    async def async_handle_state_change(self, state: int, options):
        """Handle state change from tracked entities."""
        if self.control_toggle:
            for cover in self.entities:
                await self.async_handle_call_service(cover, state, options)
        else:
            self.logger.debug("State change but control toggle is off")
        self.state_change = False
        self.logger.debug("State change handled")

    async def async_handle_cover_state_change(self, state: int):
        """Handle state change from assigned covers."""
        event = self.state_change_data
        was_manual = (
            self.manager.is_cover_manual(event.entity_id) if event else False
        )
        if self.manual_toggle and self.control_toggle:
            self.manager.handle_state_change(
                self.state_change_data,
                state,
                self._cover_type,
                self.manual_reset,
                self.wait_for_target,
                self.manual_threshold,
            )
        # A human just took over: record it with provenance
        if (
            event
            and not was_manual
            and self.manager.is_cover_manual(event.entity_id)
        ):
            pos_attr = (
                "current_tilt_position"
                if self._cover_type == "cover_tilt"
                else "current_position"
            )
            new_position = (
                event.new_state.attributes.get(pos_attr)
                if event.new_state
                else None
            )
            self.record_move_provenance(
                event.entity_id,
                new_position,
                "manual",
                "manual change detected",
            )
        self.cover_state_change = False
        self.logger.debug("Cover state change handled")

    async def async_handle_first_refresh(self, state: int, options):
        """Handle first refresh."""
        if self.control_toggle:
            for cover in self.entities:
                if (
                    self.check_adaptive_time
                    and not self.manager.is_cover_manual(cover)
                    and self.check_position_delta(cover, state, options)
                ):
                    await self.async_set_position(
                        cover, state, source="startup", reason=self._active_intent()
                    )
        else:
            self.logger.debug("First refresh but control toggle is off")
        self.first_refresh = False
        self.logger.debug("First refresh handled")

    async def async_handle_timed_refresh(self, options):
        """Handle timed refresh."""
        self.logger.debug(
            "This is a timed refresh, using sunset position: %s",
            options.get(CONF_SUNSET_POS),
        )
        if self.control_toggle:
            for cover in self.entities:
                await self.async_set_manual_position(
                    cover,
                    (
                        inverse_state(options.get(CONF_SUNSET_POS))
                        if self._inverse_state
                        else options.get(CONF_SUNSET_POS)
                    ),
                    source="end_time",
                    reason="configured end time reached",
                )
        else:
            self.logger.debug("Timed refresh but control toggle is off")
        self.timed_refresh = False
        self.logger.debug("Timed refresh handled")

    async def async_handle_call_service(self, entity, state: int, options):
        """Handle call service."""
        gate = self._first_blocking_gate(entity, state, options)
        self._gate_blocks[entity] = gate
        if gate is None:
            await self.async_set_position(
                entity, state, source="adaptive", reason=self._active_intent()
            )
        else:
            self.logger.debug(
                "Move of %s to %s blocked by gate: %s", entity, state, gate
            )

    def _first_blocking_gate(self, entity, state: int, options) -> str | None:
        """Return the first gate that blocks this move, or None if allowed.

        Precedence (also the documented order): manual override > time
        window > position delta > time throttle > quiet hours > move budget.
        Exposed per cover in the 'move_blocked_by' attribute so 'why didn't
        it move?' is answerable from the UI.
        """
        if self.manager.is_cover_manual(entity):
            return "manual_override"
        if self.wait_for_target.get(entity):
            sent_at = self.target_call_time.get(entity)
            if (
                sent_at is not None
                and dt.datetime.now(dt.UTC) - sent_at <= self.TARGET_TIMEOUT
            ):
                # One command in flight is enough; never stack re-sends.
                return "awaiting_target"
            self.wait_for_target[entity] = False
        if not self.check_adaptive_time:
            return "outside_time_window"
        if not self.check_position_delta(entity, state, options):
            return "position_delta"
        if not self.check_time_delta(entity):
            return "time_throttle"
        if not self.check_quiet_hours(state, options):
            return "quiet_hours"
        if not self.check_move_budget(entity, state, options):
            return "move_budget"
        return None

    def _is_snap_position(self, state: int, options) -> bool:
        """Positions that always deserve a move (endpoints, rest positions)."""
        return state in [
            options.get(CONF_SUNSET_POS),
            options.get(CONF_DEFAULT_HEIGHT),
            options.get(CONF_PRIVACY_POSITION),
            0,
            100,
        ]

    def check_quiet_hours(self, state: int, options) -> bool:
        """Block tracking moves during the configured quiet window.

        Snap positions (fully open/closed, default, sunset, privacy) are
        allowed through: arriving at a rest position is the one move worth
        making at night.
        """
        if not self.quiet_start or not self.quiet_end:
            return True
        if self._is_snap_position(state, options):
            return True
        now = dt.datetime.now().time()
        start = get_datetime_from_str(self.quiet_start).time()
        end = get_datetime_from_str(self.quiet_end).time()
        if start <= end:
            quiet = start <= now < end
        else:  # window crosses midnight
            quiet = now >= start or now < end
        if quiet:
            self.logger.debug(
                "Quiet hours (%s-%s): skipping tracking move", start, end
            )
        return not quiet

    def check_move_budget(self, entity, state: int, options) -> bool:
        """Cap tracking moves per entity per hour (motor noise / wear).

        Snap positions bypass the budget so day-phase transitions always
        happen; only incremental tracking moves are rationed.
        """
        if not self.max_moves_hour:
            return True
        if self._is_snap_position(state, options):
            return True
        now = dt.datetime.now(dt.UTC)
        history = [
            t
            for t in self._move_history.get(entity, [])
            if now - t < dt.timedelta(hours=1)
        ]
        self._move_history[entity] = history
        if len(history) >= self.max_moves_hour:
            self.logger.debug(
                "Move budget (%s/h) exhausted for %s: skipping tracking move",
                self.max_moves_hour,
                entity,
            )
            return False
        return True

    def _record_move(self, entity) -> None:
        if self.max_moves_hour:
            self._move_history.setdefault(entity, []).append(
                dt.datetime.now(dt.UTC)
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
            if (
                not self.manager.is_cover_manual(entity)
                and self.check_adaptive_time
            ):
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
    ):
        """Call service to set cover position."""
        if self.check_position(entity, state):
            service = SERVICE_SET_COVER_POSITION
            service_data = {}
            service_data[ATTR_ENTITY_ID] = entity

            if self._cover_type == "cover_tilt":
                service = SERVICE_SET_COVER_TILT_POSITION
                service_data[ATTR_TILT_POSITION] = state
            else:
                service_data[ATTR_POSITION] = state

            self.wait_for_target[entity] = True
            self.target_call[entity] = state
            self.target_call_time[entity] = dt.datetime.now(dt.UTC)
            self.logger.debug(
                "Set wait for target %s and target call %s",
                self.wait_for_target,
                self.target_call,
            )
            self.logger.debug("Run %s with data %s", service, service_data)
            self._record_move(entity)
            self.record_move_provenance(entity, state, source, reason)
            ctx = Context()
            self._our_context_ids.append(ctx.id)
            await self.hass.services.async_call(
                COVER_DOMAIN, service, service_data, context=ctx
            )
            self._schedule_arrival_poll(entity)

    def _schedule_arrival_poll(self, entity) -> None:
        """Force a device poll if no landing report arrives in time.

        Zigbee shades drop attribute reports; without this the entity can
        sit 'closing' at a stale position for minutes, freezing manual
        detection and the dashboard alike.
        """
        if (cancel := self._poll_cancels.pop(entity, None)) is not None:
            cancel()

        async def _poll_if_silent(_now) -> None:
            self._poll_cancels.pop(entity, None)
            if not self.wait_for_target.get(entity):
                return  # arrived; nothing to do
            self.logger.debug(
                "No landing report from %s; forcing a state poll", entity
            )
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "update_entity",
                    {ATTR_ENTITY_ID: entity},
                )
            except Exception:  # noqa: BLE001 - poll is best-effort
                self.logger.debug("Forced poll failed for %s", entity)

        self._poll_cancels[entity] = async_call_later(
            self.hass,
            self.TARGET_TIMEOUT.total_seconds() + 5,
            _poll_if_silent,
        )

    def record_move_provenance(
        self, entity, position, source: str, reason: str | None = None
    ) -> None:
        """Append to the per-cover move log and fire a logbook event.

        Answers "what moved this cover and why": source is adaptive /
        startup / end_time / control_enabled / all_covers / manual, with
        the driving intent as reason where known.
        """
        entry = {
            "time": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "position": position,
            "source": source,
            "reason": reason,
        }
        log = self.move_log.setdefault(entity, [])
        log.append(entry)
        del log[: -self.MOVE_LOG_LIMIT]
        bus = getattr(self.hass, "bus", None)
        if bus is not None:  # bare test harnesses have no event bus
            bus.async_fire("adaptive_cover_moved", {"entity_id": entity, **entry})

    def _active_intent(self) -> str | None:
        """Intent of the currently-active decision, for provenance."""
        decision = (
            self._climate_decision if self._switch_mode else self._basic_decision
        )
        return str(decision.intent) if decision else None

    def _format_last_move(self, entity) -> str | None:
        """Compact 'HH:MM -> 37% (source: reason)' line for attributes."""
        log = self.move_log.get(entity)
        if not log:
            return None
        entry = log[-1]
        when = dt.datetime.fromisoformat(entry["time"]).astimezone()
        line = f"{when.strftime('%H:%M')} -> {entry['position']}% ({entry['source']}"
        if entry.get("reason"):
            line += f": {entry['reason']}"
        return line + ")"

    def _update_options(self, options):
        """Update options."""
        self.entities = options.get(CONF_ENTITIES, [])
        self.min_change = options.get(CONF_DELTA_POSITION, 1)
        self.time_threshold = options.get(CONF_DELTA_TIME, 2)
        self.start_time = options.get(CONF_START_TIME)
        self.start_time_entity = options.get(CONF_START_ENTITY)
        self.end_time = options.get(CONF_END_TIME)
        self.end_time_entity = options.get(CONF_END_ENTITY)
        self.manual_reset = options.get(CONF_MANUAL_OVERRIDE_RESET, False)
        self.manual_duration = options.get(
            CONF_MANUAL_OVERRIDE_DURATION, {"minutes": 15}
        )
        self.manual_threshold = options.get(CONF_MANUAL_THRESHOLD)
        self.start_value = options.get(CONF_INTERP_START)
        self.end_value = options.get(CONF_INTERP_END)
        self.normal_list = options.get(CONF_INTERP_LIST)
        self.new_list = options.get(CONF_INTERP_LIST_NEW)
        self.quiet_start = options.get(CONF_QUIET_START)
        self.quiet_end = options.get(CONF_QUIET_END)
        self.max_moves_hour = options.get(CONF_MAX_MOVES_HOUR)

    def _update_manager_and_covers(self):
        self.manager.reset_duration = dt.timedelta(**self.manual_duration)
        self.logger.debug(
            "Manual override duration from config: %s → timedelta: %s",
            self.manual_duration,
            self.manager.reset_duration,
        )
        self.manager.add_covers(self.entities)
        if not self._manual_toggle:
            self.logger.debug(
                "Manual toggle is %s (falsy), clearing all manual overrides",
                self._manual_toggle,
            )
            for entity in self.manager.manual_controlled:
                self.manager.reset(entity)

    def get_blind_data(self, options):
        """Assign correct class for type of blind."""
        if self._cover_type == "cover_blind":
            cover_data = AdaptiveVerticalCover(
                self.hass,
                self.logger,
                *self.pos_sun,
                *self.common_data(options),
                *self.vertical_data(options),
            )
        if self._cover_type == "cover_awning":
            cover_data = AdaptiveHorizontalCover(
                self.hass,
                self.logger,
                *self.pos_sun,
                *self.common_data(options),
                *self.vertical_data(options),
                *self.horizontal_data(options),
            )
        if self._cover_type == "cover_tilt":
            cover_data = AdaptiveTiltCover(
                self.hass,
                self.logger,
                *self.pos_sun,
                *self.common_data(options),
                *self.tilt_data(options),
            )
        self._apply_extended_config(cover_data, options)
        return cover_data

    def _apply_extended_config(self, cover_data, options) -> None:
        """Attach overhang / glare / privacy config to the cover adapter."""
        depth = options.get(CONF_OVERHANG_DEPTH)
        height = options.get(CONF_OVERHANG_HEIGHT)
        if depth and height and self._cover_type == "cover_blind":
            cover_data.overhang = Overhang(depth=depth, height_above_sill=height)
        eye_height = options.get(CONF_EYE_HEIGHT)
        occupied = options.get(CONF_OCCUPIED_DISTANCE)
        if eye_height and occupied and self._cover_type == "cover_blind":
            cover_data.glare = GlareModel(
                eye_height=eye_height, occupied_distance=occupied
            )
        if options.get(CONF_PRIVACY_MODE):
            cover_data.privacy = PrivacyConfig(
                enabled=True,
                offset_min=options.get(CONF_PRIVACY_OFFSET, 30) or 30,
                position=options.get(CONF_PRIVACY_POSITION, 0) or 0,
            )

    @property
    def check_adaptive_time(self):
        """Check if time is within start and end times."""
        if self._start_time and self._end_time and self._start_time > self._end_time:
            self.logger.error("Start time is after end time")
        return self.before_end_time and self.after_start_time

    @property
    def after_start_time(self):
        """Check if time is after start time."""
        now = dt.datetime.now()
        if self.start_time_entity is not None:
            time = get_datetime_from_str(
                get_safe_state(self.hass, self.start_time_entity)
            )
            self.logger.debug(
                "Start time: %s, now: %s, now >= time: %s ", time, now, now >= time
            )
            self._start_time = time
            return now >= time
        if self.start_time is not None:
            time = get_datetime_from_str(self.start_time)

            self.logger.debug(
                "Start time: %s, now: %s, now >= time: %s", time, now, now >= time
            )
            self._start_time
            return now >= time
        return True

    @property
    def _end_time(self) -> dt.datetime | None:
        """Get end time."""
        time = None
        if self.end_time_entity is not None:
            time = get_datetime_from_str(
                get_safe_state(self.hass, self.end_time_entity)
            )
        elif self.end_time is not None:
            time = get_datetime_from_str(self.end_time)
            if time.time() == dt.time(0, 0):
                time = time + dt.timedelta(days=1)
        return time

    @property
    def before_end_time(self):
        """Check if time is before end time."""
        if self._end_time is not None:
            now = dt.datetime.now()
            self.logger.debug(
                "End time: %s, now: %s, now < time: %s",
                self._end_time,
                now,
                now < self._end_time,
            )
            return now < self._end_time
        return True

    def _get_current_position(self, entity) -> int | None:
        """Get current position of cover."""
        if self._cover_type == "cover_tilt":
            return get_safe_attr(self.hass, entity, "current_tilt_position")
        return get_safe_attr(self.hass, entity, "current_position")

    def check_position(self, entity, state):
        """Check if position is different as state."""
        position = self._get_current_position(entity)
        if position is not None:
            return position != state
        self.logger.debug("Cover is already at position %s", state)
        return False

    def check_position_delta(self, entity, state: int, options):
        """Check cover positions to reduce calls."""
        position = self._get_current_position(entity)
        if position is not None:
            condition = abs(position - state) >= self.min_change
            self.logger.debug(
                "Entity: %s,  position: %s, state: %s, delta position: %s, min_change: %s, condition: %s",
                entity,
                position,
                state,
                abs(position - state),
                self.min_change,
                condition,
            )
            if state in [
                options.get(CONF_SUNSET_POS),
                options.get(CONF_DEFAULT_HEIGHT),
                0,
                100,
            ]:
                condition = True
            return condition
        return True

    def check_time_delta(self, entity):
        """Check if time delta is passed."""
        now = dt.datetime.now(dt.UTC)
        last_updated = get_last_updated(entity, self.hass)
        if last_updated is not None:
            condition = now - last_updated >= dt.timedelta(minutes=self.time_threshold)
            self.logger.debug(
                "Entity: %s, time delta: %s, threshold: %s, condition: %s",
                entity,
                now - last_updated,
                self.time_threshold,
                condition,
            )
            return condition
        return True

    @property
    def pos_sun(self):
        """Fetch information for sun position."""
        return [
            get_safe_attr(self.hass, "sun.sun", "azimuth"),
            get_safe_attr(self.hass, "sun.sun", "elevation"),
        ]

    def common_data(self, options):
        """Update shared parameters."""
        return [
            options.get(CONF_SUNSET_POS),
            options.get(CONF_SUNSET_OFFSET),
            options.get(CONF_SUNRISE_OFFSET, options.get(CONF_SUNSET_OFFSET)),
            self.hass.config.time_zone,
            options.get(CONF_FOV_LEFT),
            options.get(CONF_FOV_RIGHT),
            options.get(CONF_AZIMUTH),
            options.get(CONF_DEFAULT_HEIGHT),
            options.get(CONF_MAX_POSITION),
            options.get(CONF_MIN_POSITION),
            options.get(CONF_ENABLE_MAX_POSITION, False),
            options.get(CONF_ENABLE_MIN_POSITION, False),
            options.get(CONF_BLIND_SPOT_LEFT),
            options.get(CONF_BLIND_SPOT_RIGHT),
            options.get(CONF_BLIND_SPOT_ELEVATION),
            options.get(CONF_ENABLE_BLIND_SPOT, False),
            options.get(CONF_MIN_ELEVATION, None),
            options.get(CONF_MAX_ELEVATION, None),
        ]

    def get_climate_data(self, options):
        """Update climate data."""
        return [
            self.hass,
            self.logger,
            options.get(CONF_TEMP_ENTITY),
            options.get(CONF_TEMP_LOW),
            options.get(CONF_TEMP_HIGH),
            options.get(CONF_PRESENCE_ENTITY),
            options.get(CONF_WEATHER_ENTITY),
            options.get(CONF_WEATHER_STATE),
            options.get(CONF_OUTSIDETEMP_ENTITY),
            self._temp_toggle,
            self._cover_type,
            options.get(CONF_TRANSPARENT_BLIND),
            options.get(CONF_LUX_ENTITY),
            options.get(CONF_IRRADIANCE_ENTITY),
            options.get(CONF_LUX_THRESHOLD),
            options.get(CONF_IRRADIANCE_THRESHOLD),
            options.get(CONF_OUTSIDE_THRESHOLD),
            self._lux_toggle,
            self._irradiance_toggle,
        ]

    def climate_mode_data(self, options, cover_data):
        """Update climate mode data and control method."""
        climate = ClimateCoverData(*self.get_climate_data(options))
        self._climate_decision = ClimateCoverState(cover_data, climate).get_decision()
        self.climate_state = round(self._climate_decision.position)
        climate_data = ClimateCoverState(cover_data, climate).climate_data
        if climate_data.is_summer and self.switch_mode:
            self.control_method = "summer"
        if climate_data.is_winter and self.switch_mode:
            self.control_method = "winter"
        self.logger.debug(
            "Climate mode control method was set to %s", self.control_method
        )

    def vertical_data(self, options):
        """Update data for vertical blinds."""
        return [
            options.get(CONF_DISTANCE),
            options.get(CONF_HEIGHT_WIN),
        ]

    def horizontal_data(self, options):
        """Update data for horizontal blinds."""
        return [
            options.get(CONF_LENGTH_AWNING),
            options.get(CONF_AWNING_ANGLE),
        ]

    def tilt_data(self, options):
        """Update data for tilted blinds."""
        return [
            options.get(CONF_TILT_DISTANCE),
            options.get(CONF_TILT_DEPTH),
            options.get(CONF_TILT_MODE),
        ]

    @property
    def state(self) -> int:
        """Handle the output of the state based on mode."""
        self.logger.debug(
            "Basic position: %s; Climate position: %s; Using climate position? %s",
            self.default_state,
            self.climate_state,
            self._switch_mode,
        )
        if self._switch_mode:
            state = self.climate_state
        else:
            state = self.default_state

        state = self._transform_state(state)
        self.logger.debug("Final position to use: %s", state)
        return state

    def _transform_state(self, state):
        """Apply interpolation / inversion output transforms."""
        if self._use_interpolation:
            self.logger.debug("Interpolating position: %s", state)
            state = self.interpolate_states(state)

        if self._inverse_state and self._use_interpolation:
            self.logger.info(
                "Inverse state is not supported with interpolation, you can inverse the state by arranging the list from high to low"
            )

        if self._inverse_state and not self._use_interpolation:
            state = inverse_state(state)
            self.logger.debug("Inversed position: %s", state)
        return state

    def interpolate_states(self, state):
        """Interpolate states."""
        normal_range = [0, 100]
        new_range = []
        if self.start_value and self.end_value:
            new_range = [self.start_value, self.end_value]
        if self.normal_list and self.new_list:
            normal_range = list(map(int, self.normal_list))
            new_range = list(map(int, self.new_list))
        if new_range:
            state = np.interp(state, normal_range, new_range)
            if state == new_range[0]:
                state = 0
            if state == new_range[-1]:
                state = 100
        return state

    @property
    def switch_mode(self):
        """Let switch toggle climate mode."""
        return self._switch_mode

    @switch_mode.setter
    def switch_mode(self, value):
        self._switch_mode = value

    @property
    def temp_toggle(self):
        """Let switch toggle between inside or outside temperature."""
        return self._temp_toggle

    @temp_toggle.setter
    def temp_toggle(self, value):
        self._temp_toggle = value

    @property
    def control_toggle(self):
        """Toggle automation."""
        return self._control_toggle

    @control_toggle.setter
    def control_toggle(self, value):
        self._control_toggle = value

    @property
    def manual_toggle(self):
        """Toggle automation."""
        return self._manual_toggle

    @manual_toggle.setter
    def manual_toggle(self, value):
        self._manual_toggle = value

    @property
    def lux_toggle(self):
        """Toggle automation."""
        return self._lux_toggle

    @lux_toggle.setter
    def lux_toggle(self, value):
        self._lux_toggle = value

    @property
    def irradiance_toggle(self):
        """Toggle automation."""
        return self._irradiance_toggle

    @irradiance_toggle.setter
    def irradiance_toggle(self, value):
        self._irradiance_toggle = value


class AdaptiveCoverManager:
    """Track position changes."""

    def __init__(self, reset_duration: dict[str:int], logger) -> None:
        """Initialize the AdaptiveCoverManager."""
        self.covers: set[str] = set()

        self.manual_control: dict[str, bool] = {}
        self.manual_control_time: dict[str, dt.datetime] = {}
        self.reset_duration = dt.timedelta(**reset_duration)
        self.logger = logger

    def add_covers(self, entity):
        """Update set with entities."""
        self.covers.update(entity)

    def handle_state_change(
        self,
        states_data,
        our_state,
        blind_type,
        allow_reset,
        wait_target_call,
        manual_threshold,
    ):
        """Process state change event."""
        event = states_data
        if event is None:
            return
        entity_id = event.entity_id
        if entity_id not in self.covers:
            return
        if wait_target_call.get(entity_id):
            return

        new_state = event.new_state

        if blind_type == "cover_tilt":
            new_position = new_state.attributes.get("current_tilt_position")
        else:
            new_position = new_state.attributes.get("current_position")

        if new_position != our_state:
            if (
                manual_threshold is not None
                and abs(our_state - new_position) < manual_threshold
            ):
                self.logger.debug(
                    "Position change is less than threshold %s for %s",
                    manual_threshold,
                    entity_id,
                )
                return
            self.logger.debug(
                "Manual change detected for %s. Our state: %s, new state: %s",
                entity_id,
                our_state,
                new_position,
            )
            self.logger.debug(
                "Set manual control for %s, for at least %s seconds, reset_allowed: %s",
                entity_id,
                self.reset_duration.total_seconds(),
                allow_reset,
            )
            self.mark_manual_control(entity_id)
            self.set_last_updated(entity_id, new_state, allow_reset)

    def set_last_updated(self, entity_id, new_state, allow_reset):
        """Set last updated time for manual control."""
        if entity_id not in self.manual_control_time or allow_reset:
            last_updated = new_state.last_updated
            self.manual_control_time[entity_id] = last_updated
            self.logger.debug(
                "Updating last updated for manual control to %s for %s. Allow reset:%s",
                last_updated,
                entity_id,
                allow_reset,
            )
        elif not allow_reset:
            self.logger.debug(
                "Already manual control time specified for %s, reset is not allowed by user setting:%s",
                entity_id,
                allow_reset,
            )

    def mark_manual_control(self, cover: str) -> None:
        """Mark cover as under manual control."""
        self.manual_control[cover] = True

    async def reset_if_needed(self):
        """Reset manual control state of the covers."""
        current_time = dt.datetime.now(dt.UTC)
        manual_control_time_copy = dict(self.manual_control_time)
        for entity_id, last_updated in manual_control_time_copy.items():
            if current_time - last_updated > self.reset_duration:
                self.logger.debug(
                    "Resetting manual override for %s, because duration has elapsed",
                    entity_id,
                )
                self.reset(entity_id)

    def reset(self, entity_id):
        """Reset manual control for a cover."""
        self.manual_control[entity_id] = False
        self.manual_control_time.pop(entity_id, None)
        self.logger.debug("Reset manual override for %s", entity_id)

    def is_cover_manual(self, entity_id):
        """Check if a cover is under manual control."""
        return self.manual_control.get(entity_id, False)

    @property
    def binary_cover_manual(self):
        """Check if any cover is under manual control."""
        return any(value for value in self.manual_control.values())

    @property
    def manual_controlled(self):
        """Get the list of covers under manual control."""
        return [k for k, v in self.manual_control.items() if v]


def inverse_state(state: int) -> int:
    """Inverse state."""
    return 100 - state
