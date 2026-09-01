# Simulation harness — test the house without the house

`harness.py` runs the **real integration** (config entry, coordinator,
listeners, entities) against a fully simulated house:

- **Fake shades** that behave like the real Smartwings/Zigbee covers: an
  `opening`/`closing` intermediate state the moment a command arrives, a
  landing position report only after a travel delay (default 120 s), with a
  fresh (device) context — so the coordinator's echo/travel/manual-detection
  logic is exercised exactly as in production. `position` and `tilt` are
  separate fields driven by their own services, and each shade has fault
  switches (jam, dropped landing report, missing position attribute, failing
  command) for device-misbehavior scenarios.
- **A real sun**: astral-computed azimuth/elevation for a fixed date and
  location (SLC by default), written to `sun.sun` each tick. Crossing local
  midnight regenerates the sun table in place, so multi-day runs (including
  DST transition days) see correct day-two astral data.
- **A stepped frozen clock** (`freezer` + `async_fire_time_changed`), so
  point-in-time listeners (end-of-day close, arrival polls) fire in
  simulated time. The process timezone is deliberately NOT aligned with the
  configured HA timezone — the suite proves schedule math is tz-correct.

## Writing a scenario

```python
async def test_my_scenario(hass, freezer):
    house = await SimHouse.create(
        hass, freezer,
        date="2026-03-20",
        covers=["cover.shade"],
        options={CONF_END_TIME: "20:00:00", CONF_RETURN_SUNSET: True},
    )
    await house.advance_to("14:00")
    await house.user_moves("cover.shade", 100, via="remote")   # or "dashboard"
    await house.advance_to("16:00")
    assert house.auto_moves("cover.shade", since="14:00") == []
    await house.teardown()
```

## Setup — `SimHouse.create(...)`

- `date`, `location`, `step_minutes`, `covers`, `options`, `cover_type`,
  `initial_position`, `travel_seconds` — scenario shape.
- `start_at="04:00"` — when the sim (and HA) starts. A daytime value
  (`"13:00"`) models HA starting mid-day with the sun already actionable,
  for startup/catch-up scenarios.
- `climate={...}` — enables climate mode with simulated sensors:
  `temp`, `presence`, `weather`, `temp_low`, `temp_high`,
  `weather_condition`, plus optional aux entities:
  - `lux=450` (+ `lux_threshold=1000`) → `sensor.sim_lux`
  - `irradiance=250` (+ `irradiance_threshold=300`) → `sensor.sim_irradiance`
  - `outside_temp=28.0` (+ `outside_threshold`) → `sensor.sim_outdoor_temp`
  - `presence_domain="zone"|"binary_sensor"|"input_boolean"|"device_tracker"`
    parameterizes the presence entity's domain (zone expects a count like
    `"2"`; binary_sensor expects `"on"`/`"off"`).

## Driving time

- `house.advance_to("HH:MM")` — step to a local time (crosses midnight if
  already past); `house.tick()` — one step. Day rollovers regenerate the
  sun table (`SimSunData.regenerate_for`) in place.
- `house.hold_timers()` / `await house.release_timers()` — between hold and
  release, ticks advance the clock, sun state, and shade travel but HA time
  listeners do NOT fire; release delivers them late at the current sim time
  (models "HA delivered the 20:00 callback at 20:40"). Whole-window
  suppression only — no per-listener targeting.

## Driving inputs

- `house.set_temperature(v)` / `set_presence(s)` / `set_weather(c)` /
  `set_lux(v)` / `set_irradiance(v)` / `set_outside_temp(v)` — sensor
  writes through real state events. The setters accept strings so
  `"unavailable"` / garbage can drive resilience scenarios.
- `house.user_moves(entity, pos, via=, tilt=False)` — a human act.
  `"remote"` models the physical remote (foreign state changes, no user
  context); `"dashboard"` models an HA service call with a user context.
  `tilt=True` moves the tilt field (venetian scenarios).

## Lifecycle

- `await house.set_options(**changes)` — the user edits options in the UI:
  merges into `entry.options`, waits for the reload, re-wins the fake cover
  services, re-points `house.coordinator`. With no changes it models saving
  the dialog unchanged (still a reload).
- `await house.restart(at=None, restore=True, seed_states=None)` — HA
  restart: optionally advance first, capture entity states, unload, seed
  `mock_restore_cache` (or `seed_states={entity_id: "off"}` overrides;
  `restore=False` skips capture so defaults apply), set up again on the
  same entry. The timeline and shade states persist across the restart.

## Device faults

- `house.jam(entity)` — stops mid-travel at the interpolated position,
  never lands, never reports; an arrival-poll reports the stuck position.
- `house.drop_landing_report(entity)` — the next landing is silent: target
  reached but the report is swallowed; truth surfaces on the next poll.
- `house.strip_position_attr(entity, on=True)` — state writes omit
  `current_position`/`current_tilt_position` (covers that report no
  position).
- `house.fail_next_command(entity, exc=None)` — the next cover command for
  this shade raises once (default `HomeAssistantError`) before any travel.
- `await house.shade_goes_unavailable(entity)` /
  `await house.shade_returns(entity)` — network outage and return.

## Entities (never hard-code entity_ids)

- `house.eid(domain, key)` — resolve the entry's entities by unique-id
  suffix via the entity registry (`"cover_position"`, `"toggle_control"`,
  `"manual_override"`, `"climate_mode"`, `"reset_manual_override"`,
  `"mode_select"`, `"sun_infront"`, ...).
- `house.entity(domain, key)` → `State | None`;
  `house.sensor_value(key="cover_position")` → state string;
  `house.sensor_attr(key, attr)` → one attribute (e.g.
  `sensor_attr("cover_position", "move_blocked_by")`).
- `await house.toggle(key, on)` / `await house.press(key)` /
  `await house.select_option(key, option)` — REAL switch/button/select
  service calls with a simulated-user context. `press()` drives short
  sub-steps while the reset button waits for covers to land, so sim time
  may advance a few minutes.

## Assertions

- `house.timeline` — every service call and cover state write, timestamped,
  attributed to `integration` / `human` / `device`.
- `house.moves(entity, actor=, since=, until=, service=)` — service calls;
  `service="set_cover_tilt_position"` isolates tilt commands.
- `house.auto_moves(entity, ...)` — integration-commanded moves.
- `house.position(entity, tilt=False)` — the shade's true field value.

To replay a real incident from HA history, script the observed cover events
with `user_moves` / direct `hass.states.async_set` at the recorded times.

## Sanctioned couplings

The harness touches exactly two internals, both centralized in
`tests/characterization/golden_lib.py` until the refactor's first commit
makes them public seams:

- `patch_sun_data(sun_data)` — THE one place that knows SunData's import
  path (`calculation.SunData`).
- `is_integration_context(coordinator, ctx)` — THE one place that knows
  integration commands are marked via `coordinator._our_context_ids`.

## Mutation kill matrix

`tests/mutation_set/` holds one patch file per roadmap mutation (M01–M43)
plus `run_mutations.py`, which applies each patch, runs the configured
pytest tiers, records caught/missed, reverse-applies, and writes a JSON
report — see that script's docstring. Regenerate stale patches with
`python tests/mutation_set/make_patches.py`.

## File tour

`test_symptoms.py` pins the two 2026-09 field symptoms (manual overrides
reverted; end-of-day close missed); `test_regressions.py` pins the
coordinator fixes that came out of that bug hunt; `test_harness_smoke.py`
proves each harness extension's mechanism with one minimal scenario.
