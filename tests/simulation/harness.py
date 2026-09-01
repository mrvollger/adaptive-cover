"""SimHouse: replay a whole day against the REAL integration, no house needed.

The harness sets up an actual config entry (coordinator, entities, listeners),
registers a fake ``cover.set_cover_position`` service that behaves like the
real Zigbee shades (an ``opening``/``closing`` intermediate state right away,
the landing position report only after a travel delay, with a fresh context),
drives ``sun.sun`` from real astral data for a fixed date/location, and steps
a frozen clock through the day firing HA's time-based listeners.

Every service call and cover state write is recorded on a timeline, so tests
assert on *what the integration actually told the covers to do* over a day:

    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("14:00")
    await house.user_moves("cover.shade", 100)     # human opens the shade
    await house.advance_to("16:00")
    assert house.auto_moves("cover.shade", since="14:00") == []

See tests/simulation/README.md for the full API tour (lifecycle, device
failure modes, entity accessors, timer control, multi-day runs).
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass

import pandas as pd
import pytz
from astral import sun as astral_sun
from homeassistant.core import Context, ServiceCall, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockUser,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_IRRADIANCE_ENTITY,
    CONF_IRRADIANCE_THRESHOLD,
    CONF_LUX_ENTITY,
    CONF_LUX_THRESHOLD,
    CONF_OUTSIDE_THRESHOLD,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_PRESENCE_ENTITY,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_STATE,
    DOMAIN,
    SensorType,
)
from tests.characterization.golden_lib import (
    SLC,
    STEP_MINUTES,
    FakeSunData,
    is_integration_context,
    patch_sun_data,
)
from tests.conftest import COMMON_OPTIONS

SIM_USER_ID = "simulated-human"


class SimSunData(FakeSunData):
    """FakeSunData that can regenerate itself IN PLACE for a new local date.

    calculation.py holds a reference to the single patched instance, so a
    multi-day simulation mutates this object rather than swapping it: after
    ``regenerate_for`` day-two ``sunset()``/``sunrise()``, solar-time
    sensors, and forecasts all read day-two astral data.
    """

    def regenerate_for(self, date: pd.Timestamp) -> None:
        """Recompute times/azimuth/elevation/date in place for ``date``."""
        self.date = date
        self.times = pd.date_range(
            start=date, end=date + pd.Timedelta(days=1),
            freq=f"{STEP_MINUTES}min", tz=self.timezone, name="time",
        )
        self.solar_azimuth = [
            astral_sun.azimuth(self.observer, t.to_pydatetime()) for t in self.times
        ]
        self.solar_elevation = [
            astral_sun.elevation(self.observer, t.to_pydatetime()) for t in self.times
        ]


@dataclass
class TimelineEvent:
    """One observed event in the simulated day (times are local)."""

    time: dt.datetime
    kind: str  # "service_call" | "state" | "poll"
    entity_id: str
    position: int | None = None
    actor: str = ""  # "integration" | "human" | "device"
    state: str | None = None
    service: str | None = None  # set for service_call events

    def __repr__(self) -> str:  # compact for assertion failure output
        pos = "" if self.position is None else f" pos={self.position}"
        st = "" if self.state is None else f" state={self.state}"
        tilt = " tilt" if self.service == "set_cover_tilt_position" else ""
        return (
            f"<{self.time.strftime('%H:%M')} {self.kind}{tilt} "
            f"{self.entity_id}{pos}{st} by={self.actor}>"
        )


@dataclass
class FakeShade:
    """A shade that travels: intermediate state now, landing report later.

    ``position`` and ``tilt`` are SEPARATE fields: ``set_cover_position``
    moves ``position`` and ``set_cover_tilt_position`` moves ``tilt``, each
    reported through its own state attribute. Fault switches (``jammed``,
    ``drop_next_landing``, ``report_position``, ``fail_next``) model real
    device misbehavior; drive them through the SimHouse fault API.
    """

    entity_id: str
    position: int = 100  # 100 = open (HA cover convention)
    tilt: int = 100
    travel_seconds: int = 120
    moving_to: int | None = None
    moving_field: str = "position"  # which field the current travel moves
    travel_from: int | None = None
    travel_started: dt.datetime | None = None
    eta: dt.datetime | None = None
    motion_context: Context | None = None
    jammed: bool = False
    drop_next_landing: bool = False
    report_position: bool = True
    fail_next: Exception | None = None

    def start_travel(
        self, target: int, ctx: Context, now: dt.datetime, *,
        travel_field: str = "position",
    ) -> str | None:
        """Begin moving; return the intermediate state, or None if a no-op."""
        if self.jammed:
            # A jammed motor accepts the command but never moves.
            return None
        current = getattr(self, travel_field)
        if target == current:
            self.moving_to = None
            return None
        if target == self.moving_to and travel_field == self.moving_field:
            # Motor already travelling to this target: a repeated command
            # is a no-op, it does NOT restart the journey.
            return None
        direction = "opening" if target > current else "closing"
        self.moving_field = travel_field
        self.travel_from = current
        self.travel_started = now
        self.moving_to = target
        self.eta = now + dt.timedelta(seconds=self.travel_seconds)
        self.motion_context = ctx
        return direction

    def landed(self, now: dt.datetime) -> bool:
        return (
            not self.jammed
            and self.moving_to is not None
            and self.eta is not None
            and now >= self.eta
        )

    def jam(self, now: dt.datetime) -> None:
        """Stop mid-travel at the interpolated position; never land."""
        if self.moving_to is not None and self.travel_started is not None:
            elapsed = (now - self.travel_started).total_seconds()
            frac = min(max(elapsed / self.travel_seconds, 0.0), 1.0)
            origin = (
                self.travel_from
                if self.travel_from is not None
                else getattr(self, self.moving_field)
            )
            stuck = round(origin + (self.moving_to - origin) * frac)
            setattr(self, self.moving_field, stuck)
        self.jammed = True


class SimHouse:
    """Simulated house driving the real adaptive_cover integration."""

    TEMP_SENSOR = "sensor.sim_indoor_temp"
    PRESENCE_SENSOR = "device_tracker.sim_person"
    WEATHER_ENTITY = "weather.sim_home"
    LUX_SENSOR = "sensor.sim_lux"
    IRRADIANCE_SENSOR = "sensor.sim_irradiance"
    OUTSIDE_TEMP_SENSOR = "sensor.sim_outdoor_temp"

    def __init__(self, hass, freezer, *, date, location, step_minutes):
        self.hass = hass
        self.freezer = freezer
        self.location = location
        self.tz = pytz.timezone(location["tz"])
        self.date = pd.Timestamp(date)
        self.step = dt.timedelta(minutes=step_minutes)
        self.shades: dict[str, FakeShade] = {}
        self.timeline: list[TimelineEvent] = []
        self.entry: MockConfigEntry | None = None
        self.coordinator = None
        self.sun_data: SimSunData | None = None
        self._patch = None
        self.now: dt.datetime | None = None  # tz-aware local sim time
        self._timers_held = False
        self.presence_entity = self.PRESENCE_SENSOR

    # ------------------------------------------------------------------ setup

    @classmethod
    async def create(
        cls,
        hass,
        freezer,
        *,
        date: str,
        covers: list[str] = ("cover.shade",),
        options: dict | None = None,
        cover_type: SensorType = SensorType.BLIND,
        location: dict | None = None,
        start_at: str = "04:00",
        step_minutes: int = 5,
        initial_position: int = 100,
        travel_seconds: int = 120,
        climate: dict | None = None,
    ) -> SimHouse:
        """Build the house, freeze the clock, and set up the integration.

        start_at: the local time the simulation (and HA) starts. The default
        pre-dawn 04:00 gives a clean full-day replay; a DAYTIME value (e.g.
        "13:00") models HA starting/restarting mid-day with the sun already
        actionable, for startup/catch-up scenarios.

        climate: enable climate mode with simulated sensors, e.g.
        {"temp": 22.0, "presence": "home", "weather": "sunny"}. Drive them
        later with set_temperature / set_presence / set_weather — each write
        fires the coordinator's entity listeners like the real sensors do.
        Optional aux keys create and wire extra entities:
          lux=450 (+ lux_threshold=1000)        -> sensor.sim_lux
          irradiance=250 (+ irradiance_threshold=300) -> sensor.sim_irradiance
          outside_temp=28.0 (+ outside_threshold)     -> sensor.sim_outdoor_temp
          presence_domain="zone"|"binary_sensor"|"input_boolean"|
          "device_tracker" (default) parameterizes the presence entity's
          domain (zone expects a count like "2"; binary_sensor "on"/"off").
        """
        location = location or dict(SLC)
        self = cls(hass, freezer, date=date, location=location, step_minutes=step_minutes)

        # Entity service calls validate context.user_id against hass.auth,
        # so the simulated human must exist as a real (owner) user.
        MockUser(id=SIM_USER_ID, is_owner=True).add_to_hass(hass)

        try:
            await hass.config.async_set_time_zone(location["tz"])
        except AttributeError:
            hass.config.set_time_zone(location["tz"])

        self.sun_data = SimSunData(
            location["lat"], location["lon"], location["tz"], self.date
        )
        self._patch = patch_sun_data(self.sun_data)
        self._patch.start()

        self.now = self._local(start_at)
        freezer.move_to(self.now)

        self._set_sun_state()
        for entity_id in covers:
            shade = FakeShade(
                entity_id,
                position=initial_position,
                tilt=initial_position,
                travel_seconds=travel_seconds,
            )
            self.shades[entity_id] = shade
            self._write_shade_state(shade, "open" if shade.position else "closed",
                                    Context(), actor="device", record=False)

        self._register_services()

        climate_opts = {}
        if climate is not None:
            presence_domain = climate.get("presence_domain", "device_tracker")
            if presence_domain != "device_tracker":
                self.presence_entity = f"{presence_domain}.sim_presence"
            hass.states.async_set(self.TEMP_SENSOR, str(climate.get("temp", 22.0)))
            hass.states.async_set(
                self.presence_entity, str(climate.get("presence", "home"))
            )
            hass.states.async_set(self.WEATHER_ENTITY, climate.get("weather", "sunny"))
            climate_opts = {
                CONF_CLIMATE_MODE: True,
                CONF_TEMP_ENTITY: self.TEMP_SENSOR,
                CONF_PRESENCE_ENTITY: self.presence_entity,
                CONF_WEATHER_ENTITY: self.WEATHER_ENTITY,
                CONF_TEMP_LOW: climate.get("temp_low", 21.0),
                CONF_TEMP_HIGH: climate.get("temp_high", 23.0),
                CONF_WEATHER_STATE: climate.get(
                    "weather_condition", ["sunny", "partlycloudy", "clear"]
                ),
            }
            if "lux" in climate:
                hass.states.async_set(self.LUX_SENSOR, str(climate["lux"]))
                climate_opts[CONF_LUX_ENTITY] = self.LUX_SENSOR
                climate_opts[CONF_LUX_THRESHOLD] = climate.get("lux_threshold", 1000)
            if "irradiance" in climate:
                hass.states.async_set(
                    self.IRRADIANCE_SENSOR, str(climate["irradiance"])
                )
                climate_opts[CONF_IRRADIANCE_ENTITY] = self.IRRADIANCE_SENSOR
                climate_opts[CONF_IRRADIANCE_THRESHOLD] = climate.get(
                    "irradiance_threshold", 300
                )
            if "outside_temp" in climate:
                hass.states.async_set(
                    self.OUTSIDE_TEMP_SENSOR, str(climate["outside_temp"])
                )
                climate_opts[CONF_OUTSIDETEMP_ENTITY] = self.OUTSIDE_TEMP_SENSOR
                if "outside_threshold" in climate:
                    climate_opts[CONF_OUTSIDE_THRESHOLD] = climate[
                        "outside_threshold"
                    ]

        opts = {
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: list(covers),
            **climate_opts,
            **(options or {}),
        }
        self.entry = MockConfigEntry(
            domain=DOMAIN,
            data={"name": "Sim House", CONF_SENSOR_TYPE: cover_type},
            options=opts,
        )
        self.entry.add_to_hass(hass)
        await self._setup_entry()
        return self

    async def _setup_entry(self) -> None:
        """Set the entry up and win the cover services back from the hub.

        The hub bootstrap loads the real cover component (for its aggregate
        cover), whose entity services override our fakes. Re-register so
        simulated shades win. Shared by create(), restart(), set_options().
        """
        assert await self.hass.config_entries.async_setup(self.entry.entry_id)
        await self.hass.async_block_till_done()
        self.coordinator = self.hass.data[DOMAIN][self.entry.entry_id]
        self._register_services()
        await self.hass.async_block_till_done()

    async def teardown(self) -> None:
        if self.entry is not None:
            await self.hass.config_entries.async_unload(self.entry.entry_id)
            await self.hass.async_block_till_done()
        if self._patch is not None:
            self._patch.stop()
            self._patch = None

    # ------------------------------------------------------------- lifecycle

    async def restart(
        self,
        *,
        at: str | None = None,
        restore: bool = True,
        seed_states: dict[str, str] | None = None,
    ) -> None:
        """Simulate an HA restart of this entry, preserving the timeline.

        Optionally advance to ``at`` first. Captures the current states of
        the entry's entities, unloads the entry, seeds the restore cache
        with them (``seed_states`` maps entity_id -> state string and
        overrides/extends the capture; ``restore=False`` skips capturing so
        RestoreEntity defaults apply), then re-runs setup on the SAME entry
        and re-wins the fake cover services. Shade states persist in
        hass.states across the restart, as in real HA.
        """
        if at is not None:
            await self.advance_to(at)
        registry = er.async_get(self.hass)
        reg_entries = er.async_entries_for_config_entry(
            registry, self.entry.entry_id
        )
        seeded: dict[str, State] = {}
        if restore:
            for reg_entry in reg_entries:
                state = self.hass.states.get(reg_entry.entity_id)
                if state is not None:
                    seeded[reg_entry.entity_id] = state
        for entity_id, state_str in (seed_states or {}).items():
            seeded[entity_id] = State(entity_id, state_str)
        await self.hass.config_entries.async_unload(self.entry.entry_id)
        await self.hass.async_block_till_done()
        if seeded:
            mock_restore_cache(self.hass, list(seeded.values()))
        await self._setup_entry()

    async def set_options(self, **option_changes) -> None:
        """The user edits this entry's options in the UI: merge and reload.

        Merges ``option_changes`` into entry.options, waits for the entry
        reload to complete, re-registers the fake cover services (the hub
        bootstrap steals them on setup) and re-points self.coordinator at
        the rebuilt one. Called with NO changes it models saving the
        options dialog unchanged (still a reload).
        """
        changed = self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, **option_changes}
        )
        if not changed:
            await self.hass.config_entries.async_reload(self.entry.entry_id)
        await self.hass.async_block_till_done()
        self.coordinator = self.hass.data[DOMAIN][self.entry.entry_id]
        self._register_services()
        await self.hass.async_block_till_done()

    # ------------------------------------------------------- internal helpers

    def _localize(self, naive: dt.datetime) -> dt.datetime:
        """pytz-localize handling DST folds and spring-forward gaps."""
        try:
            return self.tz.localize(naive, is_dst=None)
        except pytz.exceptions.AmbiguousTimeError:
            return self.tz.localize(naive, is_dst=False)  # take the fold
        except pytz.exceptions.NonExistentTimeError:
            return self.tz.localize(naive, is_dst=True)

    def _local(self, hhmm: str, *, day_offset: int = 0) -> dt.datetime:
        h, m = (int(x) for x in hhmm.split(":")[:2])
        naive = dt.datetime(
            self.date.year, self.date.month, self.date.day, h, m
        ) + dt.timedelta(days=day_offset)
        return self._localize(naive)

    def _sun_position(self, when: dt.datetime) -> tuple[float, float]:
        azi = astral_sun.azimuth(self.sun_data.observer, when)
        elev = astral_sun.elevation(self.sun_data.observer, when)
        return azi, elev

    def _set_sun_state(self) -> None:
        azi, elev = self._sun_position(self.now)
        self.hass.states.async_set(
            "sun.sun",
            "above_horizon" if elev > 0 else "below_horizon",
            {"azimuth": round(azi, 2), "elevation": round(elev, 2)},
        )

    def _actor_for(self, ctx: Context | None) -> str:
        if ctx is not None and getattr(ctx, "user_id", None) == SIM_USER_ID:
            return "human"
        if self.coordinator is not None and is_integration_context(
            self.coordinator, ctx
        ):
            return "integration"
        return "device"

    def _shade_state_str(self, shade: FakeShade) -> str:
        return "open" if shade.position > 0 else "closed"

    def _write_shade_state(
        self, shade: FakeShade, state: str, ctx: Context, *, actor: str,
        record: bool = True,
    ) -> None:
        attributes = {"supported_features": 255}
        if shade.report_position:
            attributes["current_position"] = shade.position
            attributes["current_tilt_position"] = shade.tilt
        self.hass.states.async_set(
            shade.entity_id, state, attributes, context=ctx
        )
        if record:
            self.timeline.append(
                TimelineEvent(
                    time=self.now, kind="state", entity_id=shade.entity_id,
                    position=shade.position, actor=actor, state=state,
                )
            )

    def _register_services(self) -> None:
        async def handle_set_position(call: ServiceCall) -> None:
            await self._handle_cover_command(
                call, travel_field="position", attr="position",
                service="set_cover_position",
            )

        async def handle_set_tilt(call: ServiceCall) -> None:
            await self._handle_cover_command(
                call, travel_field="tilt", attr="tilt_position",
                service="set_cover_tilt_position",
            )

        async def handle_update_entity(call: ServiceCall) -> None:
            # Arrival-poll: a polled device reports its true state now.
            targets = call.data.get("entity_id", [])
            if isinstance(targets, str):
                targets = [targets]
            for entity_id in targets:
                if (shade := self.shades.get(entity_id)) is None:
                    continue
                self.timeline.append(
                    TimelineEvent(
                        time=self.now, kind="poll", entity_id=entity_id,
                        actor="integration",
                    )
                )
                if shade.moving_to is not None and not shade.jammed:
                    self._land(shade)
                else:
                    # Idle, jammed, or a landing report was dropped: the
                    # poll re-reports the device's true current state.
                    self._write_shade_state(
                        shade, self._shade_state_str(shade), Context(),
                        actor="device",
                    )

        self.hass.services.async_register(
            "cover", "set_cover_position", handle_set_position
        )
        self.hass.services.async_register(
            "cover", "set_cover_tilt_position", handle_set_tilt
        )
        self.hass.services.async_register(
            "homeassistant", "update_entity", handle_update_entity
        )

    async def _handle_cover_command(
        self, call: ServiceCall, *, travel_field: str, attr: str, service: str
    ) -> None:
        entity_id = call.data["entity_id"]
        shade = self.shades[entity_id]
        if shade.fail_next is not None:
            # One-shot injected delivery failure, before any travel.
            exc = shade.fail_next
            shade.fail_next = None
            raise exc
        target = int(call.data[attr])
        current = self.hass.states.get(entity_id)
        if current is not None and current.state == "unavailable":
            # Real HA raises when an entity service targets an
            # unavailable entity; the integration must handle it.
            raise HomeAssistantError(f"Entity {entity_id} is unavailable")
        actor = self._actor_for(call.context)
        self.timeline.append(
            TimelineEvent(
                time=self.now, kind="service_call", entity_id=entity_id,
                position=target, actor=actor, service=service,
            )
        )
        direction = shade.start_travel(
            target, call.context, self.now, travel_field=travel_field
        )
        if direction is not None:
            # Intermediate state carries the caller's context, like a
            # real cover entity writing state inside the service call.
            self._write_shade_state(shade, direction, call.context, actor=actor)

    def _land(self, shade: FakeShade) -> None:
        """Finish travel: landing report with a fresh device context."""
        setattr(shade, shade.moving_field, shade.moving_to)
        shade.moving_to = None
        shade.eta = None
        shade.travel_from = None
        shade.travel_started = None
        if shade.drop_next_landing:
            # The device DID move, but the state report is swallowed; the
            # true position surfaces only on the next poll.
            shade.drop_next_landing = False
            return
        self._write_shade_state(
            shade, self._shade_state_str(shade), Context(), actor="device"
        )

    # ----------------------------------------------------------- fault modes

    def jam(self, entity_id: str) -> None:
        """Shade stops mid-travel at the interpolated position; never lands.

        No landing report is ever sent; an arrival-poll reports the stuck
        position (distinguishing a jam from drop_landing_report).
        """
        self.shades[entity_id].jam(self.now)

    def drop_landing_report(self, entity_id: str) -> None:
        """The next landing is silent: target reached, state report lost."""
        self.shades[entity_id].drop_next_landing = True

    def strip_position_attr(self, entity_id: str, on: bool = True) -> None:
        """While on, state writes omit current_position/current_tilt_position."""
        self.shades[entity_id].report_position = not on

    def fail_next_command(
        self, entity_id: str, exc: Exception | None = None
    ) -> None:
        """The next cover command for this shade raises once (no travel)."""
        self.shades[entity_id].fail_next = exc or HomeAssistantError(
            f"Simulated delivery failure for {entity_id}"
        )

    async def shade_goes_unavailable(self, entity_id: str) -> None:
        """The device drops off the network: entity turns unavailable."""
        self.hass.states.async_set(entity_id, "unavailable", {})
        await self.hass.async_block_till_done()

    async def shade_returns(self, entity_id: str) -> None:
        """The device comes back and reports its real current state."""
        shade = self.shades[entity_id]
        self._write_shade_state(
            shade, self._shade_state_str(shade), Context(), actor="device"
        )
        await self.hass.async_block_till_done()

    # --------------------------------------------------------------- driving

    def hold_timers(self) -> None:
        """Withhold HA time listeners: ticks advance clock/sun/travel only.

        Models the event loop delivering point-in-time callbacks late: a
        listener armed for 20:00 does not fire at 20:00 while held; on
        release_timers() it is delivered at the CURRENT sim time.

        Scheduled timers fire off the event loop's clock (which the freezer
        advances), so holding pins ``loop.time`` at its current value —
        wall-clock reads (datetime.now etc.) keep advancing normally.
        """
        if self._timers_held:
            return
        self._timers_held = True
        loop = self.hass.loop
        frozen_at = loop.time()
        loop.time = lambda: frozen_at  # instance attr shadows the method

    async def release_timers(self) -> None:
        """Deliver withheld time listeners now (late), and resume normal ticks."""
        if self._timers_held:
            del self.hass.loop.time  # un-shadow the real loop clock
        self._timers_held = False
        async_fire_time_changed(self.hass, self.now)
        await self.hass.async_block_till_done()

    async def tick(self) -> None:
        """Advance one step: clock, timers, shade travel, sun update.

        Crossing local midnight regenerates the (single, shared) sun-data
        instance for the new date, so multi-day runs see real day-two
        astral data. DST transition days need no extra handling.
        """
        self.now = self.tz.normalize(self.now + self.step)
        self.freezer.move_to(self.now)
        if self.now.date() != self.sun_data.date.date():
            self.sun_data.regenerate_for(pd.Timestamp(self.now.date()))
        if not self._timers_held:
            async_fire_time_changed(self.hass, self.now)
        await self.hass.async_block_till_done()
        for shade in self.shades.values():
            if shade.landed(self.now):
                self._land(shade)
        await self.hass.async_block_till_done()
        self._set_sun_state()
        await self.hass.async_block_till_done()

    async def advance_to(self, hhmm: str) -> None:
        """Step the simulation forward to a local time today (or tomorrow)."""
        offset = 0
        target = self._local(hhmm)
        while target <= self.now:
            offset += 1
            target = self._local(hhmm, day_offset=offset)
        while self.now < target:
            await self.tick()

    async def set_temperature(self, value: float) -> None:
        """The indoor temperature sensor reports a new reading."""
        self.hass.states.async_set(self.TEMP_SENSOR, str(value))
        await self.hass.async_block_till_done()

    async def set_presence(self, state: str) -> None:
        """The presence entity changes ("home"/"not_home", "on", a zone count)."""
        self.hass.states.async_set(self.presence_entity, str(state))
        await self.hass.async_block_till_done()

    async def set_weather(self, condition: str) -> None:
        """The weather entity changes condition ("sunny", "cloudy", ...)."""
        self.hass.states.async_set(self.WEATHER_ENTITY, condition)
        await self.hass.async_block_till_done()

    async def set_lux(self, value: float | str) -> None:
        """The lux sensor reports a new value (strings model bad data)."""
        self.hass.states.async_set(self.LUX_SENSOR, str(value))
        await self.hass.async_block_till_done()

    async def set_irradiance(self, value: float | str) -> None:
        """The irradiance sensor reports a new value (strings model bad data)."""
        self.hass.states.async_set(self.IRRADIANCE_SENSOR, str(value))
        await self.hass.async_block_till_done()

    async def set_outside_temp(self, value: float | str) -> None:
        """The outdoor temperature sensor reports a new value."""
        self.hass.states.async_set(self.OUTSIDE_TEMP_SENSOR, str(value))
        await self.hass.async_block_till_done()

    async def user_moves(
        self, entity_id: str, position: int, *, via: str = "remote",
        tilt: bool = False,
    ) -> None:
        """A human moves a shade (tilt=True moves the tilt field instead).

        via="dashboard": the human uses HA (service call with a user context,
        so intermediate states carry a user_id).
        via="remote": the human uses the physical remote/pull — HA only sees
        foreign state changes (fresh contexts, no user_id).
        """
        shade = self.shades[entity_id]
        ctx = (
            Context(user_id=SIM_USER_ID)
            if via == "dashboard"
            else Context()
        )
        direction = shade.start_travel(
            position, ctx, self.now,
            travel_field="tilt" if tilt else "position",
        )
        if direction is not None:
            self._write_shade_state(
                shade, direction, ctx, actor="human"
            )
        await self.hass.async_block_till_done()

    # ------------------------------------------------------ entity accessors

    def eid(self, domain: str, key: str) -> str:
        """Resolve one of the entry's entities by unique-id suffix.

        key is the normalized suffix: "cover_position", "toggle_control",
        "manual_override", "climate_mode", "reset_manual_override",
        "mode_select", "sun_infront", "control_method", ... Never hard-code
        sim_house_-slugged entity_ids in tests.
        """
        registry = er.async_get(self.hass)
        target = key.lower()
        for reg_entry in er.async_entries_for_config_entry(
            registry, self.entry.entry_id
        ):
            if reg_entry.domain != domain:
                continue
            suffix = reg_entry.unique_id.removeprefix(f"{self.entry.entry_id}_")
            if suffix.lower().replace(" ", "_") == target:
                return reg_entry.entity_id
        raise KeyError(f"No {domain} entity with unique-id suffix '{key}'")

    def entity(self, domain: str, key: str) -> State | None:
        """The current State of one of the entry's entities."""
        return self.hass.states.get(self.eid(domain, key))

    def sensor_value(self, key: str = "cover_position") -> str:
        """State string of one of the entry's sensors."""
        return self.entity("sensor", key).state

    def sensor_attr(self, key: str, attr: str):
        """One attribute of one of the entry's sensors."""
        return self.entity("sensor", key).attributes.get(attr)

    # ------------------------------------------------- entity-level controls

    async def toggle(self, key: str, on: bool) -> None:
        """Flip one of the entry's switches through a REAL HA service call."""
        await self.hass.services.async_call(
            "switch",
            "turn_on" if on else "turn_off",
            {"entity_id": self.eid("switch", key)},
            blocking=True,
            context=Context(user_id=SIM_USER_ID),
        )
        await self.hass.async_block_till_done()

    async def select_option(self, key: str, option: str) -> None:
        """Set one of the entry's selects through a REAL HA service call."""
        await self.hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": self.eid("select", key), "option": option},
            blocking=True,
            context=Context(user_id=SIM_USER_ID),
        )
        await self.hass.async_block_till_done()

    async def press(self, key: str = "reset_manual_override") -> None:
        """Press one of the entry's buttons through a REAL HA service call.

        The reset button waits (real-time polls) for covers to land; those
        polls only progress when the frozen clock moves, so this drives
        30-second sub-steps (landing shades as they arrive) until the press
        completes. Sim time may advance by up to a few minutes.
        """
        entity_id = self.eid("button", key)
        task = self.hass.loop.create_task(
            self.hass.services.async_call(
                "button",
                "press",
                {"entity_id": entity_id},
                blocking=True,
                context=Context(user_id=SIM_USER_ID),
            )
        )
        for _ in range(10):
            await asyncio.sleep(0)
            if task.done():
                break
        guard = 0
        while not task.done() and guard < 40:
            guard += 1
            self.now = self.tz.normalize(self.now + dt.timedelta(seconds=30))
            self.freezer.move_to(self.now)
            for shade in self.shades.values():
                if shade.landed(self.now):
                    self._land(shade)
            for _ in range(10):
                await asyncio.sleep(0)
                if task.done():
                    break
        await task
        if not self._timers_held:
            async_fire_time_changed(self.hass, self.now)
        await self.hass.async_block_till_done()

    # ------------------------------------------------------------ assertions

    def _t(self, hhmm: str | None) -> dt.datetime | None:
        return None if hhmm is None else self._local(hhmm)

    def moves(
        self,
        entity_id: str,
        *,
        actor: str | None = None,
        since: str | None = None,
        until: str | None = None,
        service: str | None = None,
    ) -> list[TimelineEvent]:
        """Service calls for one shade, optionally filtered."""
        lo, hi = self._t(since), self._t(until)
        return [
            ev
            for ev in self.timeline
            if ev.kind == "service_call"
            and ev.entity_id == entity_id
            and (actor is None or ev.actor == actor)
            and (service is None or ev.service == service)
            and (lo is None or ev.time >= lo)
            and (hi is None or ev.time <= hi)
        ]

    def auto_moves(self, entity_id: str, **kw) -> list[TimelineEvent]:
        """Positions the integration commanded, in order."""
        return self.moves(entity_id, actor="integration", **kw)

    def position(self, entity_id: str, *, tilt: bool = False) -> int:
        """The shade's true current position (or tilt) field."""
        shade = self.shades[entity_id]
        return shade.tilt if tilt else shade.position
