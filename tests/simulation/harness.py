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
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from unittest.mock import patch

import pandas as pd
import pytz
from astral import sun as astral_sun
from homeassistant.core import Context, ServiceCall
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
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
from tests.characterization.golden_lib import SLC, FakeSunData
from tests.conftest import COMMON_OPTIONS

SIM_USER_ID = "simulated-human"


@dataclass
class TimelineEvent:
    """One observed event in the simulated day (times are local)."""

    time: dt.datetime
    kind: str  # "service_call" | "state" | "poll"
    entity_id: str
    position: int | None = None
    actor: str = ""  # "integration" | "human" | "device"
    state: str | None = None

    def __repr__(self) -> str:  # compact for assertion failure output
        pos = "" if self.position is None else f" pos={self.position}"
        st = "" if self.state is None else f" state={self.state}"
        return (
            f"<{self.time.strftime('%H:%M')} {self.kind} "
            f"{self.entity_id}{pos}{st} by={self.actor}>"
        )


@dataclass
class FakeShade:
    """A shade that travels: intermediate state now, landing report later."""

    entity_id: str
    position: int = 100  # 100 = open (HA cover convention)
    travel_seconds: int = 120
    moving_to: int | None = None
    eta: dt.datetime | None = None
    motion_context: Context | None = None

    def start_travel(self, target: int, ctx: Context, now: dt.datetime) -> str | None:
        """Begin moving; return the intermediate state, or None if a no-op."""
        if target == self.position:
            self.moving_to = None
            return None
        if target == self.moving_to:
            # Motor already travelling to this target: a repeated command
            # is a no-op, it does NOT restart the journey.
            return None
        direction = "opening" if target > self.position else "closing"
        self.moving_to = target
        self.eta = now + dt.timedelta(seconds=self.travel_seconds)
        self.motion_context = ctx
        return direction

    def landed(self, now: dt.datetime) -> bool:
        return self.moving_to is not None and self.eta is not None and now >= self.eta


class SimHouse:
    """Simulated house driving the real adaptive_cover integration."""

    TEMP_SENSOR = "sensor.sim_indoor_temp"
    PRESENCE_SENSOR = "device_tracker.sim_person"
    WEATHER_ENTITY = "weather.sim_home"

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
        self.sun_data: FakeSunData | None = None
        self._patch = None
        self.now: dt.datetime | None = None  # tz-aware local sim time

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
    ) -> "SimHouse":
        """Build the house, freeze the clock, and set up the integration.

        climate: enable climate mode with simulated sensors, e.g.
        {"temp": 22.0, "presence": "home", "weather": "sunny"}. Drive them
        later with set_temperature / set_presence / set_weather — each write
        fires the coordinator's entity listeners like the real sensors do.
        """
        location = location or dict(SLC)
        self = cls(hass, freezer, date=date, location=location, step_minutes=step_minutes)

        try:
            await hass.config.async_set_time_zone(location["tz"])
        except AttributeError:
            hass.config.set_time_zone(location["tz"])

        self.sun_data = FakeSunData(
            location["lat"], location["lon"], location["tz"], self.date
        )
        self._patch = patch(
            "custom_components.adaptive_cover.calculation.SunData",
            return_value=self.sun_data,
        )
        self._patch.start()

        self.now = self._local(start_at)
        freezer.move_to(self.now)

        self._set_sun_state()
        for entity_id in covers:
            shade = FakeShade(
                entity_id, position=initial_position, travel_seconds=travel_seconds
            )
            self.shades[entity_id] = shade
            self._write_shade_state(shade, "open" if shade.position else "closed",
                                    Context(), actor="device", record=False)

        self._register_services()

        climate_opts = {}
        if climate is not None:
            hass.states.async_set(self.TEMP_SENSOR, str(climate.get("temp", 22.0)))
            hass.states.async_set(
                self.PRESENCE_SENSOR, climate.get("presence", "home")
            )
            hass.states.async_set(self.WEATHER_ENTITY, climate.get("weather", "sunny"))
            climate_opts = {
                CONF_CLIMATE_MODE: True,
                CONF_TEMP_ENTITY: self.TEMP_SENSOR,
                CONF_PRESENCE_ENTITY: self.PRESENCE_SENSOR,
                CONF_WEATHER_ENTITY: self.WEATHER_ENTITY,
                CONF_TEMP_LOW: climate.get("temp_low", 21.0),
                CONF_TEMP_HIGH: climate.get("temp_high", 23.0),
                CONF_WEATHER_STATE: climate.get(
                    "weather_condition", ["sunny", "partlycloudy", "clear"]
                ),
            }

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
        assert await hass.config_entries.async_setup(self.entry.entry_id)
        await hass.async_block_till_done()
        self.coordinator = hass.data[DOMAIN][self.entry.entry_id]
        # The hub bootstrap loads the real cover component (for its
        # aggregate cover), whose entity services override our fakes.
        # Re-register so simulated shades win.
        self._register_services()
        await hass.async_block_till_done()
        return self

    async def teardown(self) -> None:
        if self.entry is not None:
            await self.hass.config_entries.async_unload(self.entry.entry_id)
            await self.hass.async_block_till_done()
        if self._patch is not None:
            self._patch.stop()
            self._patch = None

    # ------------------------------------------------------- internal helpers

    def _local(self, hhmm: str) -> dt.datetime:
        h, m = (int(x) for x in hhmm.split(":")[:2])
        naive = dt.datetime(
            self.date.year, self.date.month, self.date.day, h, m
        )
        return self.tz.localize(naive)

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
        if (
            self.coordinator is not None
            and ctx is not None
            and ctx.id in self.coordinator._our_context_ids
        ):
            return "integration"
        return "device"

    def _write_shade_state(
        self, shade: FakeShade, state: str, ctx: Context, *, actor: str,
        record: bool = True,
    ) -> None:
        self.hass.states.async_set(
            shade.entity_id,
            state,
            {
                "current_position": shade.position,
                "current_tilt_position": shade.position,
                "supported_features": 255,
            },
            context=ctx,
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
            entity_id = call.data["entity_id"]
            target = int(call.data.get("position", call.data.get("tilt_position")))
            shade = self.shades[entity_id]
            actor = self._actor_for(call.context)
            self.timeline.append(
                TimelineEvent(
                    time=self.now, kind="service_call", entity_id=entity_id,
                    position=target, actor=actor,
                )
            )
            direction = shade.start_travel(target, call.context, self.now)
            if direction is not None:
                # Intermediate state carries the caller's context, like a
                # real cover entity writing state inside the service call.
                self._write_shade_state(shade, direction, call.context, actor=actor)

        async def handle_update_entity(call: ServiceCall) -> None:
            # Arrival-poll: a polled device reports its true position now.
            for entity_id in call.data.get("entity_id", []):
                if (shade := self.shades.get(entity_id)) is None:
                    continue
                self.timeline.append(
                    TimelineEvent(
                        time=self.now, kind="poll", entity_id=entity_id,
                        actor="integration",
                    )
                )
                if shade.moving_to is not None:
                    self._land(shade)

        self.hass.services.async_register(
            "cover", "set_cover_position", handle_set_position
        )
        self.hass.services.async_register(
            "cover", "set_cover_tilt_position", handle_set_position
        )
        self.hass.services.async_register(
            "homeassistant", "update_entity", handle_update_entity
        )

    def _land(self, shade: FakeShade) -> None:
        """Finish travel: landing report with a fresh device context."""
        shade.position = shade.moving_to
        shade.moving_to = None
        shade.eta = None
        state = "open" if shade.position > 0 else "closed"
        self._write_shade_state(shade, state, Context(), actor="device")

    # --------------------------------------------------------------- driving

    async def tick(self) -> None:
        """Advance one step: clock, timers, shade travel, sun update."""
        self.now = self.now + self.step
        self.freezer.move_to(self.now)
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
        target = self._local(hhmm)
        if target <= self.now:
            target += dt.timedelta(days=1)
        while self.now < target:
            await self.tick()

    async def set_temperature(self, value: float) -> None:
        """The indoor temperature sensor reports a new reading."""
        self.hass.states.async_set(self.TEMP_SENSOR, str(value))
        await self.hass.async_block_till_done()

    async def set_presence(self, state: str) -> None:
        """The presence tracker changes ("home" / "not_home")."""
        self.hass.states.async_set(self.PRESENCE_SENSOR, state)
        await self.hass.async_block_till_done()

    async def set_weather(self, condition: str) -> None:
        """The weather entity changes condition ("sunny", "cloudy", ...)."""
        self.hass.states.async_set(self.WEATHER_ENTITY, condition)
        await self.hass.async_block_till_done()

    async def user_moves(
        self, entity_id: str, position: int, *, via: str = "remote"
    ) -> None:
        """A human moves a shade.

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
        direction = shade.start_travel(position, ctx, self.now)
        if direction is not None:
            self._write_shade_state(
                shade, direction, ctx, actor="human"
            )
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
    ) -> list[TimelineEvent]:
        """Service calls for one shade, optionally filtered."""
        lo, hi = self._t(since), self._t(until)
        return [
            ev
            for ev in self.timeline
            if ev.kind == "service_call"
            and ev.entity_id == entity_id
            and (actor is None or ev.actor == actor)
            and (lo is None or ev.time >= lo)
            and (hi is None or ev.time <= hi)
        ]

    def auto_moves(self, entity_id: str, **kw) -> list[TimelineEvent]:
        """Positions the integration commanded, in order."""
        return self.moves(entity_id, actor="integration", **kw)

    def position(self, entity_id: str) -> int:
        return self.shades[entity_id].position
