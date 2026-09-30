# Adaptive Cover — Architecture & Codebase Guide

## What It Does

A Home Assistant custom integration that automatically positions window blinds, awnings, and venetian blinds based on solar geometry. It calculates where the sun is relative to each window and sets cover positions to block direct sunlight. Optionally adds climate-aware logic (temperature, presence, weather) to balance glare reduction with passive heating/cooling.

## Supported Cover Types

| Type | Key Parameters | Position Meaning |
|------|---------------|-----------------|
| **Vertical blind** | window height, distance to shade area | % of window covered from top |
| **Horizontal awning** | awning length, awning angle | % of awning extended |
| **Venetian tilt** | slat depth, slat spacing | slat tilt angle as % |

## Directory Layout

```
.
├── custom_components/adaptive_cover/  # The integration (what HACS installs)
├── card/                    # Lovelace card source (TypeScript, vitest); bundle → custom_components/adaptive_cover/www/
├── tests/                   # pytest tiers (see "Development & Testing")
├── docs/
│   ├── refactor_plan.md     # Target design and phases P0–P8 (the design reference)
│   ├── refactor_baseline_review.md  # Measured baseline (2026-09-28) and targets
│   └── adr/                 # Architecture decision records 0001–0005 + index
├── images/                  # README images (not shipped)
├── pixi.toml, pixi.lock     # Dev environment and tasks (test, lint, typecheck, mutations)
├── hacs.json                # HACS metadata, minimum HA version
├── CONTRIBUTING.md          # Dev workflow: tiers, scenarios, mutations, ledger, releases
└── agents.md                # This guide
```

```
custom_components/adaptive_cover/
├── __init__.py              # Entry point: platform setup, services, event listeners
├── coordinator.py           # Core: update loop, gates, cover service calls, manual override tracking
├── calculation.py           # HA adapters built from ShadeConfig (build_cover): engine inputs, delegate to engine/
├── engine/                  # Pure math and strategy (no HA imports, no clock reads; pyright strict)
│   ├── models.py            # Typed inputs/outputs (CoverConfig, SunSnapshot, Decision, ...)
│   ├── geometry.py          # Gamma/FOV/elevation, per-cover-type %, overhang, glare-safe height
│   ├── numeric.py           # clip/interp: scalar stand-ins for np.clip/np.interp
│   ├── evaluate.py          # evaluate(config, sun, ctx, climate=None) -> Decision
│   └── season.py            # decide_season(inputs, previous) -> Season: thresholds + hysteresis
├── runtime/                 # Runtime building blocks (P2: the clock; P4: the coordinator split; pyright strict)
│   ├── clock.py             # Clock protocol + HassClock: the only module that reads "now"
│   ├── shade_config.py      # ShadeConfig (typed options incl. CoverGeometry/ClimateOptions, one fallback per key: ABSENT), ControlState
│   ├── schedule.py          # Schedule: start/end time window (no hass; state reader + "now" passed in)
│   ├── gates.py             # GatePolicy: delta/time/quiet/budget gates and their order (no hass)
│   ├── command_tracker.py   # CommandTracker: commands in flight, travel latch, late delivery, arrival polls
│   ├── decider.py           # Decider: basic vs climate position, interpolation / inverse transforms
│   ├── manual_detector.py   # ManualDetector: motion-start, redirect-in-travel and landing rules
│   ├── override_tracker.py  # OverrideTracker: per-cover manual latch + override clock, requested holds' ends (hass.data store)
│   ├── mode.py              # P5 flip: Mode auto/hold/off, ModeControl (select, alias, button, hold service), restore rule
│   ├── end_of_day.py        # EndOfDay: end-time timer, catch-up close, retry of missed closes
│   ├── events.py            # RefreshQueue: why the next refresh runs (entity, cover, startup, end time)
│   └── explainer.py         # Explainer: next change, forecast, last change, move log, sensor attributes
├── sun.py                   # Astral-based solar table (SolarDay, 5-minute points, stdlib only)
├── config_flow.py           # Setup wizard + one-page options form (routing only)
├── settings/                # One option spec; every settings surface is built from it (P3)
│   ├── spec.py              # OPTS: one row per option (kind, default, range, unit, one-time/recurring, surfaces, legacy drift)
│   ├── schema.py            # Wizard pages, options sections, service schemas, number ranges
│   ├── normalize.py         # The window's one cover: cover_entity_id + group: [cover] (both written until P8)
│   ├── validate.py          # Cross-field checks (elevation order, blind-spot order, interp lists)
│   ├── resolve.py           # P5: pure layered resolver (window > area > floor > house > default) + provenance
│   ├── lift.py              # P5: pure lift of flat legacy options into house/floor/area/window layers
│   └── shadow.py            # P5 store: toggle settings, stored-layer (de)serialization, compare, adopt
├── window_cover.py          # One cover per window (ADR 0002): cover_problem guard, registry-id unique_id, split issue
├── migration.py             # Config entry 1.3: fallbacks written into options, cover_entity_id, unique_id
├── shadow.py                # Config entry 1.4 (P5): lift into the hub (also a never-lifted house at setup), switch-state capture, adoption
├── layers.py                # P5 flip: what a window acts on (resolved every refresh), sparse window edits, profiles, propagation
├── repairs.py               # Fix flows: "split" (multi-cover entry -> one window per cover), "consolidate" (P7: dry run, backup, move)
├── windows.py               # P7: WindowEntry (a window entry or a house "window" subentry, read the same way), lookups, async_update_window
├── house.py                 # P7: HouseRuntime (house entry runtime_data): one coordinator per window subentry, isolated setup, subentry listener
├── consolidate.py           # P7: move window entries into house subentries (plan, snapshot, re-parent rows, resumable) + the repair issue
├── const.py                 # All config keys, defaults, enums
├── hub.py                   # "Adaptive Cover All" hub device (all-shades cover, house Mode select auto/hold/off/mixed, reset-all button)
├── house_settings.py        # P5 flip: the house settings on the hub (Climate + toggle switches, threshold/duration/geometry numbers, end/quiet times)
├── profile_service.py       # adaptive_cover.get_profile: read-only, response-only view of the stored layers (any user)
├── time.py                  # The hub's house times (end time, quiet hours start/end)
├── cover.py                 # Cover platform: only the hub's aggregate cover
├── sensor.py                # Position %, solar times, control method, next/last change
├── binary_sensor.py         # Sun in front, manual override active
├── switch.py                # Hidden switch aliases (P5): Toggle Control writes the Mode; the others write the window's toggle value
├── select.py                # Mode select auto/hold/off (RestoreEntity, source of truth) + the hold entity service
├── number.py                # The hub's house numbers (the window numbers were removed in the P5 flip)
├── button.py                # Return to auto button (Mode auto)
├── entity_shared.py         # Shared entity helpers (device info, Position window attributes)
├── entity_surface.py        # Entity surface table (category, visibility, name key) + 1.2/1.5 migrations + area copy
├── frontend.py              # Serves and auto-registers the bundled Lovelace card
├── logbook.py               # Logbook text for adaptive_cover_moved events
├── helpers.py               # Utility functions (safe state access, datetime parsing)
├── config_context_adapter.py # Logger adapter that tags logs with config name
├── diagnostics.py           # HA diagnostics export (incl. the resolved settings a window acts on)
├── services.yaml            # get_forecast, hold (entity service on the Mode selects), get_profile, set_profile, change_settings, add_entry
├── manifest.json            # Integration metadata, version & requirements
├── strings.json             # English UI strings (source for translations/en.json)
├── icons.json               # MDI icon mappings
├── translations/            # en.json only (English-only by choice)
├── blueprints/              # HA automation blueprints
└── www/                     # Built card bundle (adaptive-cover-card.js)
```

```
tests/
├── engine/                  # Pure engine tests + property sweeps; test_purity.py guard
├── runtime/                 # Runtime component unit tests with fakes, no hass (P4)
├── characterization/        # Climate truth table, golden days, outbound service calls
├── simulation/              # SimHouse full-day replays (README.md = harness API)
├── replay/                  # House-replay goldens: real configs x 6 dates (added in P0)
├── contract/                # behavior_tier_ids.txt, ledger.md, check_behavior_tier.py (P0); spec_parity.json (P3)
├── settings/                # Option spec: plan's one-time/recurring table, drift list, wizard<->options<->service<->normalize round trip
├── mutation_set/            # One patch per mutation (manifest.json lists them), make_patches.py, run_mutations.py
├── refactor_roadmap.json    # Contract v1: behavior-tier seams, mutation table, acceptance bar
└── test_*.py                # Entity-surface tier: config flow, services, entities, hub
```

## Design References

- `docs/refactor_plan.md` — the refactor's target design, phases P0–P8,
  release gate, refactor contract and the owner's decisions. Read it
  before changing the config model, the entity surface or the coordinator.
- `docs/adr/` — short records of the load-bearing decisions: 0001 house
  entry + window subentries, 0002 one cover per window, 0003 settings
  precedence (window override → area → floor → house → spec default) and
  the one-time vs recurring rule, 0004 refactor contract v2 + behavior
  tier/mutation gate, 0005 drop pandas/numpy/pytz, 0006 (proposed, P7)
  window subentries in v2.0: verbatim storage, versions, move order. A
  new design decision gets a new ADR; an accepted ADR is superseded, not
  rewritten.
- `CONTRIBUTING.md` — the how-to for everything in "Development & Testing".

## Core Architecture

### Data Flow

```
sun.sun state change ──┐
temp entity change ────┤
presence change ───────┤──▶ AdaptiveDataUpdateCoordinator._async_update_data()
weather change ────────┤         │
cover state change ────┘         ▼
                          Instantiate cover class (Vertical/Horizontal/Tilt)
                                 │
                          ┌──────┴──────┐
                          ▼             ▼
                     BasicMode    ClimateMode
                     (NormalCoverState)  (ClimateCoverState)
                          │             │
                          └──────┬──────┘
                                 ▼
                          Raw position (0-100%)
                                 │
                          Apply transforms:
                            - interpolation (custom ranges)
                            - inverse (if enabled)
                            - min/max clamp
                                 │
                          Gate checks:
                            - timing window (start/end time)
                            - position delta threshold
                            - time delta throttle
                            - manual override check
                                 │
                          ▼
                    cover.set_cover_position service call
```

### Key Classes

**`AdaptiveDataUpdateCoordinator`** (coordinator.py) — The hub. Inherits HA's `DataUpdateCoordinator`. Listens to state changes, runs the calculation pipeline, calls cover services, tracks manual overrides. Delegates to the runtime/ components below; `coordinator.manager` is the `OverrideTracker`.

**`AdaptiveGeneralCover`** (calculation.py) — Abstract base for all cover types. Holds window geometry (azimuth, FOV, height) and sun state. Subclasses:
- `AdaptiveVerticalCover` — triangle geometry: `height = (distance / cos(gamma)) * tan(elevation)`
- `AdaptiveHorizontalCover` — extends vertical with awning length/angle
- `AdaptiveTiltCover` — venetian slat angle from research paper (MDPI 1996-1073/13/7/1731)

**`NormalCoverState`** / **`ClimateCoverState`** (calculation.py) — Strategy classes that evaluate whether to use calculated position, default position, or sunset position based on sun validity and climate conditions.

**`SunData`** (sun.py) — Wraps astral library. Generates daily solar position data at 5-minute intervals (`solar_day() -> SolarDay`, cached per local date). `times` is a tuple of tz-aware local datetimes (289 points; 277/301 on DST days); `solar_azimuth`/`solar_elevation` are lists; plus `sunrise()`/`sunset()`/`location`. `nearest_index()` finds the nearest point with `bisect` in UTC.

**`Clock`** (runtime/clock.py) — Where "now" comes from. The coordinator owns one (`coordinator.clock`; `coordinator.default_clock` is the test seam) and hands it to its override manager, cover adapters and `SunData`. Production uses `HassClock` (`dt_util`, which `freezer` freezes).

**`ShadeConfig`** / **`ControlState`** / **`Schedule`** / **`GatePolicy`** (runtime/, P4 batch 1) — Split out of the coordinator, no `hass`. The coordinator rebuilds `self.config = ShadeConfig.from_options(options)` each refresh, keeps the switch toggles in `self.controls` (the switch platform still sets `control_toggle`, `manual_toggle`, ... by name through `ControlToggle` forwards), asks `self.schedule` for the start/end window and `self.gates.first_blocking_gate(...)` for each automatic move.

**`CommandTracker`** / **`ManualDetector`** / **`OverrideTracker`** / **`EndOfDay`** (runtime/, P4 batch 2) — Also no `hass`. `self.commands` holds the commands in flight (`wait_for_target`, `target_call`, `target_call_time`, our context ids, failed sends that may still arrive) and classifies cover reports against them; the coordinator exposes `wait_for_target`, `target_call_time` and `TARGET_TIMEOUT` for the reset button. `self.detector` holds the manual-move rules and latches into `self.manager` (the `OverrideTracker`: latch, override clock, the `hass.data` store). `self.end_of_day` arms the end-time timer, runs the close and keeps undelivered closes for a retry. HA calls (services, timers) reach them as callables the coordinator passes in.

**`Decider`** (runtime/decider.py, P4 batch 3) — Picks the basic or climate position and applies the output transforms (interpolation, or inversion; the min/max clamp stays in the engine). `coordinator.state` and `_transform_state` delegate to `self.decider`, so tracking moves, the forecast and the end-of-day close share one transform chain.

**`Explainer`** / **`RefreshQueue`** (runtime/, P4 batch 4) — `self.explainer` builds what the entities explain (next change event, today's forecast, last change, the move log and the Position sensor's explanation attributes); `coordinator.forecast`, `move_log` and `record_move_provenance` forward to it. `self.events` replaces the four refresh flags: each `RefreshEvent` (ENTITY_CHANGED, COVER_CHANGED, STARTUP, END_TIME) stays pending until its handler marks it done, and cover reports queue in order. Each window entry's coordinator is `entry.runtime_data`; `hass.data[DOMAIN][window_key]` is the index of every loaded window's coordinator (entries and subentries) for the hub, the services and `layers`.

**`WindowEntry`** / **`HouseRuntime`** (windows.py, house.py; P7, ADR 0001/0006) — Two config models run until P8. *Legacy*: one config entry per window (1.x) plus the hub. *House*: the hub is the house entry (2.x) and each window is a `window` config subentry storing the entry's data and options verbatim (`{window_key, data, options}`). `WindowEntry` reads both the same way (`entry_id` = the window key = the old entry_id or a new window's subentry_id); the coordinator, the platforms and `layers`/`shadow` take a `WindowEntry` (or a legacy `ConfigEntry`) and write through `windows.async_update_window`. The house entry's `runtime_data` is a `HouseRuntime`: `async_build_window` per subentry (shared with legacy setup), entities added per platform with `config_subentry_id`, window devices `via_device_id` → house device, a failing window gets a `window_setup_failed_<key>` repair issue and a retry, and the house update listener (`async_sync`) starts/stops/rebuilds only the subentries that changed (an `overrides`-only change re-resolves in place). A fresh install creates the house with subentries; a 1.x house keeps window entries until the owner fixes the `consolidate_house` repair (`consolidate.py`).

### Config Flow (config_flow.py)

Multi-step wizard:
1. **User** → pick blind type + name
2. **Vertical/Horizontal/Tilt** → window geometry parameters
3. **Interpolation** (optional) → custom position mapping
4. **Blind spot** (optional) → shadow exclusion zones
5. **Automation** → timing, delta thresholds, manual override duration
6. **Climate** (optional) → temp/presence/weather/lux/irradiance entities
7. **Weather** (optional) → which weather conditions trigger control

The options flow (`OptionsFlowHandler`) is one sectioned page, `init`:
covers_geometry, sun_behavior, automation_timing and climate. Every field
on the wizard, the options form, the `change_settings` / `add_entry`
schemas and the number entities comes from `settings/spec.py`;
`tests/contract/spec_parity.json` pins what each surface shows
(regenerate with `tests/contract/generate_spec_parity.py`, ledger the diff).

One cover per window (ADR 0002, P3): the cover field is `cover_entity_id`
(single select). Every writer also stores `group: [cover]`, which the
runtime still reads (older versions write only `group`). The wizard, the
options form and `add_entry` (`cover`, or the older `covers` with one item)
refuse a cover another enabled window drives (`window_cover.cover_problem`).
A new entry's unique_id is its cover's entity-registry id. An entry with
several covers keeps working and gets a fixable `split_window` repair issue.

P7 flows: the flow's version is 2. A fresh install's user step creates the
house entry (2.1) with the window as its first subentry; on a 2.x house it
adds a subentry and ends with `window_added`; on a 1.x house it creates a
1.5 window entry as before. `WindowSubentryFlow` is "Add window" (the same
one-screen form; `consolidate_first` on a 1.x house) and a subentry's
Reconfigure (the whole form incl. the exceptions, stored sparsely). The
house entry's options flow is `HouseOptionsFlow` (step `house`): every
house-level setting, stored through `layers.async_set_profile`.

## Solar Algorithm Details

### Gamma (Relative Sun Angle)
```python
gamma = (window_azimuth - solar_azimuth + 180) % 360 - 180
```
Sun is "in front" when `-fov_right < gamma < fov_left` and elevation > 0.

### Vertical Blind Position
```python
blind_height = clip((distance / cos(gamma_rad)) * tan(elevation_rad), 0, window_height)
position = blind_height / window_height * 100
```
Lower sun → more penetration → cover moves down.

### Horizontal Awning Position
Extends vertical calculation using sine rule to find required awning extension.

### Venetian Tilt
```python
beta = arctan(tan(elevation) / cos(gamma))
slat_angle = 2 * arctan(
    (tan(beta) + sqrt(tan(beta)² - (spacing/depth)² + 1)) / (1 + spacing/depth)
)
percentage = slat_angle / 90 * 100  # or /180 for bidirectional
```

## Climate Mode Logic

Two dimensions: **presence** (home/away) and **season** (winter/summer/intermediate).

| Presence | Season | Action |
|----------|--------|--------|
| Home | Summer, sun valid | Use calculated position (block glare) |
| Home | Winter, sun valid | Open fully (passive heating) |
| Home | Any, sun not valid | Default position |
| Away | Summer | Close fully (block heat gain) |
| Away | Winter | Open fully (passive heating) |

Season is determined by comparing current temperature against configurable low/high thresholds
(`engine/season.py`). The `temp_hysteresis` setting (house, area override; HA's temperature
unit, default 0 = off) makes each season sticky: winter lasts until the temperature reaches
low + h, summer until it falls to high − h, and the intermediate band is left only h past a
threshold. The previous season is an input: each window's coordinator keeps the last one in
memory only, so the first decision after a restart or reload uses the plain rule.

## Entity Inventory (per config entry)

Names come from `translation_key` + `strings.json` (`has_entity_name`), so
friendly names read "<Device> <Role>". Unique_id suffixes (in parentheses)
are frozen; categories and default visibility come from one table in
`entity_surface.py` (refactor plan, "Entity surface"; P1). Config entry
1.1 -> 1.2 (`async_migrate_entry`) applies the table to existing registry
rows without overriding user choices. 1.2 -> 1.3 (P3, `migration.py`)
writes every option the entry reads through a code fallback into its
options, the cover as `cover_entity_id`, and the cover's registry id as
unique_id. 1.3 -> 1.4 (P5 shadow, `shadow.py`) lifts every window into
house / floor / area profiles in the hub's options and a sparse
`overrides` per window, recording the states of the switches P5 drops;
since the P5 flip the runtime acts on them (`layers.py`: every refresh
resolves window -> area -> floor -> house -> default; one-time settings
come from the window's options), edits store sparsely in them (the
options form, `change_settings`: recurring values as the window's
`overrides`, one-time ones in its options) and the legacy flat keys are
left for a downgrade. A house that was never lifted lifts itself at setup.
1.4 -> 1.5 (P5 flip) hides the six switches (hidden_by integration, still
enabled): they are aliases of the Mode select and the toggle settings for
one release. At setup the window device copies the physical cover's area
if it has none.

| Platform | Name (unique_id suffix) | Visibility | Purpose |
|----------|-------------------------|------------|---------|
| sensor | Target position (`Cover Position`) | primary | Calculated position (0-100%); attributes include `window_key`, `cover_entity`, `cover_type`, `override_until`, `next_move`, `provenance` (non-house sources of the layered settings; P5) |
| select | Mode (`mode_select`) | primary | `auto` / `hold` / `off` (P5 flip): the window's control state, restored (first boot: from the Toggle Control switch); attribute `until` while held. Entity service `adaptive_cover.hold(duration?, position?)` |
| button | Return to auto (`Reset Manual Override`) | primary | Mode auto: end a hold (move back) or turn an off window on |
| binary_sensor | Manual override (`Manual Override`) | diagnostic | Any cover under manual control? (attribute `until`) |
| binary_sensor | Sun in front (`Sun Infront`) | diagnostic | Is sun within window FOV? |
| sensor | Control method (`Control Method`) | diagnostic | "winter" / "summer" / "intermediate" |
| sensor | Start sun, End sun, Next change, Last change | diagnostic, disabled by default | Solar times and the next/last change |
| switch | Automatic control, Manual override detection, Climate mode, Outside temperature, Lux, Irradiance | config, hidden (enabled) | Aliases until P8: Automatic control writes/mirrors the Mode; the others still set the window's ControlState (house settings `manual_detection`, `climate_on`, `use_*` in the stored layers) |
| hub switch | Climate (`climate_on`), Manual-move detection, Use outside temperature / lux / irradiance | primary (Climate), config | The house's settings (P5 flip); a change reaches every window without a reload |
| hub number | Heating / cooling threshold, threshold hysteresis, manual override duration (min), eye height, seat distance, privacy delay | config | The house's settings (P5 flip); the window numbers are gone (rows removed at setup) |
| hub time | End time, quiet hours start, quiet hours end | config | The house's settings (P5 flip) |

## Manual Override Detection

1. Cover state change event fires
2. A human move is detected by any of: foreign `opening`/`closing` when no
   command is in flight (motion-start latch); motion AGAINST our in-flight
   command's direction; a definitive landing inside the travel window that
   differs from OUR commanded target; or a landing that differs from the
   computed state when idle. Landings matching our own commanded target
   (±`TARGET_TOLERANCE`) are never manual, even if the computed state
   drifted during travel.
3. Every override expires after `CONF_MANUAL_OVERRIDE_DURATION` and
   auto-control resumes (user intent: a manual move wins for ~the
   configured window, e.g. 1.5-2 h). `CONF_MANUAL_OVERRIDE_RESET` only
   controls whether LATER manual moves restart that clock (True) or the
   clock runs from the first manual move (False). Day rollover
   (local-date) clears any leftover override as a safety net.
4. Override state lives in `hass.data[f"{DOMAIN}_manual_state"]` and
   survives options reloads; only an EXPLICIT manual-toggle off clears it.
   Across a restart the Mode select restores a hold with its `until`.
5. The scheduled end-of-day close bypasses manual overrides when it fires
   on time; a catch-up close (armed late after restart/reload) respects
   them. Undeliverable end-of-day closes (cover unavailable) retry when the
   cover returns.
6. Since the P5 flip an override is the window's Mode `hold`. A requested
   hold (Mode hold, `adaptive_cover.hold`) has a fixed end
   (`OverrideTracker.hold_until`): the restart-clock option, the day
   rollover and detection off do not end it; Mode auto or off does.
   Mode `off` is no moves and no detection (the old Toggle Control off).

Code: the rules in 2 are `ManualDetector` (runtime/manual_detector.py)
over `CommandTracker` (runtime/command_tracker.py); 3 and 4 are
`OverrideTracker` (runtime/override_tracker.py); 5 is `EndOfDay`
(runtime/end_of_day.py); 6 is `ModeControl` (runtime/mode.py).

## Development & Testing

Environment and tasks come from `pixi.toml` (see `CONTRIBUTING.md`):

```bash
pixi install          # environment from pixi.lock
pixi run test         # full pytest suite, parallel (pytest -n auto)
pixi run lint         # ruff
pixi run typecheck    # pyright (strict and zero errors on engine/ and runtime/)
pixi run mutations    # mutation kill matrix (tests/mutation_set/)
pixi run pytest tests/simulation -q   # one tier or file
```

Don't `pip install` into the pixi env; use `pixi add`. The card has its
own npm toolchain in `card/` (`npm test`, `npm run typecheck`,
`npm run lint`, `npm run build`); commit the rebuilt bundle in
`custom_components/adaptive_cover/www/` with any card change.

### Test tiers

| Tier | Path | Pins |
|------|------|------|
| Engine | `tests/engine/` | pure `evaluate()`/geometry, property sweeps; `test_purity.py` guards engine purity |
| Runtime | `tests/runtime/` | runtime components called directly with fakes, no `hass` fixture (implementation tier); `test_no_hass.py` guards it |
| Characterization | `tests/characterization/` | `climate_truth_table.json` (216 combos), golden day schedules in `goldens/`, outbound service calls |
| Simulation | `tests/simulation/` | full-day SimHouse replays of the REAL integration (fake shades, real astral sun, stepped frozen clock) |
| Entity surface | root `tests/test_*.py` | config flow, options, services, entities, hub, restore — through a real config entry |
| House replay | `tests/replay/` | the real house configs on 6 dates (DST start/end, equinoxes, solstices): outbound command timeline |
| Contract | `tests/contract/` | `behavior_tier_ids.txt` + `ledger.md`, checked by `check_behavior_tier.py` |
| Card | `card/tests/` | vitest |

- **Simulation harness**: see `tests/simulation/README.md` for the SimHouse
  API. New coordinator-level bugs get a scenario there (symptom pin) in
  addition to unit regressions. Resolve entities with `house.eid(...)`;
  never hard-code entity_ids.
- **Pinned outputs** (truth table, goldens, house replay) must stay
  byte-identical unless behavior is meant to change. Regenerate
  deliberately — truth table:
  `PYTHONPATH=. pixi run python tests/characterization/generate_truth_table.py`;
  goldens: `UPDATE_GOLDENS=1 pixi run pytest tests/characterization/test_golden_days.py`.
  The diff is the review artifact and needs a ledger entry.
- **Mutations**: `tests/mutation_set/make_patches.py` defines every
  mutation as an exact-unique text replacement and writes the patches +
  `manifest.json`; `--check` fails when a committed patch is stale or no
  longer applies. `run_mutations.py` applies each patch, runs the tiers,
  and reverts. Kill bar: 100%. Code moves re-anchor their mutations in
  the same PR with unchanged descriptions.
- **Behavior-tier ledger** (`tests/contract/`): removing or renaming a
  behavior-tier test id, or changing a pinned output, needs a `ledger.md`
  entry naming retired tests, replacements and re-targeted mutations
  (ADR 0004).
- **Release gate** (every release): CI green, behavior tier passes,
  100% mutation kills, `make_patches.py --check` passes, pinned outputs
  byte-identical or ledgered, no silent removals from
  `behavior_tier_ids.txt`.

### Test rules

- Every bug fix gets a `test_regression_<slug>` naming the commit, in
  its own commit.
- Time is always an input; never call `datetime.now()` in logic. Outside
  `runtime/clock.py` nothing reads the wall clock: use the coordinator's
  `clock` (`tests/engine/test_purity.py` scans for it).
- New tests reach the integration through public surfaces only (entity
  states, registries, services, SimHouse helpers) — no `hass.data`,
  coordinator attributes or private attributes.

## Dependencies

- **astral** — solar position calculations; the only manifest requirement
- **voluptuous** — config schema validation (ships with HA)
- **python-dateutil** — time-string parsing in `helpers.py`; not declared,
  it ships with HA core (hass-nabucasa -> pycognito -> boto3 -> botocore)

pandas, numpy and pytz were removed in P2 (ADR 0005): the day table uses
the standard library, trigonometry uses `math` (`engine/numeric.py` has
`clip`/`interp`, checked against numpy) and time zones come from
`dt_util` / `zoneinfo`. `tests/engine/test_purity.py` fails on any other third-party
import. The test environment still has numpy (pytest-homeassistant-custom-
component pins it) and pytz (astral 2.2 needs it); only tests use numpy, as
the reference for `engine/numeric.py`.

## Patterns Worth Knowing

- **Coordinator pattern**: single `DataUpdateCoordinator` per config entry, all entities subscribe
- **RestoreEntity**: the Mode select (control state, a hold's end) and the switch aliases persist across HA restarts
- **Executor offload**: solar calculations run in `hass.async_add_executor_job` to avoid blocking
- **Contextual logging**: `ConfigContextAdapter` prepends config name to all log messages
- **Service call throttling**: position delta + time delta + timing window gates before calling covers
- **Config merging**: options flow updates `config_entry.options`; coordinator merges `data + options`

## Fork & Release Workflow

This is a fork of [basbruss/adaptive-cover](https://github.com/basbruss/adaptive-cover) hosted at [mrvollger/adaptive-cover](https://github.com/mrvollger/adaptive-cover). License: MIT (`LICENSE`).

### Development

1. Branch from `main` for non-trivial changes.
2. Run `pixi run lint`, `pixi run typecheck` and `pixi run test`
   (see "Development & Testing").
3. Open a PR against `main`; CI must be green.

### Releasing to HACS

HACS requires a GitHub Release to see updates. A release is a tag push:

```bash
# after committing the new "version" in custom_components/adaptive_cover/manifest.json
git tag v1.x.x
git push origin v1.x.x
```

The release workflow checks that the manifest version equals the tag and
publishes the GitHub release. Don't create releases by hand with
`gh release create`. HACS then shows the update; the user clicks
**Update** in HACS → restarts HA. Rollback: downgrade in HACS.

### HACS Configuration

- `hacs.json` has `"zip_release": false` — HACS downloads the repo directly (no zip artifact needed)
- The repo must have at least one GitHub Release for HACS to install it
- Users add `https://github.com/mrvollger/adaptive-cover` as a **Custom Repository** (category: Integration) in HACS

### Deploying Without HACS

Alternatively, SSH into the HA instance and copy files directly:

```bash
cd /tmp
git clone https://github.com/mrvollger/adaptive-cover.git
cp -r adaptive-cover/custom_components/adaptive_cover /config/custom_components/
rm -rf /tmp/adaptive-cover
# Then restart HA
```

### Important Notes

- HA config (integration settings) is stored in `.storage/core.config_entries`, not in the integration code — replacing the code preserves configuration
- If the upstream repo was previously installed via HACS, remove it first before adding this fork
- Delete any `adaptive_cover.bak` directories in `custom_components/` — HA will try to load them as integrations

## Redesign Architecture (v1.1.0+)

### Pure Engine (`custom_components/adaptive_cover/engine/`)

All math and strategy logic lives in a pure package: no `homeassistant`
imports, no wall-clock reads, no entity access (enforced by
`tests/engine/test_purity.py`). `calculation.py` classes are thin HA
adapters that build typed inputs and delegate. Since P2 the package is
scalar `math` (no numpy) and pyright-strict with zero errors
(`pixi run typecheck` allows no baseline there).

- `models.py` — `CoverConfig`, `SunSnapshot`, `TimeContext`, `ClimateInputs`,
  `Overhang`, `GlareModel`, `PrivacyConfig`, `Decision(position, intent, trace)`
- `geometry.py` — gamma/FOV/elevation checks, per-cover-type percentages,
  profile angle, overhang shadow line (`sunlit_top`), glare-safe height
- `evaluate.py` — `evaluate(config, sun, ctx, climate=None) -> Decision`;
  privacy runs first, then climate/basic strategy branches
- `season.py` — `decide_season(SeasonInputs, previous) -> Season`: the
  winter/summer thresholds with the `temp_hysteresis` margin; the previous
  season comes in and the new one goes out (the coordinator keeps it)

Key domain rule (sunlit-band asymmetry): position = f(sunlit_band, intent).
ADMIT_NO_GLARE cares about the band's top vs eye height; BLOCK cares whether
the band is non-empty. Same sun, cold vs hot day, opposite positions.

### New features & options

- Overhang: `overhang_depth`, `overhang_height` (vertical covers)
- Glare band: `eye_height`, `occupied_distance` (engages on sunny winter
  days with presence; cloudy/away keep historical fully-open)
- Privacy: `privacy_mode`, `privacy_offset`, `privacy_position`
- Smoothing: `quiet_start`/`quiet_end`, `max_moves_hour` (snap positions
  bypass both gates)
- Position sensor attributes: `intent`, `decision_trace`, `forecast_today`
- Service: `adaptive_cover.get_forecast` (entry id or title)

Testing for the engine and everything else is in "Development & Testing"
above.
