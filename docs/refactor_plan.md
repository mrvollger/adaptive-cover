# Adaptive Cover refactor plan

## Summary

**What you will see at the end**

- **One Shades dashboard** controls the whole house. HA builds it for you: New dashboard → Community → *Adaptive Cover*. It has three levels:
  - **House bar.** Mode chips Auto / Hold / Off. The bar shows *Mixed* when windows differ. It also has Return all to auto, Hold all…, Open all, Close all, a Climate on/off switch, and a ⚙ button for house settings (thresholds, override duration, eye height, privacy, quiet hours, end time).
  - **Headings per floor, then per room**, taken from HA floors and areas. For example, "Upstairs › Office · 2 auto, 1 hold". Each heading has one-tap Auto / Hold / Return, and a ⚙ for the settings of that room or floor. Each value shows where it comes from, for example "inherited from House".
  - **One row per window.** Each row has a position bar with the target, a status chip ("Auto · blocking glare", "Hold until 14:30", "Off"), the next move ("→ 40 % at 15:10"), ↑ ■ ↓, and Return to auto.
- **Tapping a row** opens today's detail dialog with the forecast, the decision trace and the compass. Its **Window setup** button goes directly to that window's geometry form. You use that form once per window.
- **Adding a window takes one screen.** On the Adaptive Cover integration, click **Add window**. Then:
  1. Pick a cover. Covers that are already managed are hidden.
  2. Optionally pick *Copy from* (another window, or the East / South / Door preset).
  3. Enter the azimuth, plus the height for a blind.

  The name, the type and the room come from the cover. Everything else is inherited.
- **One window = exactly one cover.** A window cannot hold several covers. The same cover cannot be added twice.
- **Fewer entities.** Each window shows 3 entities (Position, Mode, Return to auto) instead of 21. The house goes from 318 loaded entities to about 49 primary ones. The rest are diagnostic or removed.
- **What does not change:** today's behavior (sun math, override rules, end-of-day close), your entity_ids, the hub entities, and your existing tile and compass cards. The house migrates only when you click **Consolidate** in a repair notice, after a backup.

## Goals and non-goals

**Goals**
- G1: One place to control every shade.
- G2: Setup that already has your defaults.
- G3: One cover per window.
- G4: A typed, pandas-free, split codebase with one declarative option spec.
- G5: Measurably easier to test and maintain. The targets are in the testability section.

**Non-goals**
- Changing the solar or glare algorithm (`engine/` is frozen).
- Supporting HA versions older than 2026.8.
- Rewriting the card framework.
- Renaming physical cover entities (`cover.sw_sw_shade` and the others). HA owns those, not this integration.

## One-time vs recurring settings

**Rule:** a setting you might change more than once lives at house level. A room or floor may override it, and a window override exists only where the "Narrower" column allows it. One-time settings live only in the window setup form.

| Setting / control | Class | Home | Narrower override |
|---|---|---|---|
| Cover (exactly one); name, type, area (read from the cover) | one-time | window setup | — |
| Azimuth, FOV left/right, window height, distance to shaded area | one-time | window | — |
| Awning length/angle; slat depth/spacing/tilt mode | one-time | window | — |
| Overhang depth/height, min/max elevation, blind spot | one-time | window (preset / copy-from) | — |
| Min/max position and their enable flags, inverse, interpolation, transparent blind | one-time | window › Advanced | — |
| Privacy opt-in (window faces the street) | one-time | window | — |
| "Ignore climate" exception | one-time | window › Exceptions | — |
| Mode Auto / Hold / Off; Return to auto; Hold N h; open/close/stop | recurring control | row, room, floor, house (`select.select_option`, `button.press`, `adaptive_cover.hold` targeted at an area or floor) | — |
| House mode, Return all | recurring control | house | — |
| Climate on/off | recurring | house switch | area |
| Heating / cooling thresholds | recurring | house | floor, area |
| Indoor temperature sensor | recurring | floor | area |
| Weather entity, sunny states, presence, outside temp / lux / irradiance entities, their use-flags and thresholds | recurring (rare) | house | — |
| Manual-move detection; override duration; restart clock on later moves; ignore intermediate positions | recurring | house | area |
| Eye height, seat distance | recurring | house | area, window |
| Start time / sunrise offset; end time / sunset offset; return at sunset | recurring | house | area |
| Default position, sunset position | recurring | house | area, window |
| Privacy delay, offset, position | recurring | house | area |
| Quiet hours, max moves/hour, position delta, time delta | recurring | house | — |

**Enforcement:** each spec `Opt` has `scope` and `overridable_at`, and a spec test checks the table above.
- Every recurring key can be reached from a house, floor or room sheet.
- The window form shows recurring keys only inside its collapsed *Exceptions* section.

## Target design

### Config model

```
House entry (today's hub entry, promoted; same entry_id; VERSION 2 after consolidation)
 ├─ options: {house:{…}, floors:{floor_id:{sparse}}, areas:{area_id:{sparse}}, unit_system}
 └─ subentries "window" (one per cover)
     unique_id = cover's entity-registry id   → a duplicate cover aborts
     data: {window_key, cover_entity_id, cover_type, geometry:{…}, overrides:{sparse}}
```

- **`window_key`** is the old entry_id for migrated windows and the subentry_id for new ones. It is the unique_id prefix, the override-store key and the card binding key. Because migrated windows keep their old entry_id as the key, **no unique_id or override state is ever re-keyed.**
- **Resolution** is `settings/resolve.py`, a pure function. Precedence: window override → area → floor → house → spec default. It returns a frozen `WindowConfig` plus the provenance of each key. The card uses the provenance to show "inherited from …".
  - The area and floor are read live from the window device. That device's area is copied from the physical cover.
  - Windows read the house's *stored* options, not its runtime state, so startup order does not matter.

### Built-in defaults (your values)

These defaults are the spec defaults for new installs. For the live house, a lift migration computes the house layer: the house gets the most common value, and a floor or area gets any value its windows all share. Anything left over stays as a window override.

| Scope | Values |
|---|---|
| House | climate **on**; thresholds **72 / 75 °F** (22 / 24 °C on metric); weather `weather.forecast_home_2`; sunny states sunny, partlycloudy, clear, windy, windy-variant; eye height 1.2 m; seat distance 2 m; delta position 1 %; delta time 2 min; override duration **2:00**, restart clock off, ignore intermediate off, detection on; end 00:00; return at sunset off; outside / lux / irradiance thresholds 0 / 1000 / 300; privacy delay 30 min, position 0; default position 100 |
| Upstairs floor | `sensor.upstairs_indoor_temperature` |
| Main + Ground floors | `sensor.downstairs_indoor_temperature` |
| SW bedroom, Den areas | start 06:00, sunset offset −30, default position 97 |
| Office area | start 07:30, sunrise offset +45 |
| Presets (copy-from) | **East:** az 100, FOV 90/44, max elevation 50, offsets −20/+20. **South:** az 190, FOV 50/50, overhang 1.2/2.6, privacy on. **Door:** az 145, FOV 40/40, overhang 1.2/2.3, min position 9, max elevation 40, sunset position 3 |

### Entity surface

**Per window.** Each window has one device. The house entry and the window subentry own it, `via_device_id` points to the house device, and the area comes from the cover. `has_entity_name` and `translation_key` provide the names. **Unique_ids do not change.**

| Entity (unique_id suffix kept) | Visibility |
|---|---|
| sensor Target position (`Cover Position`). New attributes: `window_key`, `cover_entity`, `cover_type`, `override_until`, `next_move`, `provenance` | primary |
| select Mode `auto` / `hold` / `off` (`mode_select`). RestoreEntity; the source of truth for control state | primary |
| button Return to auto (`Reset Manual Override`) | primary |
| binary_sensor Manual override (attribute `until`); Sun in front; sensor Control method (climate only) | diagnostic, enabled (the card and M40–M42 use them) |
| sensor Start sun, End sun, Next change, Last change | diagnostic, disabled by default |
| 6 switches | hidden aliases from P5, removed in P8 |
| 7 numbers | removed in P5. Thresholds and privacy move to the house. Eye height and seat distance become house settings with area/window overrides. Overhang becomes geometry |

**Mode meanings**
- `hold` means a manual override with an expiry. A detected manual move sets `hold`. Selecting `hold` holds for the resolved override duration.
- `off` means no moves and no manual-move detection. It is today's "Manual" / Toggle Control off.

**House device.** The entity_ids stay the same.
- Primary:
  - `cover.adaptive_cover_all`
  - `select.adaptive_cover_all_cover_control_mode`: Auto / Hold / Off, with a display-only Mixed. It changes each window's Mode directly.
  - `button.adaptive_cover_all_reset_all_manual_overrides`
  - Climate switch
- CONFIG: detection switch; heating/cooling thresholds (unit-aware); eye height; seat distance; override duration; privacy delay; end / quiet start / quiet end (time entities).

**Services**
- `adaptive_cover.hold(duration, position?)`. An entity service on Mode, so it can target an area or floor. `position` lets `automation.meeting` close the office covers and hold them in one call.
- `adaptive_cover.set_profile(scope, **opts)` saves the room and floor sheets.
- `change_settings`, `add_entry` and `get_forecast` keep their names and response schemas. Their input schemas are generated from the spec.
- There is no custom `set_mode` or `resume_auto`. The built-in `select.select_option` and `button.press` already accept area and floor targets.

### UI

- **Dashboard strategy** `ll-strategy-dashboard-adaptive-cover`, registered through `window.customStrategies` (HA 2026.5+). It filters `hass.entities` on `platform === "adaptive_cover"` and excludes hidden and disabled entities.
- **House card** `custom:adaptive-cover-house-card` has the same layout. You can drop it into `dashboard-shades`.
- **Mode chips** are a custom tile card feature (`customCardFeatures`), so stock tile cards can show them.
- **Card binding.** Cards bind by `window:` (window_key) or `cover:`. Old `entry_id:` configs still resolve, because the entry_id is the window_key. Discovery reads the Position attributes first and uses the unique_id prefix as a fallback. It never filters on `config_entry_id`.
- **Card editors** use `getConfigForm`.
- **Limitation:** custom integrations cannot change the more-info dialog, so all detail stays in the card dialog.

### Backend layout

```
engine/    FROZEN pure math (numpy → math + 10-line interp)
settings/  spec.py (Opt table) · resolve.py · lift.py · schema.py (generated vol/selector) · validate.py
runtime/   clock.py · solar_day.py · schedule.py · climate_reader.py · decider.py · command_tracker.py
           override_tracker.py · manual_detector.py · gates.py · actuator.py · explainer.py
           events.py (typed queue) · window.py (WindowCoordinator ≤300 lines) · house.py (HouseRuntime)
flows/     house.py · window.py (ConfigSubentryFlow user+reconfigure) · migrate.py · repairs.py
services.py · diagnostics.py (per device) · frontend.py · <platform>.py
```

- `entry.runtime_data: HouseRuntime`. `hass.data[DOMAIN]` goes away, except for the override store.
- The update listener compares `entry.subentries`: a changed window is rebuilt alone. A house-profile change re-resolves every window in place, with no reload.
- Each window sets up in isolation. A failing window raises a repair issue, and the rest of the house keeps running.
- Deleted: `coordinator.py`, `calculation.py`, `sun.py`, pandas, numpy and pytz. `manifest.requirements` keeps only astral, or becomes `[]` if astral is vendored through HA's sun helper.

## Phases

**Every release passes this gate:**
- CI is green.
- The behavior tier passes.
- The mutation kill rate is 100%, and the simulation tier alone kills at least the P0 baseline set.
- `make_patches.py --check` passes.
- The goldens, the truth table and the **house replay** are byte-identical, or the PR carries a ledger entry that explains the diff.
- `behavior_tier_ids.txt` has no silent removals.

**How moved code is handled:** a PR that moves code re-anchors its mutations in the same PR, and the reviewer confirms that each mutation's description did not change. Each fixed defect gets a `test_regression_<slug>` and its own commit.

**Size key:** S = up to 1 week, M = 1–2 weeks, L = 3+ weeks.

### P0: Foundations, no behavior change (v1.14.0, M)

- **CI:**
  - Pin `pytest-homeassistant-custom-component` to the HA 2026.8 release and to latest.
  - Make CI a required check.
  - Re-enable hassfest and HACS validation.
  - Add jobs: ruff check, ruff format, pyright (basic, baseline file), `pytest -n auto`, vitest, tsc, eslint, and a check that the card bundle is fresh.
  - Make DeprecationWarnings from our own package an error.
- **HA version:** one minimum, 2026.8, set in hacs.json and in the phcc pin. Delete the pyproject poetry block and `poetry.lock`.
- **Test net:**
  - Re-measure the mutation baseline (the current one is stale).
  - Add `run_mutations.py --jobs N` (parallel worktrees), `make_patches.py --check`, `behavior_tier_ids.txt` and the contract ledger.
  - Add a sanitized **live-snapshot fixture**: config entries, entity and device registries, restore_state, the override store, and the dashboard-shades JSON (hash `fe8b68210008ffb2`).
  - Add **house-replay goldens**: the 15 real configs on 6 dates (DST start and end, both equinoxes, both solstices), with scripted weather and manual moves. They pin the outbound command timeline.
  - Add **WindowHandle**: a test API that finds entities by role through the registry, keyed by cover. Port the 48 `hass.data` reads and the coordinator-attribute reads to it.
  - Add seams `coordinator.is_own_context()` and `sun_data_factory`.
- **Hygiene:**
  - Translations: English-only (already done 2026-09-28: es/de/fr/nl/sk removed). Add a CI check that `translations/en.json` matches `strings.json`, and drop the card's de/fr strings.
  - Fix the failing sky-compass vitest.
  - Run ruff format once and keep a single ruff config.
  - Untrack `node_modules`, `notebooks/` and `sim_plot.png`.
  - Fix the LICENSE and pyproject mismatch.
  - Rewrite CONTRIBUTING.md and add ADR 0001–0005.
- **Release workflow:** a tag push checks that the manifest version equals the tag, rebuilds the card, runs the gate, and publishes the release.
- **Live house:** take a backup, then delete the 3 disabled SE multi-cover entries (they are decision-free leftovers).
- **Rollback:** HACS downgrade.

### P1: Quick UI wins on today's model (v1.15.0, S)

- **Scope:**
  - A MINOR config migration (1.1 → 1.2) calls `er.async_update_entity` to apply the categories and disabled defaults above. New `entity_category` values only affect new registry rows, so existing rows need this call.
  - `dr.async_update_device(area_id=)` copies each physical cover's area. Today 12 of 15 window devices have no area.
  - Entity names come from translations.
  - New Position attributes.
  - The card discovers windows through attributes and the unique_id prefix, not `config_entry_id`.
  - The dialog's configure button links directly to that window's settings.
  - The Mode select becomes primary. It keeps today's vocabulary for now.
  - **Naming cleanup** (decision 5): dry-run list → owner approval → backup → rename entities, devices and physical covers to the `<area>_<window>_<role>` scheme, rewriting every reference in the same step.
- **Tests:** surface tests for category, visibility and area; vitest discovery against the snapshot registry and a subentry-shaped registry.
- **Rollback:** downgrade. The category and area changes are harmless to older code.

### P2: Dependency diet and engine typing (v1.15.x, S)

- **Scope:**
  - Remove pandas. A UTC 5-minute stepper keeps 289 points (the end is inclusive), and 277 or 301 points on DST days. `bisect` replaces the nearest-point lookup.
  - Replace numpy with `math` and wrap values in `float()`.
  - Replace pytz with `dt_util`.
  - Add a `Clock` protocol. No `now()` or `utcnow()` calls remain outside `runtime/clock.py`.
  - Bring `engine/` to 0 pyright-strict errors.
  - Move the test fakes off pandas.
- **Tests:** goldens and replay byte-identical; a pin on the DST point counts; M36 and M37 re-anchored.

### P3: One option spec and one cover per window (v1.16.0, M-L)

- **Scope:**
  - The first commit snapshots each surface's key, default, min and max into `spec_parity.json`.
  - `settings/spec.py` then generates the wizard, the options, the `change_settings` and `add_entry` schemas, and the live numbers.
  - `ShadeConfig.from_options` replaces the positional adapter constructors.
  - Delete the unreachable options steps (about 600 lines) and the 7 copies of the elevation check.
  - **Ledgered drift fixes:**
    - Height and distance max are 10.
    - `delta_time` min is 0. This is the wider range, so no stored value becomes invalid.
    - Thresholds are unit-aware everywhere.
  - **One cover:**
    - The selector uses `multiple=False`, and `add_entry` takes `cover`.
    - A MINOR migration (1.3) writes `cover_entity_id`, still writes `group:[cover]` for rollback, and sets the entry unique_id to the cover's registry id.
    - An entry with more than one cover gets a fixable "split" repair.
    - Before any default changes, the migration **writes every value the entry currently gets from code defaults into its options**. This covers Leanne's and Den's thresholds, so the new defaults cannot move them.
- **Tests:**
  - A spec round-trip property test: wizard ↔ options ↔ service ↔ normalize.
  - Cross-field validators.
  - Migration on the snapshot.
  - SimHouse `covers=[a,b]` creates two windows.
  - **M44:** a duplicate cover is accepted.

### P4: Split the coordinator (v1.17.x, L, about 8 move-only PRs)

- **Scope:**
  - Split out one component per PR, in this order: ShadeConfig/ControlState (M13), Schedule (M05–M06), GatePolicy (M01–M04, M07), CommandTracker, ManualDetector and OverrideTracker (M08–M12), EndOfDay (M14–M18), Decider (M35–M38), Explainer.
  - The components are built for a single cover, since P3 guarantees one.
  - The per-cover dicts, the event deque, `manual_list` and the button loop go away.
  - A typed event queue replaces the four boolean flags.
  - `entry.runtime_data` replaces the per-entry `hass.data`.
  - Pyright strict on `runtime/`.
- **Ledgered fixes, each with a regression test and a sim scenario:**
  - `control_method` returns to intermediate.
  - The `after_start_time` no-op.
  - The snap-position list is the same in both checks.
  - The reset button no longer blocks.
  - `ClimateCoverState` is built once.
- **Tests:**
  - Each component gets fake-driven unit tests with no `hass` fixture.
  - Run the deletion drill in the first PR and again in the last.

### P5: Layered settings, Mode, house controls (v1.18.0 shadow → v1.18.1 flip, M-L)

**v1.18.0, shadow release (minor version 1.4):**
- `lift.py` writes the house, floor and area profiles into the hub entry options, and writes sparse window `overrides`. The legacy flat keys are left alone.
- The lift **reads the live states of the per-window switches** (outside temp, lux, irradiance, climate, detection) and records them, so the dropped toggles keep their current effect.
- The runtime still acts on the legacy keys. It also resolves the new config and raises a repair issue for any key that differs.
- Soak for 7 days with no diff.

**v1.18.1, flip:**
- The runtime acts on `resolve()`.
- The Mode select becomes `auto` / `hold` / `off` and is the source of truth.
- The switches stay **hidden but enabled**, so they keep restoring for one boot, and they write through to ControlState.
- The house CONFIG entities go live. The hub select moves to Auto / Hold / Off / Mixed.
- The `hold` service and `set_profile` are added.
- The window numbers are removed, and their registry rows are cleaned up.

**Tests:**
- `resolve(w) == legacy_flat(w)` for all 15 snapshot windows.
- A property test: random options → lift → resolve gives back the same options.
- A sim scenario: a house threshold change reaches every window without a reload.
- A sim scenario: a 4 h hold on area office.
- SimHouse maps `toggle("toggle_control")` to Mode, so its call sites do not change.
- New mutations:
  - M45: area and floor precedence swapped.
  - M46: the lift drops an outlier.
  - M47: gates ignore `off`.
  - M48: `hold` ignores its duration.
  - M51: Mode restore ignores the legacy switch fallback.

**Live house:** in `automation.meeting`, replace the close and `timer.office_shades_manual_override` with `adaptive_cover.hold(area: office, 4 h, position: 0)`.

**Rollback:** v1.18.0 still acts on the legacy keys. After the flip, a downgrade reads the untouched legacy keys.

### P6: House UI and one-screen setup (v1.19.0, M)

- **Scope:**
  - The house card, the dashboard strategy and the tile Mode-chip feature.
  - The room and floor sheets, which save through `set_profile`.
  - The one-screen form with collapsed sections (`data_entry_flow.section`, flattened by the spec), used for both the add and the reconfigure steps.
  - It is written once, so a ConfigFlow step (today) and a ConfigSubentryFlow (P7) can both use it.
  - Copy-from and presets.
- **Tests:**
  - A window made from only a cover and an azimuth resolves to the house defaults.
  - A snapshot of the strategy's `generate()` output for 3 floors and 15 windows.
- **Live house:** build the new dashboard next to `dashboard-shades`.

### P7: House entry and window subentries (v2.0.0, L)

- **Scope:**
  - Add the subentry flow and HouseRuntime, with a listener that compares subentries and isolated setup for each window.
  - v2.0 still loads legacy entries. Both legacy entries and subentries produce a `WindowConfig`.
  - Consolidation is a **user-triggered repair fix flow**. See the migration section below.
- **Tests:**
  - Snapshot migration with crash injection after window *k*, and a check that a second run changes nothing.
  - Equivalence replay per window, legacy vs consolidated.
  - Setup isolation: one broken cover does not fail the house.
  - The simulation suite runs under both `model=legacy` and `model=house`.
  - New mutations:
    - M49: the listener reloads every window.
    - M50: consolidation leaves an entity or device unmoved.
- **Rollback:** before the click, downgrade. After the click, restore the backup.

### P8: Cleanup (v2.1.0, S; the point of no return)

- **Scope:**
  - Needs consolidation to be done. A repair nags until it is.
  - Remove the legacy path, the switch aliases, the `group` dual-write, and the `model=legacy` parametrization.
  - Set `single_config_entry` in the manifest.
  - Remove the hub's leftover geometry and its reference to itself in `group`.
  - Run pyright in standard mode across the rest of the code.
- **Rollback:** restore the backup and reinstall v2.0.x.

## Migration of the live house

**Identity mapping**

| Item | How it is handled |
|---|---|
| Entity unique_ids | Stay `{old_entry_id}_{suffix}` forever |
| New windows | Use `{subentry_id}_…` |
| Hub | Keeps `adaptive_cover_hub_*` and its entry_id |
| Entity_ids, restore state, history | Survive, because unique_ids are unchanged |
| Override store | Keyed by `window_key` = the old entry_id, so it needs no re-key. P4 only collapses its per-cover dict into one record |

**Consolidation fix flow (P7)**

1. **Preconditions.**
   - An HA backup is less than 24 h old. The flow asks you to confirm it.
   - No entry has more than one cover.
   - All windows are loaded.
2. **Snapshot.** Write `.storage/adaptive_cover.v1_snapshot` (entries, relevant registry rows, override store, dashboard JSON) and a JSON export to `/config`.
3. **Preview (pure).**
   - The profiles that will be moved up to the house, floors and areas.
   - The window exceptions that remain.
   - "Entity_ids preserved: N/N".
   - An assertion that `resolve(new) == resolve(old)` for every window. If it fails, the flow aborts with a report.
4. **Per legacy entry.** Progress is recorded in the house entry, so the run can resume after a crash.
   1. Unload the entry.
   2. `async_add_subentry(unique_id=cover_reg_id, data={window_key: old_entry_id, …})`.
   3. `dr.async_update_device(new_config_entry_id=, new_config_subentry_id=, area_id=)`.
   4. `er.async_update_entity(config_entry_id=, config_subentry_id=)` for each entity.
   5. Remove the old entry, only after the device and entities have moved. Removing an entry deletes whatever it still owns.
5. **House entry.**
   - Drop the hub's leftover geometry and its reference to itself.
   - Set VERSION 2. This major bump makes older code refuse the entry, so a backup is the rollback.
   - A migration error raises `ConfigEntryNotReady` or a repair issue. Recovery uses `async_retry_migration`.

**Consumers**
- **Automations and scripts:** no automation references an adaptive_cover entity, so the only change is the `automation.meeting` improvement.
- **dashboard-shades:** 15 tiles keyed by `entry_id` and 1 compass listing 15 entry_ids. They keep working because `entry_id` = window_key.
- **Hub cards:** these are mushroom cards that reference entity_ids, which are unchanged. The hub select options change to Auto / Hold / Off.

**Restore and override state**
- The Mode select restores its own state. On its first boot it falls back to the aliased switches.
- Manual overrides survive, because the store key does not change.
- The end-of-day retry state is rebuilt from the schedule.

**Dry run:** the P0 snapshot fixture runs the full migration in CI on every PR that touches `flows/` or `settings/`.

## Refactor contract

**Frozen**
- `evaluate()` and the engine models.
- The goldens, the truth table and the house replay.
- What the SimHouse scenarios assert.
- Outbound cover calls: target, value and timing.
- Manual-override semantics.
- The unique_ids and entity_ids of kept entities.
- The hub entity_ids.
- The Position attributes. New ones may be added.
- Service names and response schemas. Input fields may be added.

**Changed on purpose.** Each change is a ledger entry that names the tests it retires, their replacements, and the mutations it re-targets.

| # | Change | Phase | New pin |
|---|---|---|---|
| C1 | Entity categories, visibility, area, names | P1 | `test_entity_surfaces` rewrite |
| C2 | SunData pandas types become `SolarDay` (same values) | P2 | API pin |
| C3 | Spec drift fixes; generated schemas | P3 | `spec_parity.json`, round-trip test |
| C4 | `group` becomes `cover_entity_id` | P3 | migration tests, M44 |
| C5 | Five defect fixes | P4 | `test_regression_*` |
| C6 | Options-over-data becomes layered `resolve()` | P5 | `tests/settings/`, M39 re-anchored, M45–M46 |
| C7 | Switches and numbers become Mode and house entities; hub vocabulary | P5, P8 | `test_hub` asserts Mode, M47, M48, M51 |
| C8 | Entries become house + subentries | P7 | snapshot migration, replay, M49–M50 |

**How the net evolves**
- Tests reach the system only through WindowHandle and public APIs, so a change of backend does not touch them.
- `refactor_roadmap.json` gets a `contract_v2` block with these seams: evaluate, resolve, entity surface v2, services, SolarDay.
- The kill bar stays at 100%, and each new behavior adds a mutation.
- The deletion drill runs once per phase.

## Testability and maintainability

| Metric | Baseline (2026-09-28) | Target | Phase |
|---|---|---|---|
| CI on main | 49/49 runs red; hassfest and HACS disabled | 0 red runs; required check; PR under 6 min | P0 |
| HA minimum version | 4 conflicting sources | one (2026.8); matrix of min + latest; weekly newest-phcc job | P0 |
| Deprecation warnings | 1,025 per run | 0 (our package's warnings fail the run) | P0, P2 |
| Largest module / function | 1,937 lines / 253 lines (radon F52) | ≤400 / ≤60 lines, C901 ≤10, enforced by ruff; WindowCoordinator ≤300 | P4 |
| Pyright strict errors | 1,629 (engine: 14 basic) | 0 on engine/, settings/, runtime/; standard mode elsewhere | P2–P4, P8 |
| Functions annotated | 55% | 100%; ruff ANN; no `Any` in seam signatures | P4 |
| `now()` / `utcnow()` outside the clock | 19 | 0; `test_purity` extended to settings/ and runtime/ | P2, P4 |
| Hand-written schemas / default copies | 3 schema copies, 5 default copies | 0 outside the spec | P3 |
| Test reads of internals | 48 `hass.data` reads, 8 private attributes, 1 `object.__new__`, autouse wall-clock mock | 0; `patch()` only in one helper | P0, P4 |
| Unit tier without hass | none | every runtime/ and settings/ module; whole tier under 2 s | P4 |
| Suite time | 27 s serial / 5.9 s with -n auto | under 45 s / under 10 s including replay and legacy/house parametrization; no test over 2 s | all |
| Mutation gate | stale; serial; about 20 min; not in CI | fresh baseline each release; ≤6 min with `--jobs`; runs on PRs and nightly; a patch that no longer applies fails CI | P0 |
| Dependencies | pandas, plus numpy and pytz imported but undeclared | none undeclared; pandas, numpy and pytz removed | P2 |
| Translations | es.json invalid; 26–46 missing or stale keys per language (fixed 2026-09-28 by going English-only) | en.json in sync with strings.json, checked in CI; card English-only | P0 |
| Card | 1 failing vitest; not in CI | vitest, tsc, eslint and bundle freshness in CI; strategy and discovery snapshots | P0, P6 |
| Release | manual version bump; an unused zip | `git tag` only | P0 |
| Docs | boilerplate CONTRIBUTING.md; no ADRs | CONTRIBUTING.md covers tiers, sim scenarios, mutations, the ledger and releases; at least 5 ADRs; agents.md updated each phase | P0+ |

**Seams (typing Protocols)**

| Seam | Covers | Test double |
|---|---|---|
| `Clock` | the current time | frozen stepped clock |
| `SolarDayProvider` | solar table for a day | fixed solar tables |
| `CoverActuator` | moving covers; owns context ids and `is_own_context` | recording fake |
| `StateReader` | reading HA entity states | dict-backed fake |
| `Scheduler` | timed callbacks | manual scheduler |
| `OverrideStore` | override state | in-memory store |

**Test tiers**
- **Pure state machines:** `resolve`, `lift`, Decider, GatePolicy, ManualDetector, OverrideTracker and Schedule have the form `(state, event, now) -> (state, effects)`. They are tested with tables and properties.
- **Shell:** WindowCoordinator and HouseRuntime are tested through SimHouse.
- **Flows and platforms:** tested through WindowHandle.

## Risks and mitigations

1. **Consolidation corrupts the live house.**
   - It runs only when you start it, after a backup and a snapshot.
   - The pure preview asserts equivalence before anything is written.
   - Every step is idempotent and can resume.
   - CI rehearses it on the snapshot, including injected crashes.
2. **New defaults or the lift silently change behavior.**
   - P3 writes the current defaults into every entry first.
   - P5 runs in shadow mode with a diff repair.
   - The house replay and the per-window replay must match.
3. **Mode or override state is lost when the switches go.** The aliases stay hidden but enabled for several releases. A sim `restart()` test and M51 cover this.
4. **Editing one window restarts all 15.** The listener compares subentries (M49). House changes re-resolve in place.
5. **One entry becomes one failure domain.** Setup is isolated per window, and a failing window gets its own repair issue.
6. **The card breaks when `config_entry_id` changes.** P1 decouples discovery from it, and the entry_id stays valid as window_key.
7. **The split drifts.** The split uses move-only PRs, mutations re-anchored in the same PR, and the deletion drill.
8. **Churn in the 2026.8+ device registry API.** Use only `via_device_id`, `config_subentry_id` and `async_get_device_by_identifier(config_entry_id=)`.

## Decisions (answered by the owner, 2026-09-28)

1. **Window Mode = Auto / Hold / Off**, with climate at house or area level plus a one-time per-window "ignore climate". **Yes.**
2. **Manual override duration:** **2 hours is the house default for every window**, and a room (area) may override it. Already applied to the live house on 2026-09-28 (all 15 windows set to 2:00) and to the built-in default in `const.py`.
3. **Consolidate into one house entry (P7–P8).** **Yes.**
4. **Dashboard:** run the generated dashboard next to `dashboard-shades` for 2 weeks, then retire the old one and keep its JSON. **Yes.**
5. **Names:** **clean up and make consistent, and remove leftovers where needed.** This moves from optional-in-P8 to **P1** (see "Naming cleanup" below), because entity_ids survive consolidation (unique_ids never change), so renaming once in P1 does not have to be redone later.
6. **Grouping by HA areas and floors**, not custom zones. **Yes.**

### Naming cleanup (decision 5, delivered in P1)

- **Scheme:** `<domain>.<area>_<window>_<role>`, all lowercase, from the HA area and a short window name, for example `sensor.office_door_position`, `select.office_door_mode`, `button.office_door_return_to_auto`. The house device uses `<domain>.shades_<role>`.
- **Scope:** every adaptive_cover entity and device name, and the physical cover entities (`cover.ne_door_shades`, `cover.sw_sw_shade`, `cover.sw_sw_1st_floor_bed`, …) renamed to the same scheme (`cover.office_door_shade`, …).
- **Leftovers removed:** the 3 disabled "SE" multi-cover entries (P0), orphaned registry rows, and entities that the new surface drops (P1/P5).
- **Safety:**
  - A **dry run** first lists every old → new entity_id and every reference to it: automations, scripts, scenes, dashboards, groups, and the HomeKit bridge's entity filters. HA does not rewrite these references automatically.
  - The owner approves the list before anything is applied.
  - The rename updates every listed reference in the same step, and a backup is taken first.
  - Physical covers belong to other integrations (Zigbee/HomeKit bridge), so their renames are part of the same approved list and are applied with HA's entity registry, not by this integration's code.

## Appendix: how the three designs scored

Scores are out of 5.

| | Goal fit | Migration safety | Test safety | Testability / maintainability gains | Feasibility | HA correctness |
|---|---|---|---|---|---|---|
| Plan 1 (house-model) | 5 | 4 | 4 | 4 | 3 | 4 |
| Plan 2 (UI-first) | 5 | 4 | 4 | 3 | 3 | 4 |
| Plan 3 (risk-first) | 3 | 5 | 5 | 4 | 3 | 4 |

- **Plan 1** has the best end state: pure resolve, a split runtime, crash-injection migration tests. It relied on a CI that is red today, re-keyed override state that did not need re-keying, disabled the switches (which would lose their restore state), and packed an XL v2.0.
- **Plan 2** has the best test retargeting (WindowHandle, equivalence replay) and the best UI description. It added services and categories to the 1,937-line coordinator before the split, and it added a custom `set_mode` that `select.select_option` already covers.
- **Plan 3** has the best gates: ledger, `behavior_tier_ids`, house replay, shadow mode, move-only split, clock seam. It left subentries optional, kept dual models for about 10 releases, and assumed a `--check` flag that does not exist yet.
- **Fixed in all three:** red CI, release automation, translations and docs. None of the plans addressed them. This plan adds them in P0.
