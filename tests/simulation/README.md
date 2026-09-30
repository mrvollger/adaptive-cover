# Simulation harness — test the house without the house

`harness.py` runs the **real integration** (the house entry with one window
subentry per cover, coordinators, listeners, entities) against a fully
simulated house:

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
        hass,
        freezer,
        date="2026-03-20",
        covers=["cover.shade"],
        options={CONF_END_TIME: "20:00:00", CONF_RETURN_SUNSET: True},
    )
    await house.advance_to("14:00")
    await house.user_moves("cover.shade", 100, via="remote")  # or "dashboard"
    await house.advance_to("16:00")
    assert house.auto_moves("cover.shade", since="14:00") == []
    await house.teardown()
```

## Setup — `SimHouse.create(...)`

- `date`, `location`, `step_minutes`, `covers`, `options`, `cover_type`,
  `initial_position`, `travel_seconds` — scenario shape.
- The house is one house entry (3.1) with a `window` subentry per cover
  (ADR 0001; a window drives one cover: ADR 0002). It is built by
  `tests/house_model.py`: the house options are the windows' recurring
  values lifted into house/floor/area profiles and each subentry stores the
  window's geometry, cover and overrides, so every window acts on exactly
  `options`. `house.house_entry` (and `house.entries == [house_entry]`) is
  the entry to set up; `house.entry` is the first window as the house
  holds it (`windows.WindowEntry`: `entry_id` = its window key, `options` =
  its one-time options; recurring values are read with
  `await house.window().settings()`).
- `covers=[a, b]` creates **two windows**, one subentry per cover. The
  windows share `options` and `cover_type`; the first is "Sim House", the
  next "Sim House 2", and so on.
- `window_keys=[...]` — the windows' keys in the order of `covers`
  (default: their subentry_ids). A migrated window keeps its old
  entry_id as its key; the house replay uses the live entry_ids.
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

- `await house.set_options(**changes)` — the user edits every window's
  settings: one `adaptive_cover.change_settings` call per window (one-time
  settings go to the window's geometry and rebuild that window alone,
  recurring ones become the window's own values without a rebuild), then
  re-wins the fake cover services and keeps attributing commands to the
  rebuilt windows. With no changes it reloads the house entry.
- `await house.restart(at=None, restore=True, seed_states=None, cold=False)`
  — HA restart: optionally advance first, capture every window's entity
  states, unload, seed `mock_restore_cache` (or `seed_states={entity_id:
  "off"}` overrides, e.g. `{house.eid("select", "mode_select"): "off"}`;
  `restore=False` skips capture so defaults apply), set up again on the
  same house entry. The timeline and shade states persist across the
  restart. `cold=True` also drops the in-memory manual-override store, as
  a real process restart does.
- `await house.teardown()` — unloads and removes the house entry (and its
  entities' restore-cache records): a second SimHouse created later in
  the same test is then the one house.

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

- `house.window(entity=None)` — the cover's `WindowHandle`
  (`tests/window_handle.py`; default: the first cover): role-based public
  reads such as `target` (Position sensor), `is_manual` (this cover is in
  the Manual override sensor's `manual_controlled`), `manual_override`,
  `available` (update loop healthy), `move_blocked_by`, `moves`
  (`adaptive_cover_moved` provenance), `commands`, and `teardowns`
  (entity unloads, i.e. reloads). Built before setup, so it also sees the
  startup command.
- `house.eid(domain, key, cover=None)` — resolve a window's entities by
  unique-id suffix via the entity registry (`"cover_position"`,
  `"manual_override"` (the binary sensor), `"reset_manual_override"`,
  `"mode_select"`, `"sun_infront"`, `"control_method"`, ...).
  `cover` picks the window; the default is the first. The same `cover=`
  keyword works on `entity`, `sensor_value`, `sensor_attr`, `toggle`,
  `press` and `select_option`.
- `house.entity(domain, key)` → `State | None`;
  `house.sensor_value(key="cover_position")` → state string;
  `house.sensor_attr(key, attr)` → one attribute (e.g.
  `sensor_attr("cover_position", "move_blocked_by")`).
- `await house.toggle(key, on)` / `await house.press(key)` /
  `await house.select_option(key, option)` — REAL switch/button/select
  service calls with a simulated-user context. The reset button returns
  at once (it does not wait for covers to land); should a press ever
  block, `press()` drives short sub-steps until it completes.
  Windows have no switches since v2.1 (the six switches were hidden
  aliases since the P5 flip). `toggle(key, on)` keeps the old keys:
  `toggle("toggle_control", on)` sets the window's Mode (on selects
  `auto`, off selects `off`); `manual_override`, `climate_mode`,
  `outside_temperature`, `lux` and `irradiance` flip the house's switch
  of that toggle (`manual_detection`, `climate_on`, `use_outside_temp`,
  `use_lux`, `use_irradiance`: house settings). `house.switch(key)` reads
  the same way (`"on"` / `"off"`), and `house.house_switch_eid(key)` is
  the house switch's entity_id.
- `await house.hold(cover=, area_id=, duration=, position=)` — a REAL
  `adaptive_cover.hold` call: one window's Mode select, or every window in
  an area. `house.place(cover, "Office", floor="Upstairs")` puts a
  window's device in an area (created on first use) and returns its id.
- The window's Mode: `house.window().mode` (`auto` / `hold` / `off`) and
  `house.window().hold_until` (the Mode select's `until`).

## Assertions

- `house.local("HH:MM")` — that time on the sim day, tz-aware (for comparing
  with attributes such as the Mode select's `until`).
- `house.timeline` — every service call and cover state write, timestamped,
  attributed to `integration` / `human` / `device`.
- `house.moves(entity, actor=, since=, until=, service=)` — service calls;
  `service="set_cover_tilt_position"` isolates tilt commands.
- `house.auto_moves(entity, ...)` — integration-commanded moves.
- `house.position(entity, tilt=False)` — the shade's true field value.

To replay a real incident from HA history, script the observed cover events
with `user_moves` / direct `hass.states.async_set` at the recorded times.

## Sanctioned couplings

Tests observe the house only through `house.window()` / entity states and
the timeline. The harness itself uses two production seams, each wrapped
by one helper in `tests/characterization/golden_lib.py`:

- `patch_sun_data(sun_data)` — sets `calculation.sun_data_factory`, the
  hook every cover adapter uses to build its solar day.
- `is_integration_context(coordinator, ctx)` — wraps the coordinator's
  public `is_own_context(ctx)`, to attribute commands to the integration.
  Reaching that coordinator is the harness's one internal read
  (`window_handle.internal_coordinator`, marked `contract: internal`).

## Mutation kill matrix

`tests/mutation_set/` holds one patch file per roadmap mutation (M01–M43)
plus `run_mutations.py`, which applies each patch in its own temp copy of
the repo, runs the configured pytest tiers, records caught/missed, and
writes a JSON report. Use `--jobs N` to run mutations in parallel (your
checkout is never modified). Regenerate stale patches with
`python tests/mutation_set/make_patches.py`; `--check` verifies them
without writing. Flags, the behavior-tier ledger and its checker are
documented in `tests/contract/README.md`.

## File tour

`test_symptoms.py` pins the two 2026-09 field symptoms (manual overrides
reverted; end-of-day close missed); `test_regressions.py` pins the
coordinator fixes that came out of that bug hunt; `test_harness_smoke.py`
proves each harness extension's mechanism with one minimal scenario.
