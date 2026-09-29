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
├── calculation.py           # HA adapters: build engine inputs, delegate to engine/
├── engine/                  # Pure math and strategy (no HA imports, no clock reads)
│   ├── models.py            # Typed inputs/outputs (CoverConfig, SunSnapshot, Decision, ...)
│   ├── geometry.py          # Gamma/FOV/elevation, per-cover-type %, overhang, glare-safe height
│   └── evaluate.py          # evaluate(config, sun, ctx, climate=None) -> Decision
├── sun.py                   # Astral-based solar table (5-minute points)
├── config_flow.py           # Multi-step UI configuration (setup + options)
├── options_spec.py          # Changeable options for the change_settings service
├── const.py                 # All config keys, defaults, enums
├── hub.py                   # "Adaptive Cover All" hub device (all-shades cover, house mode select, reset-all button)
├── cover.py                 # Cover platform: only the hub's aggregate cover
├── sensor.py                # Position %, solar times, control method, next/last change
├── binary_sensor.py         # Sun in front, manual override active
├── switch.py                # Toggle switches (control, climate mode, lux, etc.)
├── select.py                # Mode select: one control instead of several toggles
├── number.py                # Live tunables that skip the options wizard
├── button.py                # Reset manual override button
├── entity_shared.py         # Shared entity helpers
├── frontend.py              # Serves and auto-registers the bundled Lovelace card
├── logbook.py               # Logbook text for adaptive_cover_moved events
├── helpers.py               # Utility functions (safe state access, datetime parsing)
├── config_context_adapter.py # Logger adapter that tags logs with config name
├── diagnostics.py           # HA diagnostics export
├── services.yaml            # get_forecast, change_settings, add_entry
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
├── characterization/        # Climate truth table, golden days, outbound service calls
├── simulation/              # SimHouse full-day replays (README.md = harness API)
├── replay/                  # House-replay goldens: real configs x 6 dates (added in P0)
├── contract/                # behavior_tier_ids.txt, ledger.md, check_behavior_tier.py (added in P0)
├── mutation_set/            # One patch per mutation (M01–M43), make_patches.py, run_mutations.py
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
  tier/mutation gate, 0005 drop pandas/numpy/pytz. A new design decision
  gets a new ADR; an accepted ADR is superseded, not rewritten.
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

**`AdaptiveDataUpdateCoordinator`** (coordinator.py) — The hub. Inherits HA's `DataUpdateCoordinator`. Listens to state changes, runs the calculation pipeline, calls cover services, tracks manual overrides. Contains `AdaptiveCoverManager` for per-cover override state.

**`AdaptiveGeneralCover`** (calculation.py) — Abstract base for all cover types. Holds window geometry (azimuth, FOV, height) and sun state. Subclasses:
- `AdaptiveVerticalCover` — triangle geometry: `height = (distance / cos(gamma)) * tan(elevation)`
- `AdaptiveHorizontalCover` — extends vertical with awning length/angle
- `AdaptiveTiltCover` — venetian slat angle from research paper (MDPI 1996-1073/13/7/1731)

**`NormalCoverState`** / **`ClimateCoverState`** (calculation.py) — Strategy classes that evaluate whether to use calculated position, default position, or sunset position based on sun validity and climate conditions.

**`SunData`** (sun.py) — Wraps astral library. Generates daily solar position data at 5-minute intervals. Provides sunrise/sunset, azimuth/elevation lists.

### Config Flow (config_flow.py)

Multi-step wizard:
1. **User** → pick blind type + name
2. **Vertical/Horizontal/Tilt** → window geometry parameters
3. **Interpolation** (optional) → custom position mapping
4. **Blind spot** (optional) → shadow exclusion zones
5. **Automation** → timing, delta thresholds, manual override duration
6. **Climate** (optional) → temp/presence/weather/lux/irradiance entities
7. **Weather** (optional) → which weather conditions trigger control

Both initial setup (`ConfigFlow`) and edit (`OptionsFlowHandler`) share the same step logic via `_SchemaCommonFlowHandler`.

## Solar Algorithm Details

### Gamma (Relative Sun Angle)
```python
gamma = (window_azimuth - solar_azimuth + 180) % 360 - 180
```
Sun is "in front" when `-fov_right < gamma < fov_left` and elevation > 0.

### Vertical Blind Position
```python
blind_height = clip(
    (distance / cos(gamma_rad)) * tan(elevation_rad),
    0, window_height
)
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

Season is determined by comparing current temperature against configurable low/high thresholds.

## Entity Inventory (per config entry)

| Platform | Entity | Purpose |
|----------|--------|---------|
| sensor | Cover position | Calculated position (0-100%) |
| sensor | Start sun time | When sun enters FOV |
| sensor | End sun time | When sun leaves FOV |
| sensor | Control method | "winter" / "summer" / "intermediate" |
| binary_sensor | Sun in front | Is sun within window FOV? |
| binary_sensor | Manual override | Any cover under manual control? |
| switch | Toggle control | Enable/disable auto positioning |
| switch | Toggle manual override | Enable/disable override detection |
| switch | Toggle climate mode | Basic vs climate mode |
| switch | Toggle outside temp | Use outside temp sensor (climate only) |
| switch | Toggle lux | Use lux sensor (climate only) |
| switch | Toggle irradiance | Use irradiance sensor (climate only) |
| button | Reset manual override | Clear all manual override states |

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
5. The scheduled end-of-day close bypasses manual overrides when it fires
   on time; a catch-up close (armed late after restart/reload) respects
   them. Undeliverable end-of-day closes (cover unavailable) retry when the
   cover returns.

## Development & Testing

Environment and tasks come from `pixi.toml` (see `CONTRIBUTING.md`):

```bash
pixi install          # environment from pixi.lock
pixi run test         # full pytest suite, parallel (pytest -n auto)
pixi run lint         # ruff
pixi run typecheck    # pyright
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
- Time is always an input; never call `datetime.now()` in logic.
- New tests reach the integration through public surfaces only (entity
  states, registries, services, SimHouse helpers) — no `hass.data`,
  coordinator attributes or private attributes.

## Dependencies

- **astral** — solar position calculations
- **pandas** — time series (5-min interval generation); declared in the manifest
- **numpy** — trigonometry, interpolation, clipping; imported but not declared
- **pytz** — time zones in `coordinator.py`; imported but not declared
- **voluptuous** — config schema validation (ships with HA)

pandas, numpy and pytz are removed in P2 (ADR 0005).

## Patterns Worth Knowing

- **Coordinator pattern**: single `DataUpdateCoordinator` per config entry, all entities subscribe
- **RestoreEntity**: switches persist state across HA restarts
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
adapters that build typed inputs and delegate.

- `models.py` — `CoverConfig`, `SunSnapshot`, `TimeContext`, `ClimateInputs`,
  `Overhang`, `GlareModel`, `PrivacyConfig`, `Decision(position, intent, trace)`
- `geometry.py` — gamma/FOV/elevation checks, per-cover-type percentages,
  profile angle, overhang shadow line (`sunlit_top`), glare-safe height
- `evaluate.py` — `evaluate(config, sun, ctx, climate=None) -> Decision`;
  privacy runs first, then climate/basic strategy branches

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
