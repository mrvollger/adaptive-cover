"""House replay: every live window entry, replayed through SimHouse.

Each replay runs ONE real window entry from the sanitized live snapshot
(``tests/fixtures/house_snapshot/``) through the REAL integration via
``tests.simulation.harness.SimHouse`` for one full local day, and renders
what the house would do: the OUTBOUND cover-command timeline plus the
position sensor (value and ``intent``), run-length encoded per step.

Taken from the snapshot, verbatim:
- the entry's ``entry_id``, title, ``data`` and complete ``options``
  (geometry, limits, offsets, climate thresholds, the real cover and the
  real temperature/weather entity ids);
- the entry's entity-registry rows (pre-registered, so the sim runs with
  the live entity_ids and unique_ids);
- the live on/off state of the entry's switches (Toggle Control, Manual
  Override detection, Climate Mode, Outside Temperature), seeded through
  the restore cache exactly like an HA restart.

Scripted, identical for every window and date:
- HA runs in America/Denver with the US customary unit system; the indoor
  temperature sensors report °F, one profile per floor (``TEMP_PROFILE_F``);
- the weather entity goes sunny -> cloudy -> sunny (``WEATHER_SCRIPT``);
- one manual move from the physical remote mid-day (``MANUAL_MOVE``);
- the shade starts the day where the evening left it (its sunset position)
  and travels for ``TRAVEL_SECONDS``.

The replay starts at 00:30 local and ends at 00:30 the next local day, so
the DST start and end days step through the 02:00 transition.

Harness gaps closed here (only here; ``tests/simulation`` is untouched):
- ``ReplayHouse.tick`` delivers each shade landing AT its ETA (a sub-step)
  instead of after the next step's timers (see its docstring);
- ``TRAVEL_SECONDS`` is 90, not the harness's 120: 120 s ties exactly with
  the coordinator's 120 s in-flight timeout, which made the timer-vs-landing
  order (and so the command timeline) an artifact of callback ordering.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.adaptive_cover.const import (
    CONF_ENTITIES,
    CONFIG_ENTRY_MINOR_VERSION,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)
from tests.simulation import harness
from tests.simulation.harness import SimHouse

REPLAY_DIR = Path(__file__).parent
GOLDENS_DIR = REPLAY_DIR / "goldens"
SNAPSHOT_DIR = REPLAY_DIR.parent / "fixtures" / "house_snapshot"

STEP_MINUTES = 5
TRAVEL_SECONDS = 90
START_AT = "00:30"  # the replay also ENDS at this time on the next local day

# 2026 dates, America/Denver local. The September equinox is 00:05 UTC on
# 09-23, which is the evening of 09-22 in Denver.
DATES: dict[str, str] = {
    "dst_start": "2026-03-08",
    "spring_equinox": "2026-03-20",
    "summer_solstice": "2026-06-21",
    "autumn_equinox": "2026-09-22",
    "dst_end": "2026-11-01",
    "winter_solstice": "2026-12-21",
}

# Indoor temperature per floor, °F: every live window uses 72/75 °F
# thresholds. Upstairs walks winter (<72) -> intermediate -> summer (>75)
# -> intermediate -> winter; downstairs stays cooler and never hits summer.
FLOOR_BY_TEMP_ENTITY: dict[str, str] = {
    "sensor.upstairs_indoor_temperature": "upstairs",
    "sensor.downstairs_indoor_temperature": "downstairs",
}
TEMP_PROFILE_F: dict[str, list[tuple[str, float]]] = {
    "upstairs": [
        ("00:30", 70.0),
        ("08:00", 71.0),
        ("10:00", 73.0),
        ("14:00", 76.0),
        ("18:00", 74.0),
        ("21:00", 71.5),
    ],
    "downstairs": [
        ("00:30", 68.0),
        ("08:00", 69.0),
        ("10:00", 71.0),
        ("14:00", 73.5),
        ("18:00", 72.5),
        ("21:00", 70.0),
    ],
}
# Weather: sunny, a cloudy spell around noon, sunny again.
WEATHER_SCRIPT: list[tuple[str, str]] = [
    ("00:30", "sunny"),
    ("11:00", "cloudy"),
    ("13:00", "sunny"),
]
# Outdoor temperature on the weather entity, °F. Only read when a window's
# Outside Temperature switch is on.
OUTDOOR_F_BY_DATE: dict[str, float] = {
    "2026-03-08": 45.0,
    "2026-03-20": 55.0,
    "2026-06-21": 90.0,
    "2026-09-22": 75.0,
    "2026-11-01": 50.0,
    "2026-12-21": 35.0,
}
# One human act: the physical remote moves the shade mid-day. The live
# override lasts 2 h, so auto control resumes around 15:30.
MANUAL_MOVE: tuple[str, int, str] = ("13:30", 37, "remote")

# Switches restored from the live snapshot, by unique_id suffix.
RESTORED_SWITCHES = (
    "Toggle Control",
    "Manual Override",
    "Climate Mode",
    "Outside Temperature",
)


# --------------------------------------------------------------- snapshot


def _load_json(name: str) -> dict:
    return json.loads((SNAPSHOT_DIR / name).read_text())


@dataclass(frozen=True)
class Window:
    """One live window entry from the snapshot."""

    entry_id: str
    title: str
    data: dict
    options: dict
    registry_rows: tuple[dict, ...] = ()
    switch_states: tuple[tuple[str, str], ...] = ()  # (entity_id, on|off)

    @property
    def slug(self) -> str:
        keep = "".join(c if c.isalnum() else "_" for c in self.title.lower())
        return "_".join(part for part in keep.split("_") if part)

    @property
    def cover(self) -> str:
        (cover,) = self.options[CONF_ENTITIES]  # every live window has one
        return cover

    @property
    def floor(self) -> str:
        return FLOOR_BY_TEMP_ENTITY[self.options[CONF_TEMP_ENTITY]]

    @property
    def options_digest(self) -> str:
        blob = json.dumps(self.options, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


def load_windows() -> list[Window]:
    """The 15 live window entries (hub and disabled legacy entries excluded)."""
    entries = _load_json("config_entries.json")["entries"]
    registry = _load_json("entity_registry.json")["entities"]
    states = _load_json("entity_states.json")["states"]
    windows = []
    for entry in entries:
        if entry["role"] != "window":
            continue
        rows = tuple(
            row for row in registry if row["config_entry_id"] == entry["entry_id"]
        )
        switches = []
        for row in rows:
            suffix = row["unique_id"].removeprefix(f"{entry['entry_id']}_")
            if row["domain"] == "switch" and suffix in RESTORED_SWITCHES:
                live = states.get(row["entity_id"], {}).get("state")
                if live in ("on", "off"):
                    switches.append((row["entity_id"], live))
        windows.append(
            Window(
                entry_id=entry["entry_id"],
                title=entry["title"],
                data=entry["data"],
                options=entry["options"],
                registry_rows=rows,
                switch_states=tuple(sorted(switches)),
            )
        )
    return sorted(windows, key=lambda w: w.slug)


# ------------------------------------------------------------ the harness


class ReplayHouse(SimHouse):
    """SimHouse wrapper: live registry rows, restore seeding, ordered marks.

    ``marks`` interleaves step samples and scripted inputs with the
    harness timeline: each mark stores ``len(timeline)`` at the moment it
    was taken, so rendering can order everything by what really happened
    first, not just by timestamp.
    """

    window: Window  # bound per replay by a one-off subclass (see _create)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.marks: list[tuple[int, dt.datetime, str, tuple]] = []
        self.position_sensor: str | None = None
        self._replay_seeded = False

    async def _setup_entry(self) -> None:
        if not self._replay_seeded:
            self._replay_seeded = True
            self._seed_registry_and_restore()
        await super()._setup_entry()
        self.position_sensor = self.eid("sensor", "cover_position")

    def _seed_registry_and_restore(self) -> None:
        """Pre-register the live entity rows and seed the live switch states."""
        registry = er.async_get(self.hass)
        for row in self.window.registry_rows:
            domain, object_id = row["entity_id"].split(".", 1)
            registry.async_get_or_create(
                domain,
                DOMAIN,
                row["unique_id"],
                suggested_object_id=object_id,
                config_entry=self.entry,
            )
        if self.window.switch_states:
            mock_restore_cache(
                self.hass,
                [State(eid, state) for eid, state in self.window.switch_states],
            )

    def mark(self, kind: str, *payload) -> None:
        self.marks.append((len(self.timeline), self.now, kind, payload))

    def sample(self) -> None:
        state = self.hass.states.get(self.position_sensor)
        if state is None:
            self.mark("sensor", "<none>", "")
        else:
            self.mark("sensor", state.state, str(state.attributes.get("intent")))

    async def tick(self) -> None:
        """One step, but shade landings arrive AT their ETA (a sub-step).

        SimHouse.tick fires the step's timers first and only then lands
        shades whose ETA already passed. With 5-minute steps, the refresh
        at step+5min sees the old position after the 120 s in-flight latch
        expired and re-sends the same command: a harness artifact the real
        house never shows (its shades report within 1-3 min). Delivering
        each landing at its ETA keeps 5-minute steps without that artifact.
        """
        target = self.tz.normalize(self.now + self.step)
        while True:
            etas = sorted(
                shade.eta
                for shade in self.shades.values()
                if shade.moving_to is not None
                and not shade.jammed
                and shade.eta is not None
                and self.now < shade.eta < target
            )
            if not etas:
                break
            await self._advance_clock(self.tz.normalize(etas[0]))
        await self._advance_clock(target)
        self._set_sun_state()
        await self.hass.async_block_till_done()
        self.sample()

    async def _advance_clock(self, when: dt.datetime) -> None:
        """Move the clock, fire due timers, land due shades (SimHouse order)."""
        self.now = when
        self.freezer.move_to(when)
        if self.now.date() != self.sun_data.date.date():
            self.sun_data.regenerate_for(self.now.date())
        async_fire_time_changed(self.hass, when)
        await self.hass.async_block_till_done()
        for shade in self.shades.values():
            if shade.landed(self.now):
                self._land(shade)
        await self.hass.async_block_till_done()


@dataclass
class Replay:
    """What one replay observed, ready to render."""

    window: Window
    label: str
    date: str
    lines: list[tuple[tuple, dt.datetime, str]] = field(default_factory=list)


def _entry_factory(window: Window):
    """MockConfigEntry with the live entry_id, title and data."""

    def factory(*, domain, data, options):  # the call SimHouse.create makes
        return MockConfigEntry(
            domain=domain,
            entry_id=window.entry_id,
            title=window.title,
            data=dict(window.data),
            options=options,
        )

    return factory


async def _create(hass, freezer, window: Window, date: str) -> ReplayHouse:
    house_cls = type("WindowReplayHouse", (ReplayHouse,), {"window": window})
    with patch.object(harness, "MockConfigEntry", _entry_factory(window)):
        house = await house_cls.create(
            hass,
            freezer,
            date=date,
            covers=[window.cover],
            options=dict(window.options),
            start_at=START_AT,
            step_minutes=STEP_MINUTES,
            travel_seconds=TRAVEL_SECONDS,
            # At 00:30 the shade sits where the evening left it.
            initial_position=int(window.options.get("sunset_position") or 0),
        )
    # The entry starts at config version 1.1 (as the live house did before
    # P1), so every replay runs the live options through migrations 1.2 and
    # 1.3 (P3: fallbacks written, cover_entity_id) and the goldens pin the
    # migrated windows.
    assert (house.entry.version, house.entry.minor_version) == (
        1,
        CONFIG_ENTRY_MINOR_VERSION,
    )
    # P5 flip: the hub lifted the window (a hub created at 1.4 or later
    # lifts itself), so the goldens pin the window acting on its resolved
    # layered settings; a window that is not lifted has no provenance.
    assert house.windows[window.cover].attributes.get("provenance") is not None
    house.sample()
    return house


async def run_replay(hass, freezer, window: Window, label: str) -> Replay:
    """Replay one live window over one scripted local day."""
    date = DATES[label]
    hass.config.units = US_CUSTOMARY_SYSTEM
    temp_entity = window.options[CONF_TEMP_ENTITY]
    weather_entity = window.options[CONF_WEATHER_ENTITY]
    outdoor_f = OUTDOOR_F_BY_DATE[date]

    def set_temp(value: float) -> None:
        hass.states.async_set(
            temp_entity,
            str(value),
            {"unit_of_measurement": "°F", "device_class": "temperature"},
        )

    def set_weather(condition: str) -> None:
        hass.states.async_set(
            weather_entity,
            condition,
            {"temperature": outdoor_f, "temperature_unit": "°F"},
        )

    profile = TEMP_PROFILE_F[window.floor]
    set_temp(profile[0][1])
    set_weather(WEATHER_SCRIPT[0][1])

    script: list[tuple[str, str, object]] = sorted(
        [
            *(("temp", hhmm, value) for hhmm, value in profile[1:]),
            *(("weather", hhmm, cond) for hhmm, cond in WEATHER_SCRIPT[1:]),
            ("human", MANUAL_MOVE[0], MANUAL_MOVE[1]),
        ],
        key=lambda item: item[1],
    )

    house = await _create(hass, freezer, window, date)
    try:
        for kind, hhmm, value in script:
            await house.advance_to(hhmm)
            if kind == "temp":
                house.mark("input", f"{temp_entity} = {value} °F")
                set_temp(value)
            elif kind == "weather":
                house.mark("input", f"{weather_entity} = {value}")
                set_weather(value)
            else:
                house.mark("human", f"{window.cover} -> {value} (via {MANUAL_MOVE[2]})")
                await house.user_moves(window.cover, value, via=MANUAL_MOVE[2])
            await hass.async_block_till_done()
        await house.advance_to(START_AT)  # through midnight into tomorrow
        replay = Replay(window=window, label=label, date=date)
        _collect(house, replay)
    finally:
        await house.teardown()
    return replay


def _collect(house: ReplayHouse, replay: Replay) -> None:
    """Merge outbound commands, RLE sensor samples and script marks.

    Sort key: a timeline event at index i sorts as (i, 1, 0); a mark taken
    when the timeline had L events sorts as (L, 0, n), n = mark order. So a
    mark lands after every event that happened before it, and before every
    event that happened after it.
    """
    for index, ev in enumerate(house.timeline):
        if ev.kind == "service_call" and ev.actor == "integration":
            replay.lines.append(
                (
                    (index, 1, 0),
                    ev.time,
                    f"cmd    {ev.service} {ev.entity_id} {ev.position}",
                )
            )
    previous = None
    for n, (length, when, kind, payload) in enumerate(house.marks):
        if kind == "sensor":
            if payload == previous:
                continue
            previous = payload
            text = f"sensor {payload[0]} ({payload[1]})"
        else:
            text = f"{kind:<6} {payload[0]}"
        replay.lines.append(((length, 0, n), when, text))
    replay.lines.append(
        (
            (len(house.timeline), 2, 0),
            house.now,
            f"end    shade at {house.position(replay.window.cover)}",
        )
    )


def render(replay: Replay) -> str:
    """Deterministic text rendering of one replay."""
    w = replay.window
    o = w.options
    switches = (
        ", ".join(f"{eid.split('.', 1)[1]}={state}" for eid, state in w.switch_states)
        or "(none captured: integration defaults)"
    )
    min_pos = o.get("min_position")
    max_pos = o.get("max_position")
    lines = [
        f"# house replay: {w.title} ({w.entry_id}) on {replay.date} ({replay.label})",
        f"# SLC (tests' lat/lon), tz=America/Denver, units=US customary, "
        f"step={STEP_MINUTES}min, travel={TRAVEL_SECONDS}s, "
        f"{START_AT} -> {START_AT} next day",
        f"# cover={w.cover} sensor_type={w.data[CONF_SENSOR_TYPE]} "
        f"options_sha256={w.options_digest}",
        f"# azimuth={o.get('set_azimuth')} fov={o.get('fov_left')}/"
        f"{o.get('fov_right')} elevation={o.get('min_elevation')}.."
        f"{o.get('max_elevation')} window_h={o.get('window_height')} "
        f"distance={o.get('distance_shaded_area')} overhang="
        f"{o.get('overhang_depth')}/{o.get('overhang_height')} glare="
        f"{o.get('eye_height')}/{o.get('occupied_distance')}",
        f"# default={o.get('default_percentage')} sunset_pos="
        f"{o.get('sunset_position')} sunset_off={o.get('sunset_offset')} "
        f"sunrise_off={o.get('sunrise_offset')} start={o.get('start_time')} "
        f"end={o.get('end_time')} min={min_pos} (sun-only="
        f"{o.get('enable_min_position')}) max={max_pos} (sun-only="
        f"{o.get('enable_max_position')}) privacy={o.get('privacy_mode')}",
        f"# climate={o.get('climate_mode')} temp={o.get(CONF_TEMP_ENTITY)} "
        f"({w.floor}) low/high={o.get('temp_low')}/{o.get('temp_high')} "
        f"sunny={','.join(o.get('weather_state') or [])} "
        f"override={o.get('manual_override_duration')} "
        f"reset={o.get('manual_override_reset')}",
        f"# restored switches: {switches}",
        "# lines: cmd = outbound cover call; sensor = position sensor "
        "(intent), shown when it changes; input/human = scripted",
        "#",
    ]
    for _, when, text in sorted(replay.lines, key=lambda line: line[0]):
        lines.append(f"{when.strftime('%m-%d %H:%M:%S %Z')}  {text}")
    return "\n".join(lines) + "\n"


def golden_path(window: Window, label: str) -> Path:
    return GOLDENS_DIR / f"{window.slug}__{label}.txt"
