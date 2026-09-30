# Contract ledger

This file records every intentional change to the Refactor Contract
(`docs/refactor_plan.md`, "Refactor contract"). A behavior-tier test may
only disappear, be renamed or be re-parametrized in the same PR as an entry
here. `tests/contract/check_behavior_tier.py` fails CI when an id leaves
`behavior_tier_ids.txt` without being named in an entry.

## Rules

- One entry per intentional change. Append entries at the end of
  "Entries". Never edit or delete an old entry; correct it with a new one.
- Entry ids are `L` plus four digits, in order: `L0001`, `L0002`, ...
- Write each node id exactly as `pytest --collect-only -q` prints it, in
  backticks. `*` is the only wildcard (for example
  `tests/test_hub.py::TestLegacy::*`). Brackets in parametrized ids are
  literal.
- "Removed" and the left side of "Renamed" are the retired ids. The checker
  accepts a removal only if one of these names it.
- "Replacements" names the tests that now pin the retired behavior.
- "Mutations re-targeted" names each mutation (M##) that the change
  re-anchors, re-targets or adds, and where it now lives. Write "none" if
  there are none.
- "Contract change" is the row in the plan's table (C1 to C8), or "none".
  An entry that retires no tests is allowed only when it names a contract
  change (it records a deliberate change that only adds or re-anchors pins).
- "Reason" is required.

After you add the entry, run
`python tests/contract/check_behavior_tier.py --update` and commit the
ledger, `behavior_tier_ids.txt` and the test changes together.

## Entry format

The example below is inside an HTML comment. The checker ignores it.

<!--
## L0001 · 2026-10-14 · Entity categories and names (C1)
- **Removed:**
  - `tests/test_entity_surfaces.py::test_position_sensor_has_no_category`
  - `tests/test_entity_surfaces.py::TestLegacyNames::*`
- **Renamed:**
  - `tests/test_hub.py::test_old_name` -> `tests/test_hub.py::test_new_name`
- **Replacements:**
  - `tests/test_entity_surfaces.py::test_diagnostic_categories`
- **Mutations re-targeted:** M40 re-anchored in sensor.py `PositionSensor.native_value`
- **Contract change:** C1
- **Reason:** P1 gives entities categories and new names; the old tests
  asserted the pre-P1 surface.
-->

## Entries

## L0001 · 2026-09-28 · bbca2e9 regression moved to the entity boundary (P0)
- **Renamed:**
  - `tests/characterization/test_service_calls.py::test_regression_bbca2e9_predict_position_timezone` -> `tests/characterization/test_service_calls.py::test_regression_bbca2e9_predicted_entry_position`
- **Replacements:**
  - `tests/characterization/test_service_calls.py::test_regression_bbca2e9_predicted_entry_position`
- **Mutations re-targeted:** none
- **Contract change:** none
- **Reason:** the old test built a coordinator with `object.__new__` and called
  the private `_predict_position_at_time`. The replacement asserts the same
  regression (a tz-aware sun table indexed from a UTC target returns the
  calculated, not default, position) through the Next State Change sensor's
  `expected_position`. It fails on the default-fallback and UTC-as-local
  mutations. The helper's UTC-input branch is unreachable from any public path.

## L0002 · 2026-09-28 · P1 entity surface: categories, names, device areas, Position attributes (C1)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins in `tests/test_entity_surface_v2.py::*`
- **Mutations re-targeted:** M40–M42 re-anchored (offsets only). Added M52
  (a card sensor must not be disabled by default), M54 (area copy must not
  overwrite a user-set area), M55 (override_until requires a duration).
  M53 (migration must not disable user-touched rows) retired until P6
  reintroduces a disabled-by-default role.
- **Contract change:** C1
- **Reason:** P1 gives entities categories (primary / diagnostic / config),
  translation-key names ("<Device> <Role>", e.g. "Office door Position"),
  copies each physical cover's area to its window device, and adds
  `window_key`, `cover_entity`, `cover_type`, `override_until` and
  `next_move` to the Position sensor. Entity ids and unique ids are unchanged;
  goldens, truth table and house replay are unchanged. One assertion changed:
  `test_regression_resume_button_rename_keeps_unique_id` now expects
  "Rename Return to auto". The schedule sensors stay enabled because the card
  still reads them.

## L0003 · 2026-09-29 · Replay-found defect fixes change the pinned timelines (C5)
- **Removed:** none
- **Replacements:** new `test_regression_*` tests for each fix
- **Mutations re-targeted:** none
- **Contract change:** C5
- **Reason:** four defects found by the house replay are fixed, and the replay
  and golden-day timelines change only where those defects showed:
  (1) climate threshold numbers use HA's temperature unit (display only);
  (2) Next State Change picks tomorrow by the local date, not UTC;
  (3) an intermediate opening/closing report no longer counts as arrival, so
  small snap moves are not re-sent (duplicate `cmd` lines removed; a follow-up
  target can go out on the next update instead of at the landing sub-step);
  (4) when the sun leaves the window within 30 minutes of the sunset position,
  the sunset position starts right away instead of opening to the default and
  closing minutes later (dusk open-then-close lines removed).
  35 of 90 replay goldens changed (+14 / -66 lines), all in these categories.


## L0004 · 2026-09-29 · SunData without pandas: SolarDay, same values (C2, P2)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none. `tests/test_regression_fixes.py::test_regression_sun_data_public_api_intact`
  keeps its id and now pins the C2 types: `times` is a tuple of tz-aware
  datetimes (was a pandas `DatetimeIndex`); `solar_azimuth` and
  `solar_elevation` stay lists. New pins:
  - `tests/test_regression_fixes.py::test_sun_data_day_points_follow_real_time[normal_day]`
  - `tests/test_regression_fixes.py::test_sun_data_day_points_follow_real_time[dst_start]`
  - `tests/test_regression_fixes.py::test_sun_data_day_points_follow_real_time[dst_end]`
  - `tests/test_regression_fixes.py::test_sun_data_values_are_astral_at_each_point`
  - `tests/test_regression_fixes.py::test_sun_data_solar_day_is_the_snapshot`
- **Mutations re-targeted:** M36 and M37 re-anchored from `np.interp` onto
  `engine.numeric.interp` in coordinator.py `interpolate_states` (descriptions
  unchanged, a `deviation` note added). M30 and M31 re-anchored onto the
  narrowed lines in engine/evaluate.py (`evaluate`, `_apply_limits`) for
  pyright strict. No new mutations.
- **Contract change:** C2
- **Reason:** P2 removes pandas, numpy and pytz (ADR 0005). SunData builds
  its day with a UTC stepper (289 points, 277 on the day DST starts, 301 on
  the day it ends) and exposes it as `SunData.solar_day() -> SolarDay`;
  `times`, `solar_azimuth`, `solar_elevation`, `sunrise()`, `sunset()` and
  `location` keep their names and values. Nearest-point lookups use `bisect`
  in UTC with pandas' tie rule. The goldens, the truth table and all 90
  house-replay goldens are byte-identical; no pinned output changed.

## L0005 · 2026-09-29 · One option spec generates every settings surface (C3)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins in `tests/contract/test_spec_parity.py::*`
  (every surface, against `tests/contract/spec_parity.json`) and
  `tests/settings/test_spec.py::*` (the plan's one-time/recurring table,
  the remaining drift list, form-to-service round trip)
- **Mutations re-targeted:** none (M39's anchor in
  `__init__.handle_change_settings` did not move)
- **Contract change:** C3
- **Reason:** P3 replaces the hand-written wizard, options, service and
  number schemas with one table (`settings/spec.py`, built by
  `settings/schema.py`). `spec_parity.json` is byte-identical before and
  after: every key keeps its kind, default, range, unit and placement.
  Drift between surfaces that existed before is now listed per row
  (`legacy`) and pinned by `test_legacy_drift_is_exactly_the_listed_entries`;
  the drift fixes that follow each remove entries with their own ledger
  entry. `options_spec.py` is removed; the options flow's nine unreachable
  per-page steps went in the commit before (a static step-graph walk from
  `init` reaches none of them). Cross-field errors now use translation keys
  (`config.error.*`, `options.error.*`) instead of English sentences as
  keys; the fields they mark are unchanged. Five
  `tests/test_units_and_defaults.py` default tests now read the wizard's
  forms through a real flow instead of module-level schema constants (same
  ids, same assertions). Goldens, truth table and house replay unchanged.

## L0006 · 2026-09-29 · Window height and distance take up to 10 m everywhere (C3)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pin
  `tests/test_config_flow.py::test_regression_height_distance_max_ten`
- **Mutations re-targeted:** none
- **Contract change:** C3
- **Reason:** drift fix. The change_settings and add_entry services took
  `window_height` and `distance_shaded_area` from 0.1 to 10 m, but the
  wizard and the options form capped the height at 6 m and the distance at
  2 m, so a value set by the service could not be saved from the options
  form again. `spec_parity.json` changes in four lines: the form `max` of
  both keys (wizard vertical/horizontal, options covers_geometry) is now 10.
  Stored values are untouched (the range only widens). Goldens, truth table
  and house replay unchanged.

## L0007 · 2026-09-29 · delta_time accepts 0 on every surface (C3)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pin
  `tests/test_config_flow.py::test_regression_delta_time_min_zero`
- **Mutations re-targeted:** none
- **Contract change:** C3
- **Reason:** drift fix. The services accepted `delta_time` >= 0 (many
  entries and tests run with 0, no time throttle), but the wizard and the
  options form required at least 2 minutes, so such an entry could not be
  saved from the options form without raising its throttle.
  `spec_parity.json` changes in two lines: the form `min` (wizard
  automation, options automation_timing) is now 0. This is the wider range,
  so no stored value becomes invalid; the default stays 2. Goldens, truth
  table and house replay unchanged.

## L0008 · 2026-09-29 · Climate thresholds are unit-aware on every surface (C3)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/test_units_and_defaults.py::test_regression_thresholds_unit_aware_everywhere[celsius]`
  and `[fahrenheit]`
- **Mutations re-targeted:** M39 patch regenerated: its anchor in
  `__init__.handle_change_settings` moved down three lines (text and
  description unchanged). Added M56 (change_settings validates the
  thresholds in °C whatever HA's unit), killed by the new regression test.
- **Contract change:** C3
- **Reason:** drift fix. `temp_low` / `temp_high` are stored and compared in
  HA's temperature unit (v1.13.5), and their number entities follow it
  (v1.15.1, L0003), but the wizard and the options form still showed a
  unit-less 0-86 / 0-90 slider in whole degrees, change_settings and
  add_entry accepted any number (a °F house could store 21 and sit in
  permanent winter), and the °C numbers showed 21 / 25 while unset instead
  of the spec defaults 22 / 24. Now every surface uses the unit's shape:
  °C 5-30 / 10-40, °F 40-90 / 50-100, step 0.5, a box, the unit shown; the
  services reject a value outside that range (their schema is built with
  HA's unit when they register). services.yaml can't follow the unit: its
  selectors take the union (5-90 / 10-100) and the text names HA's unit
  instead of "the sensor's unit" (which was wrong since v1.13.5).
  `spec_parity.json` changes only in `temp_low` / `temp_high`; the °F
  numbers are unchanged, so a °F house (this one) sees the same numbers.
  One behavior-tier test body changed without changing its id or
  assertions: `tests/test_change_settings.py::test_regression_change_settings_enables_climate_mode`
  now runs in a °F house, because its 70 / 74 thresholds are °F values
  that a °C house now rejects. A stored threshold outside the unit's range
  (only possible with a wrong-unit value) now shows as invalid in the
  options form until corrected. Goldens, truth table and house replay
  unchanged.

## L0009 · 2026-09-29 · The options form runs the wizard's cross-field checks (C3)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/test_one_page_options.py::test_regression_options_form_runs_every_cross_field_check[interp_lists_differ]`
  and `[blind_spot_reversed]`
- **Mutations re-targeted:** none
- **Contract change:** C3
- **Reason:** defect fix found while merging the elevation checks into one
  validator. The one-page options form checked only the elevation order,
  so it saved interpolation lists of different lengths (np.interp then
  raises on every update and the window stops moving) and a blind spot
  whose right edge is left of its left edge; the wizard always rejected
  both. The options form now runs every rule in `settings/validate.py` on
  the options as they would be saved, and shows the error at form level.
  `spec_parity.json`, goldens, truth table and house replay unchanged.

## L0010 · 2026-09-29 · Layered settings resolver and legacy lift, pure core (C6, P5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/settings/test_resolve.py::*` (ADR 0003 precedence, provenance,
  forbidden levels), `tests/settings/test_lift.py::*` (the lift's rules,
  tie-breaks, and two seeded property tests: any options -> lift ->
  resolve round-trips exactly; options the allowed levels can express
  lift without legacy values) and `tests/settings/test_house_lift.py::*`
  (`resolve(w) == legacy_flat(w)` for all 15 snapshot windows, plus the
  lifted house, floor, area, window and legacy values).
- **Mutations re-targeted:** added M45 (area and floor precedence swapped
  in `settings/resolve.py`) and M46 (the lift drops a window's outlier in
  `settings/lift.py`), both killed by the new pins. M39 is not re-anchored
  yet: the runtime still merges the legacy options.
- **Contract change:** C6 (first half: the pure resolver and lift; no
  runtime code reads them yet)
- **Reason:** P5 needs the layered model and the migration into it before
  the shadow release can compare them with the legacy options. Nothing in
  the runtime changed, so goldens, truth table and house replay are
  unchanged. The real house cannot be expressed exactly with the levels
  the spec allows (Master trap's sunrise and sunset offsets differ from
  the rest of its room, and five windows store `None` for three
  house-only thresholds), so the lift keeps those values as explicit
  window `legacy` values with provenance `legacy`, instead of breaking
  the round trip or the spec's `overridable_at`.

## L0011 · 2026-09-29 · An unreadable time entity no longer stops the window (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/simulation/test_regressions.py::test_regression_unreadable_start_entity_uses_fixed_start[unavailable]`,
  `[not a time]`,
  `tests/simulation/test_regressions.py::test_regression_unreadable_start_entity_alone_waits`
  and the unit pins in `tests/runtime/test_schedule.py`
  (`test_regression_unreadable_start_entity_falls_back[*]`,
  `test_regression_unreadable_start_entity_alone_is_not_started[*]`,
  `test_unparseable_end_entity_means_no_end`)
- **Mutations re-targeted:** M05 re-anchored onto the restructured
  `Schedule.after_start` (same swap, description unchanged). Added M60 (an
  unreadable start entity with no fixed start counts as started).
- **Contract change:** C5
- **Reason:** defect fix (P4 batch 3). With a start-time entity configured,
  `Schedule.after_start` compared "now" with None when the entity was
  unavailable, and the date parser raised when its state was not a time.
  Either way every refresh failed and the window went unavailable. An
  unreadable start entity now falls back to the fixed start time, and with
  no fixed start the window has not started yet (it starts once the entity
  reads a time again). The end-time entity uses the same reader, so a state
  that is not a time now means "no end time", as an unavailable one already
  did. Goldens, truth table and house replay unchanged: no pinned config
  uses a start or end entity.

## L0012 · 2026-09-29 · An end-time entity at 00:00 means the coming midnight (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/simulation/test_regressions.py::test_regression_midnight_end_entity_means_coming_midnight`
  and the unit pins in `tests/runtime/test_schedule.py`
  (`test_regression_midnight_end_entity_means_the_coming_midnight`,
  `test_a_dated_end_entity_keeps_its_date`)
- **Mutations re-targeted:** M06 re-anchored onto the shared normalization in
  `Schedule.end_time` (description unchanged; it now drops the
  normalization for both sources). Added M61 (an end-time entity at 00:00
  is not normalized).
- **Contract change:** C5
- **Reason:** defect fix (P4 batch 3). Only the fixed `end_time` option
  treated 00:00 as the coming midnight. An end-time entity at 00:00 read as
  the midnight that started today: the window was shut all day, and
  EndOfDay armed that past time, so the end close fired as a catch-up close
  at startup. Both sources now normalize an end of 00:00 today to the
  coming midnight, so EndOfDay arms the next midnight. An entity whose
  state names another date keeps it. Goldens, truth table and house replay
  unchanged: the house uses the fixed `end_time` 00:00, which behaves as
  before.

## L0013 · 2026-09-29 · The fixed start time feeds the start-after-end check (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/simulation/test_regressions.py::test_regression_fixed_start_after_end_is_reported`
  and `tests/runtime/test_schedule.py::test_regression_fixed_start_is_recorded`
- **Mutations re-targeted:** M05 re-anchored (its fixed-start block now
  records the start; description unchanged). Added M62 (the fixed start is
  not recorded).
- **Contract change:** C5
- **Reason:** defect fix listed in the plan's P4 ("the `after_start_time`
  no-op"). The fixed-start path read the start time but its "record it"
  line was a bare expression, so `Schedule.last_start` only ever held an
  entity start and the "Start time is after end time" error never fired for
  a fixed start. The fixed path now records the start like the entity path.
  This changes only that error log; which moves go out is unchanged, and
  goldens, truth table and house replay are unchanged (the house's fixed
  06:00 start is before its end).

## L0014 · 2026-09-29 · The delta gate uses the same snap positions as the other gates (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/simulation/test_regressions.py::test_regression_small_move_to_privacy_passes_delta_gate`
  and `tests/runtime/test_gates.py::test_regression_privacy_position_passes_the_delta_gate`
- **Mutations re-targeted:** none re-anchored (M01's line is unchanged).
  Added M63 (the delta gate's snap list leaves out the privacy position).
- **Contract change:** C5
- **Reason:** defect fix listed in the plan's P4 ("the snap-position list is
  the same in both checks"). The time throttle, quiet hours and move budget
  let every snap position through (sunset, default, privacy, 0, 100), but
  the position-delta gate kept its own list without the privacy position.
  A privacy position closer than `delta_position` to the evening position
  was therefore never sent. `GatePolicy.position_delta_ok` now asks
  `is_snap_position`. Goldens, truth table and house replay unchanged: the
  privacy golden days and the house use privacy position 0, which was
  already a snap position.

## L0015 · 2026-09-29 · The Control method sensor returns to intermediate (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pin
  `tests/simulation/test_regressions.py::test_regression_control_method_returns_to_intermediate`
- **Mutations re-targeted:** none. Added M64 (control_method keeps the last
  season when neither winter nor summer applies).
- **Contract change:** C5
- **Reason:** defect fix listed in the plan's P4 ("`control_method` returns
  to intermediate"). Confirmed first: in a climate entry the coordinator
  only ever set "winter" or "summer", so once the temperature went back
  between the thresholds, or the climate switch went off, the Control
  method sensor kept the old season (the new scenario failed with
  'winter' where 'intermediate' was due). It now reads "intermediate"
  whenever neither season applies or the climate switch is off; winter
  still wins if both held. Positions are unchanged (the climate strategy
  never read this value), so goldens, truth table and house replay are
  unchanged.

## L0016 · 2026-09-29 · Return to auto no longer waits for the covers to land (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pin
  `tests/simulation/test_regressions.py::test_regression_reset_button_returns_at_once`.
  One behavior-tier test body changed without changing its id:
  `tests/simulation/test_harness_smoke.py::test_press_reset_button_resumes_auto`
  now lets the shade travel (advances to 11:20) before it checks the landed
  position, because the press no longer waits for the landing. Its
  assertions are unchanged.
- **Mutations re-targeted:** none, and none added: the defect was a wait
  loop, and a mutation that re-adds it would hang the entity tier until the
  runner's 30-minute timeout.
- **Contract change:** C5
- **Reason:** defect fix listed in the plan's P4 ("the reset button no
  longer blocks"). Confirmed first: `AdaptiveCoverButton.async_press`
  commanded each overridden cover, then polled every second until it
  reported landing or 120 s passed, before resetting the override and
  moving on to the next cover. One press held its service call for up to
  two minutes per overridden cover (the new two-cover scenario saw sim time
  advance during the press). The button now sends each command and clears
  the override at once. The travel stays ours through the coordinator's
  travel window, so the landing is never read as a manual move (the new
  scenario checks both covers after they land). Goldens, truth table and
  house replay unchanged: none of them presses the button.

## L0017 · 2026-09-29 · ShadeConfig feeds the cover adapters (C3)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins `tests/test_cover_adapters.py::*`
  (implementation tier: the adapter factory) and
  `tests/runtime/test_option_reads.py::*` (one fallback per option)
- **Mutations re-targeted:** M27 (sunrise-offset fallback) moved from
  `coordinator.common_data` to `runtime/shade_config._sunrise_offset`;
  M28 (privacy-offset None check) moved from
  `coordinator._apply_extended_config` to
  `runtime/shade_config.CoverGeometry.from_options`. Descriptions
  unchanged. The other coordinator and calculation patches were
  regenerated for line offsets only.
- **Contract change:** C3
- **Reason:** P3 replaces the positional adapter constructors (three
  order-coupled lists of 18, 2-3 values each in the coordinator) with
  `AdaptiveGeneralCover.from_config` / `calculation.build_cover` and
  `ClimateCoverData.from_config`, fed by `ShadeConfig.geometry` and
  `ShadeConfig.climate`. The adapters' fields are keyword-only. Every
  option read now has one fallback (`runtime/shade_config.ABSENT`), which
  config migration 1.3 writes into entries. No output changes: goldens,
  truth table and house replay are byte-identical.

## L0018 · 2026-09-29 · One cover per window on every settings surface (C4)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins `tests/test_one_cover_per_window.py::*`
  (wizard, options form and add_entry refuse a second or duplicate cover,
  write both cover keys, key a new entry by its cover's registry id)
- **Mutations re-targeted:** added M59 in `window_cover.cover_problem` (a
  duplicate/second cover is accepted), killed by the new pins. The plan
  and ADR 0002 call this mutation M44; M44-M51 are reserved there for
  P5-P7 and M58 was taken, so it is M59.
- **Contract change:** C4
- **Reason:** ADR 0002. The cover selector on the wizard's cover-type page
  and the options form's first section is now `cover_entity_id` with
  `multiple: false` (it was `group`, a multi-select). Every writer stores
  the cover as `cover_entity_id` and as `group: [cover]` (older versions
  read `group`; the runtime still reads `group` until P8, so a downgrade
  that edits it is never out of sync). `add_entry` takes `cover`; `covers`
  is still accepted with exactly one item, and more than one, none, both
  forms, or a cover another enabled window drives is a
  `ServiceValidationError` naming the problem. The wizard and the options
  form show `cover_in_use` for such a cover; a registered cover's second
  entry aborts `already_configured` (entry unique_id = the cover's
  entity-registry id). `spec_parity.json` changes only in the cover
  fields: `group` becomes `cover_entity_id` in the wizard's type pages
  and the options form (`multiple: false`, no `[]` default), `add_entry`
  gains `cover`, and `covers` is no longer required (schema and
  services.yaml). The spec's `group` row is no longer on any form (kind
  internal, still one-time window identity, default `[]`). Behavior-tier
  test bodies changed without changing ids: `tests/test_config_flow.py`
  step inputs pick a cover with `cover_entity_id` instead of `group: []`;
  `tests/test_translations.py::test_flow_strings_cover_every_form` also
  requires the new error and abort strings. Goldens, truth table and
  house replay unchanged.

## L0019 · 2026-09-29 · Config entry migration 1.3: fallbacks written, one cover, split repair (C4)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins `tests/test_migration_1_3.py::*` (the
  15 live windows: no runtime read changes, exactly which keys are
  written, cover and unique_id; multi-cover entries keep working with a
  fixable split issue; the split fix; two windows on one cover)
- **Mutations re-targeted:** none
- **Contract change:** C4
- **Reason:** plan P3 / ADR 0002. `CONFIG_ENTRY_MINOR_VERSION` is 3.
  Migration 1.3 (`migration.py`) writes every option a window reads
  through a code fallback (`runtime/shade_config.ABSENT`) into its
  options before any default changes, writes `cover_entity_id` next to
  `group: [cover]`, and sets the entry unique_id to the cover's registry
  id when the cover is registered and no other entry holds it. The hub
  only gets the version bump. On the live snapshot it writes 116 keys
  (every one None, plus the cover) and changes none; `ShadeConfig` is
  identical before and after for all 15 windows. Setup now keeps the
  unique_id on the cover (the options form can change the cover) and
  raises a fixable `split_window` repair issue for an entry with several
  covers (`repairs.py` splits it: the entry keeps the first free cover,
  each other free cover gets a copy of the settings as a new window named
  after the cover, covers another window drives are dropped). The house
  replay starts its entries at 1.1, so every golden now runs the migrated
  options; `tests/replay/house_replay.py` asserts the entry reached 1.3.
  Goldens, truth table and house replay unchanged. Behavior-tier test
  bodies changed without changing ids: in `tests/test_entity_surface_v2.py`,
  `TestMigration::test_migration_applies_surface_to_legacy_rows`,
  `TestMigration::test_migration_is_idempotent` and
  `test_live_house_upgrade` expect 1.3 instead of 1.2, and
  `TestMigration::test_newer_minor_version_loads_unchanged` uses 1.4 as
  the newer version (1.3 is now current);
  `tests/test_one_page_options.py::test_regression_options_form_runs_every_cross_field_check`
  takes its "before" options after setup (the migration adds keys).

## L0020 · 2026-09-29 · SimHouse covers=[a, b] creates two windows (C4)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pin
  `tests/simulation/test_harness_smoke.py::test_two_covers_make_two_windows`
- **Mutations re-targeted:** none
- **Contract change:** C4
- **Reason:** plan P3 and ADR 0002 ("SimHouse `covers=[a, b]` creates two
  windows"). A window drives one cover, so the harness builds one config
  entry per cover ("Sim House", "Sim House 2", ...), sharing `options`
  and `cover_type`. `house.entry` is the first window's entry; `eid`,
  `entity`, `sensor_value`, `sensor_attr`, `toggle`, `press` and
  `select_option` take `cover=` to pick a window (default: the first);
  `restart` and `set_options` act on every window. The four multi-cover
  scenarios now run as two windows with the same assertions:
  `tests/simulation/test_regressions.py::test_regression_group_remote_latches_both_covers`,
  `tests/simulation/test_device_failures.py::test_service_raise_non_fatal`
  and `tests/simulation/test_harness_smoke.py::test_fail_next_command_raises_once_loop_survives`
  pass unchanged; the body of
  `tests/simulation/test_gates_and_windows.py::test_control_on_force_apply`
  now restarts both windows with control off and switches both back on,
  and `tests/simulation/test_regressions.py::test_regression_reset_button_returns_at_once`
  (L0016) presses each window's Return to auto button (same ids and
  assertions). A multi-cover entry from before P3 is no
  longer a SimHouse shape; it is pinned at the entity-surface tier
  (`tests/test_migration_1_3.py`, and
  `tests/test_entity_surface_v2.py::TestPositionAttributes::test_multi_cover_entry_lists_every_cover`).
  Goldens, truth table and house replay unchanged (the replay drives one
  cover per window).

## L0021 · 2026-09-29 · One-screen window form replaces the setup wizard (C3, P6)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins `tests/test_window_setup_form.py::*`
  (one screen, recurring settings only in the collapsed exceptions
  sections; a window from only a cover and an azimuth is valid and
  resolves to the house defaults; the name defaults to the cover's;
  a cover type switch keeps what was entered; a cover that cannot move
  the way the type needs is refused; "Copy from" pre-fills everything but
  the name and cover; presets fill geometry only; Reconfigure shows and
  changes the one-time settings only, refuses a cover in use and aborts
  on the house entry). Implementation tier: `tests/settings/test_setup_form.py`.
- **Mutations re-targeted:** added M80 (`settings/schema.py`
  `copy_from_values`: "Copy from" copies the cover), M81
  (`settings/schema.py` `setup_section`: recurring settings land in the
  one-time sections), M82 (`settings/schema.py` `_setup_marker`: no field
  gets its spec default), M83 (`config_flow.py` `WindowForm.submit`: a
  cover type switch saves instead of showing that type's geometry). No
  earlier mutation targets these files.
- **Contract change:** C3 (the setup surface, generated from the spec;
  plan P6 "one-screen setup")
- **Reason:** plan P6 and the owner's UI principle (one-time settings in a
  window submenu, used once; everything recurring at a higher level). The
  nine-step wizard (user -> vertical/horizontal/tilt -> interp ->
  blind_spot -> automation -> climate -> weather -> update) is one form,
  `config.step.user`, built by `settings/schema.py`
  (`setup_section_fields`) from the spec: an expanded Window section
  (Copy from, preset, name, cover, cover type, azimuth, field of view,
  the type's geometry incl. overhang), then collapsed `sun_limits`,
  `advanced` and three "Exceptions for this window" sections that hold
  every recurring setting at its spec default. The same form without the
  exceptions is the new `config.step.reconfigure` (cover, type, geometry;
  recurring options untouched; the options form stays the everyday
  editor). Picking another cover type, a preset or a window to copy shows
  the form again, filled in. `spec_parity.json`: the `wizard.*` places
  become `setup.user[.<section>]` and `setup.reconfigure[.<section>]`;
  every option keeps its kind, default, min, max, step, unit and
  required flag from the wizard, except that the cover is required and
  offers covers of either type (`supported_features` [4, 128]; checked on
  submit, error `cover_type_unsupported`), `name` is optional (the cover's
  name), and `temp_entity` is optional (the climate section is optional;
  the runtime already runs climate mode without it, and the options form
  never required it). The first page's type picker `mode` becomes
  `sensor_type`; `copy_from` and `preset` are new. The options form, the
  services, services.yaml and the number entities are unchanged in the
  snapshot. A new window now stores the spec default for settings whose
  wizard page used to be skipped (blind spot edges, climate thresholds,
  sunny states; before: None); each is read only when its feature is on,
  so a new window behaves the same. Errors show above the form (`base`),
  as on the options form: HA shows no error on a field inside a section.
  Behavior-tier test bodies changed without changing ids (same intent,
  new form): `tests/test_config_flow.py::*`,
  `tests/test_one_cover_per_window.py::test_wizard_*` (the cover error is
  now `{"base": "cover_in_use"}`),
  `tests/test_units_and_defaults.py` (the defaults are read from the
  exceptions sections), and
  `tests/test_translations.py::test_flow_strings_cover_every_form` (walks
  add and reconfigure per type; needs the new error and abort strings;
  the wizard's step strings are gone). Goldens, truth table and house
  replay unchanged.

## L0022 · 2026-09-29 · Shadow release: migration 1.4 lifts the house, diff repair, provenance (C6, C7)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins `tests/test_shadow_settings.py::*`
  (migration 1.4 on the live snapshot: the stored house, floor and area
  profiles and each window's overrides and legacy values, the recorded
  switch states, zero `settings_differ` issues, the Position sensor's
  `provenance`, idempotence, a window added after the lift, a hub created
  at 1.4 is not lifted, the lift does not reload a running window) and
  `tests/simulation/test_shadow_settings.py::*` (a legacy option changed
  through the options form still drives the window and raises one
  `settings_differ` issue listing the key; a dropped switch flipped after
  the lift raises it too; both clear when the values agree again).
  Implementation tier: `tests/settings/test_shadow.py::*`.
- **Mutations re-targeted:** added M70 (`settings/shadow.py`
  `differing_keys`: the comparison ignores a differing recurring key;
  killed by the simulation and entity tiers) and M71 (`shadow.py`
  `_switch_state`: the lift records a switch's initial state instead of
  its restored one; killed by the entity tier). M44 and M47-M51 stay
  reserved by the plan.
- **Contract change:** C6 (second half: the lift is stored and compared
  at runtime; the runtime still acts on the legacy keys) and C7 (first
  step: the states of the switches P5 drops are recorded as layered
  settings; the switches still drive the runtime)
- **Reason:** plan P5, v1.18.0 shadow release (ADR 0003).
  `CONFIG_ENTRY_MINOR_VERSION` is 4. Migration 1.4 (`shadow.py`) lifts
  every enabled window into the hub entry's options (`house`, `floors`,
  `areas`, `temperature_unit`) and writes each window's sparse
  `overrides` (`{window_key, values, legacy}`); the legacy flat keys are
  untouched and windows only get the version bump. The lift reads the
  windows' options as migration 1.3 stores them, their placement (window
  device area, else the cover's area) and the states of the dropped
  switches (Climate Mode, Outside Temperature, Lux, Irradiance, Manual
  Override) as five new house-level settings (`climate_on`,
  `use_outside_temp`, `use_lux`, `use_irradiance`, `manual_detection`;
  `settings/shadow.py` `TOGGLE_OPTS`, outside `OPTS`, so no form, service
  or `spec_parity.json` changes). Switch states come from the restore
  cache when the switches are not up (HA loads it before any integration
  sets up; a switch restores from exactly that record). Every window
  setup, options-only-`overrides` update and dropped-switch change
  resolves the window and raises one non-fixable `settings_differ`
  repair issue listing the differing keys, deleted when they agree. An
  update that only writes `overrides` no longer reloads the window. The
  Position sensor gains `provenance`: the options whose value comes from
  an area, a floor, a window override or a legacy value, mapped to that
  source (house, default and one-time values are left out); None until
  the house is lifted. On the live snapshot the lift finds the expected
  profiles plus one wrinkle of migration 1.3: 13 windows store `None`
  privacy offset/position (the runtime's fallback), so the house takes
  `None` and Master south / Family south keep 30 / 0 as legacy values.
  Behavior-tier test bodies changed without changing ids (1.4 is now
  current): in `tests/test_entity_surface_v2.py`,
  `TestMigration::test_migration_applies_surface_to_legacy_rows`,
  `TestMigration::test_migration_is_idempotent` and
  `test_live_house_upgrade` expect 1.4, and
  `TestMigration::test_newer_minor_version_loads_unchanged` uses 1.5 as
  the newer version; in `tests/test_migration_1_3.py`,
  `test_live_house_migrates_to_1_3` expects 1.4, compares the window
  options without `overrides` and the hub's leftover options key by key
  (1.4 adds the lifted layers), and
  `test_multi_cover_entry_keeps_working_with_a_split_issue` expects 1.4.
  Goldens, truth table and house replay unchanged (the replay's hub is
  created at 1.4, so it is not lifted; nothing the runtime reads changed).

## L0023 · 2026-09-29 · The cover adapters read the coordinator's clock (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pin
  `tests/test_clock_seam.py::test_regression_adapters_use_the_coordinator_clock`
  (implementation tier, like the rest of that file: it injects through
  `coordinator.default_clock`)
- **Mutations re-targeted:** none. Added M65 (the cover adapters read the
  system clock instead of the coordinator's).
- **Contract change:** C5
- **Reason:** defect fix (P4 batch 4). `calculation.build_cover` never
  passed the coordinator's clock, so every cover adapter, and the SunData
  it builds, used `SYSTEM_CLOCK`, although agents.md says the coordinator
  hands its clock to them. An injected clock reached the move log but not
  the solar day, the forecast or the engine's time context: the new test
  saw a forecast for the system date instead of the injected one.
  `build_cover` and `from_config` now take `clock=`, and the coordinator
  passes its own. Production uses `SYSTEM_CLOCK` for both, so nothing
  changes there; goldens, truth table and house replay unchanged.

## L0024 · 2026-09-29 · last_moves shows the house's local time (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/simulation/test_regressions.py::test_regression_last_move_time_is_house_time`
  and `tests/runtime/test_explainer.py::test_regression_last_move_time_is_in_the_given_zone[*]`
- **Mutations re-targeted:** none. Added M66 (the last-move HH:MM uses the
  process time zone instead of HA's).
- **Contract change:** C5
- **Reason:** defect fix. The Position sensor's `last_moves` line
  ("HH:MM -> 37% (source: reason)") converted the move time with a bare
  `astimezone()`, which uses the PROCESS time zone: UTC in a docker
  container, so the hour differed from the house's clock. It now converts
  to HA's configured time zone, which the coordinator passes to the
  Explainer. The new scenario runs the process in Asia/Tokyo and failed
  with "01:00" for a 10:00 move in Salt Lake City. Position attributes keep
  their names; only this value changes. Goldens, truth table and house
  replay unchanged (none records this attribute).

## L0025 · 2026-09-29 · Start/end time entities honor a timestamp's UTC offset (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins
  `tests/simulation/test_regressions.py::test_regression_start_entity_timestamp_honors_its_offset`
  and the unit pins in `tests/runtime/test_schedule.py`
  (`test_regression_start_entity_timestamp_honors_its_offset[*]`,
  `test_end_entity_timestamp_honors_its_offset`,
  `test_a_midnight_timestamp_is_the_coming_midnight`)
- **Mutations re-targeted:** none. Added M67 (a time entity's UTC offset is
  dropped: the instant is read as local wall time).
- **Contract change:** C5
- **Reason:** defect fix. The start- and end-time entities were parsed with
  `ignoretz=True`, so a timestamp sensor's "2026-03-20T16:00:00+00:00"
  (10:00 in Salt Lake City) read as 16:00 local wall time: the window
  opened, or the end close fired, off by the UTC offset. A state with an
  offset is now that instant, converted to HA's configured zone
  (`helpers.get_local_datetime_from_str`, fed the zone by the
  coordinator); bare "HH:MM[:SS]" states and date-times without an offset
  keep their meaning, and 00:00 today still means the coming midnight.
  The fixed start/end options are unchanged. Goldens, truth table and
  house replay unchanged: no pinned config uses a time entity.

## L0026 · 2026-09-29 · Mode auto / hold / off, the hold service, hidden switch aliases (C7, P5 flip)
- **Removed:**
  - `tests/test_hub_behavior.py::test_house_mode_mixed_and_adaptive`
  - implementation tier, listed for the record:
    `tests/test_live_tunables.py::TestModeSelect::*`
- **Renamed:** none
- **Replacements:** `tests/test_hub_behavior.py::test_house_mode_mixed_and_auto`
  (windows in different Modes show `mixed`; the house Auto turns an off
  window back on AND ends another window's hold, both covers re-commanded:
  the old test pinned that "Adaptive" skipped a held cover),
  `tests/test_hub_behavior.py::test_house_mode_hold_and_off`,
  `tests/test_hub_behavior.py::test_hold_service_on_the_house_select_holds_every_window`,
  `tests/test_mode_select.py::*` (options, off stops moves and detection,
  selected / detected / service holds and their ends, area target, bad
  input, Return to auto, restore incl. the first-boot switch fallback and
  the old option names, hidden aliases, the Toggle Control write-through)
  and `tests/simulation/test_mode_and_hold.py::*` (the plan's "4 h hold on
  area office", a detected move -> hold -> expiry -> auto, a selected hold,
  off blocks moves and detection, hold and off across a cold restart).
  Implementation tier: `tests/runtime/test_mode.py::*`.
  Behavior-tier test bodies changed without changing ids:
  `tests/simulation/test_harness_smoke.py::test_select_option_drives_mode`
  (options `off` / `auto`); `tests/test_hub.py::test_house_mode_flips_all_entries`
  (options `auto` / `off`, asserts each window's Mode);
  `tests/test_entity_surface_v2.py::TestFreshSurface::test_categories_and_default_visibility`
  (the six switches are hidden by the integration, enabled);
  `TestMigration::test_migration_applies_surface_to_legacy_rows` (1.5, the
  switch rows hidden), `TestMigration::test_migration_is_idempotent` (5),
  `TestMigration::test_newer_minor_version_loads_unchanged` (1.6 is now the
  newer version) and `test_live_house_upgrade` (1.5; the 60 switch rows of
  the 15 windows hidden, still enabled); the version asserts (4 -> 5) in
  `tests/test_migration_1_3.py::test_live_house_migrates_to_1_3`,
  `test_multi_cover_entry_keeps_working_with_a_split_issue`,
  `tests/test_shadow_settings.py::*` and
  `tests/simulation/test_shadow_settings.py::*`. SimHouse keeps its call
  sites: `toggle("toggle_control", on)` selects Mode `auto` / `off`, and a
  `restart(seed_states=...)` that seeds a window's Toggle Control switch
  drops that window's captured Mode, so the window restores as on its
  first boot after the flip (from that switch). With that,
  `tests/simulation/test_gates_and_windows.py::test_control_on_force_apply`
  and the other `toggle_control` scenarios pass unchanged.
- **Mutations re-targeted:** added M47 (`coordinator.py`
  `async_handle_state_change`: the sun-tracking path ignores Mode off),
  M48 (`runtime/mode.py` `ModeControl.hold`: every hold lasts the override
  duration) and M51 (`runtime/mode.py` `restored_mode`: the first boot
  ignores the Toggle Control switch). M55 re-anchored from
  `entity_shared.override_until` to `OverrideTracker.expires_at` (same
  description; the latch + duration rule moved there, next to a requested
  hold's own end). M13 keeps its anchor (`ControlState.clears_overrides`);
  switching detection off now ends only detected overrides.
  Run with `--mutations M47,M48,M51,M55,M13 --jobs 3`: 5/5 killed, each
  by the simulation and entity tiers.
- **Contract change:** C7 (the window switches become the Mode select and
  hidden aliases; the house select's vocabulary)
- **Reason:** plan P5 v1.18.1 flip, batch 1 (Mode and Hold).
  `CONFIG_ENTRY_MINOR_VERSION` is 5.
  - The window's Mode select (unique_id `mode_select` kept) offers
    `auto` / `hold` / `off` (translation-keyed) and is the source of truth
    for its control state: a RestoreEntity whose `until` attribute carries
    a hold's end across restarts. `runtime/mode.py` holds the rules:
    `current_mode` (control off -> `off`; a held cover -> `hold`),
    `restored_mode` (own state; the old options "Manual" -> off, "Sun
    tracking" / "Sun + climate" -> auto; with no own state the Toggle
    Control switch's last state from the restore cache; a hold whose end
    passed -> auto) and `ModeControl` (select, alias, button, service).
  - The climate choice the old options carried is the house `climate_on`
    setting: migration 1.4 already recorded each window's Climate Mode
    switch, which is exactly what the old select derived "Sun tracking" vs
    "Sun + climate" from, so nothing is lost. The runtime still reads the
    Climate Mode switch (hidden) until the runtime acts on `resolve()`.
  - Hold: a detected manual move is Mode hold until latch + the override
    duration (unchanged clock rules). Selecting hold holds every cover in
    place for the override duration; `adaptive_cover.hold(duration?,
    position?)` is an entity service on the Mode selects (area and floor
    targets resolve to them) and on the house select (every window); with
    `position` it commands that position first (source `hold`, our own
    travel, never a manual move). A requested hold has a fixed end
    (`OverrideTracker.hold_until`) that the restart-clock option, the day
    rollover and switching detection off do not shorten; a person's move
    under it extends it to at least a detected override's end. Mode auto
    ends a hold and sends the target; off ends every hold.
  - Off: no moves, no detection (as Toggle Control off). Auto from off is
    the old switch-on: control on and a forced apply to covers that are
    not held. Return to auto is Mode auto (it now also turns an off window
    on).
  - The six switches are hidden (hidden_by integration), still enabled:
    new rows through the surface table (`visible_default`), existing rows
    through migration 1.5 (`async_apply_surface_to_registry`, unless the
    user already chose visibility or otherwise touched the row). Toggle
    Control writes through to the Mode (on keeps holds, as it always did;
    off is Mode off) and mirrors it; it no longer restores itself. The
    other five still restore and set `ControlState`.
  - The rule that keeps user-touched rows alone ignored nothing on HA
    2026.x: HA lists the entity's own name as a computed alias on every
    row, so every row looked "aliased by the user" and the migration could
    never hide (or disable) a default row. Only string aliases count now.
    No role was disabled or hidden by default before this change, so
    nothing observable changes for the 1.2 migration.
  - The house select offers `auto` / `hold` / `off` and the display-only
    `mixed`; picking one sets every window's Mode (`auto` now ends holds;
    the old "Adaptive" skipped held covers).
  - Card: modes are read from the Mode select (`until` first), Auto is one
    `select_option auto`, Hold one `adaptive_cover.hold` call with every
    target select (rooms), the detail sheet has Hold 1 h / 2 h / 4 h /
    until tonight, the house Return all to auto selects the house `auto`;
    the hidden Climate mode switch is still discovered for the Climate
    control. Bundle rebuilt.
  - Goldens, truth table and house replay byte-identical: with no manual
    action every window restores `auto`, which is the old Toggle Control
    on.

## L0027 · 2026-09-29 · A row's computed name alias is not a user choice (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pin
  `tests/test_entity_surface_v2.py::TestMigration::test_regression_default_alias_is_not_a_user_choice`
- **Mutations re-targeted:** none
- **Contract change:** C5
- **Reason:** defect fix, landed with the hide rule in a9eb63c (L0026)
  because only a hidden- or disabled-by-default role makes it observable.
  `entity_surface._user_touched` keeps the surface migrations away from
  rows the user adopted (renamed, aliased, ...). Home Assistant 2026.x
  lists the entity's own name as a computed alias (`er.COMPUTED_NAME`, not
  a string) on every registry row, and `any(row.aliases)` counted it, so
  every row looked user-touched: migration 1.5 hid none of the switch
  aliases, and a P6 disabled-by-default role would have stayed enabled
  everywhere. Only string aliases count now. The new pin fails without the
  fix (no row hidden) and checks that a row with a typed alias stays
  visible. Goldens, truth table and house replay unchanged.

## L0028 · 2026-09-29 · The runtime acts on the layered settings; edits store sparsely (C6, P5 flip)
- **Removed:**
  - `tests/test_shadow_settings.py::test_hub_created_at_1_4_is_not_lifted`
  - `tests/simulation/test_shadow_settings.py::test_legacy_option_change_raises_a_repair_issue`
  - `tests/simulation/test_shadow_settings.py::test_dropped_switch_flip_raises_a_repair_issue`
- **Renamed:** none
- **Replacements:** `tests/test_shadow_settings.py::test_hub_created_at_1_4_lifts_itself`,
  `tests/simulation/test_shadow_settings.py::test_recurring_change_is_a_window_override`
  (a recurring change is the window's own sparse value, acted on without
  a reload; changed back, the override goes away),
  `tests/simulation/test_shadow_settings.py::test_dropped_switch_writes_through`
  (the hidden detection switch writes the window's own value; detection
  stops and starts), the new pin
  `tests/test_shadow_settings.py::test_live_house_runs_on_the_same_settings`
  (all 15 live windows, running on the layers, act on exactly their legacy
  options and switch states: the diagnostics settings, `ShadeConfig` and
  the toggles) and `tests/test_layered_settings.py::*` (the options form
  and `change_settings` store sparse overrides and leave the legacy keys
  alone, the form shows what the window acts on, a new window starts from
  the house, a copy copies what the source acts on, invalid layers leave
  the window on its options). The house replay now asserts that every
  replayed window is lifted (a provenance), so the unchanged goldens pin
  the window acting on its resolved settings.
  Behavior-tier test bodies changed without changing ids (the storage
  assertions read what the window acts on, via the diagnostics settings,
  instead of the flat option key an edit no longer writes):
  `tests/test_change_settings.py::test_lookup_by_title_and_name`,
  `::test_rename_combines_with_option_changes`,
  `::test_regression_change_settings_enables_climate_mode`;
  `tests/test_live_tunables.py::TestNumberEntities::test_setting_number_persists_and_reloads`,
  `::test_regression_threshold_numbers_follow_unit_system[*]`;
  `tests/test_units_and_defaults.py::test_regression_thresholds_unit_aware_everywhere[*]`;
  `tests/test_one_page_options.py::test_submit_flattens_sections_and_preserves_rest`;
  `tests/simulation/test_lifecycle.py::test_end_time_rearm_via_settings_service`;
  `tests/test_window_setup_form.py::test_window_from_only_a_cover_and_azimuth_resolves_to_house_defaults`
  (the lifted window stores no override of its own);
  `tests/test_shadow_settings.py::test_lift_does_not_reload_a_running_window`
  (the window lifts the never-lifted house at its setup; enabling the hub
  migrates it without a second lift);
  `tests/simulation/test_harness_smoke.py::test_set_options_survives_reload`
  (a recurring edit does not reload, a one-time edit does);
  `tests/test_entity_surfaces.py::TestDiagnostics::test_diagnostics_shape`
  (two new keys). Implementation tier: `tests/settings/test_round_trip.py`
  (a copy has overrides of its own) and the spec-parity fakes.
  SimHouse: `set_options(**changes)` calls `change_settings` per window.
- **Mutations re-targeted:** added M90 (`layers.py` `effective_settings`:
  the runtime ignores a window's own values; killed by the simulation and
  entity tiers). M39 re-anchored from `__init__.handle_change_settings` to
  `layers.window_options_after` (same description: the merge of a window's
  edits into its options moved there). M13, M70 and M71 keep their
  anchors. Run with `--mutations M90,M39,M70,M71,M13 --jobs 3`: 5/5 killed.
- **Contract change:** C6 (the runtime acts on `resolve()`; plan P5
  v1.18.1 flip, batch 2)
- **Reason:** plan P5 flip. `layers.py` is the runtime side of the layered
  settings.
  - The runtime acts on `resolve()`: every refresh the coordinator reads
    `layers.effective_settings` (house -> floor -> area -> window, plus the
    lift's legacy values; one-time settings from the window's options) and
    sets the switch-era toggles (`climate_on`, `use_*`, `manual_detection`)
    from it. Values read only at setup (the listened-to entities, climate
    mode, the lux / irradiance / outside-temperature entities) reload the
    window when they change; everything else applies at the next refresh.
    Before the house is lifted, or when a stored layer breaks the spec
    (logged), a window acts on its legacy options and switch states as
    before.
  - A house that was never lifted lifts itself: at hub setup and at a
    window's setup (a hub created at 1.4 or later, a new install).
    Migration 1.4 no longer lifts a house that is already lifted: a second
    lift would rebuild the layers from the legacy keys and lose every edit
    since the flip. A window without its own overrides is adopted at its
    setup, before its coordinator reads the layers.
  - Edits: the options form (it shows the resolved values) and
    `change_settings` store one-time settings in the window's options and
    recurring ones in its `overrides`, sparsely: `values` where the spec
    lets a window override the option, `legacy` otherwise (a per-window
    exception, the lift's bucket for the same thing); a value equal to
    what the window inherits, or a cleared field / `None`, removes the
    override. An overrides-only update does not reload the window; it acts
    on it at once. The legacy flat keys are left as they are: a downgrade
    reads them, i.e. the settings as of the lift; edits made after the
    flip do not reach a downgraded install. `change_settings` keeps its
    schema and response.
  - The hidden per-window toggle switches show the value the window acts
    on and write through to the window's own value (a legacy value: the
    spec lets no window override them), removed when it equals the
    inherited one. Before the lift a switch is the setting, as before.
  - A new window (the add form, `add_entry` without `copy_from`) starts
    from the house's settings; "Copy from" / `copy_from` copy what the
    source window acts on.
  - The `settings_differ` repair issue (L0022) is retired: with the
    runtime on the layers there is no second set of values to compare.
    Setup deletes a leftover issue; its strings are gone. The pure
    comparison stays (`settings.shadow.compare`): it checks that a lift or
    an adoption is exact.
  - The Position sensor's `provenance` now comes from the refresh
    (`coordinator.provenance`); the diagnostics download gains `settings`
    (what the window acts on) and `settings_provenance`.
  - Goldens, truth table and house replay byte-identical, with every
    replayed window running on its resolved settings.

## L0029 · 2026-09-29 · adaptive_cover.set_profile: house, floor and room settings (C6, P5 flip)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins `tests/test_set_profile.py::*` (a house
  setting reaches every window without a reload; a room setting beats the
  house for its windows only and `null` removes it; floor < area < window
  precedence; a window moved to another room takes that room's settings at
  its next refresh; values a level may not hold, an id the house does not
  take, an unknown area, a floor without an id, an empty call and an empty
  house value are refused and store nothing)
- **Mutations re-targeted:** added M91 (`layers.py` `async_set_profile`:
  a floor's values are stored under the area of that id and an area's
  under the floor; killed by the entity tier, `--mutations M91 --jobs 3`).
- **Contract change:** C6 (a new service; plan "Services":
  `adaptive_cover.set_profile(scope, **opts)`)
- **Reason:** plan P5 flip ("The `hold` service and `set_profile` are
  added"). `set_profile(scope: house|floor|area, id?, **settings)` stores
  recurring settings in the hub's layered profiles. The schema takes every
  recurring setting (the change_settings validators, plus booleans for the
  toggles and entity ids for the entity fields, all nullable); which level
  may hold which setting is checked against the spec's home and
  overridable_at levels, the floor or area id against HA's registries. On
  a floor or an area `null` removes the value (the rooms inherit again);
  the house keeps an explicit empty value only for options that may be
  empty (entity fields, nullable service fields). Every window acts on the
  change at once (`layers.async_settings_changed`: a refresh; a setup-only
  value reloads the window). Response: `{scope, id, changed}`. The
  services.yaml entry lists the common settings; the schema accepts all.
  Goldens, truth table and house replay unchanged.

## L0030 · 2026-09-29 · House settings on the hub device; the window numbers are gone (C7, P5 flip)
- **Removed:**
  - `tests/test_live_tunables.py::TestNumberEntities::*`
- **Renamed:** none
- **Replacements:** `tests/test_house_settings.py::*` (the five house
  switches and six house numbers sit on the hub device, Climate primary,
  the rest CONFIG, and the windows have no numbers; the numbers show the
  house's values, the thresholds and privacy delay their spec default
  while unset; `test_regression_threshold_numbers_follow_unit_system[*]`
  moves here from the window numbers: HA's unit, its range, stored as
  given; a house number or switch reaches every window without a reload,
  and the window's hidden alias follows; a window with its own value keeps
  it) and `tests/simulation/test_house_settings.py::test_house_threshold_change_reaches_every_window`
  (the plan's scenario: a house cooling threshold change flips every
  window's season at once, no reload, before the next sun tick).
  Behavior-tier test bodies changed without changing ids:
  `tests/test_units_and_defaults.py::test_regression_thresholds_unit_aware_everywhere[*]`
  (reads the house threshold numbers); in `tests/test_entity_surface_v2.py`,
  `TestTranslations::test_number_names_match_tunable_specs` (every number
  name is a house number's), `TestMigration::test_migration_applies_surface_to_legacy_rows`
  (the legacy number rows are gone after setup; the other rows keep their
  identity) and `test_live_house_upgrade` (the live house loses its 105
  window number rows and the hub gains 11 house-setting rows; every other
  row keeps its entity_id). Implementation tier: `tests/settings/test_spec.py`
  (the live-number rows are the house numbers; the overhang's number drift
  is gone), `tests/test_translations.py` (numbers come from the hub table).
  `tests/contract/spec_parity.json` regenerated: the `number` surface is
  the house's six numbers (the same shapes for the thresholds, eye height,
  seat distance and privacy delay; the override duration new, in minutes
  1-1440; the overhang numbers gone), for every cover type and climate
  mode.
- **Mutations re-targeted:** added M92 (`house_settings.py`
  `HouseSetting._store`: a house entity's change is stored but not
  propagated; killed by the simulation and entity tiers). M52 re-run
  (its surface table changed around it): killed. `--mutations M92,M52
  --jobs 3`: 2/2.
- **Contract change:** C7 (the window numbers become house entities; plan
  "Entity surface": "7 numbers | removed in P5")
- **Reason:** plan P5 flip ("The house CONFIG entities go live", "The
  window numbers are removed, and their registry rows are cleaned up").
  - The hub device carries the house settings (`house_settings.py`): the
    Climate switch (`climate_on`, primary), the manual-move detection and
    the outside-temperature / lux / irradiance switches, and the numbers
    for the heating and cooling thresholds (HA's unit and range, from the
    spec), the manual override duration (minutes), the eye height, the
    seat distance and the privacy delay (CONFIG). Each shows the house's
    value in the layered settings and stores a change through
    `layers.async_set_profile`; every window acts on it at once
    (`async_settings_changed`), without a reload. They follow the settings
    signal, so a `set_profile` or a lift updates them too; they are
    unavailable before the house is lifted.
  - The seven window numbers are removed; a window's old number rows are
    removed at its setup (`entity_surface.async_remove_window_numbers`,
    idempotent, no config version needed). Their values live in the
    layers: the thresholds, eye height, seat distance and privacy delay are
    house settings (a floor, room or window can still set its own through
    `set_profile` and the options form), the overhang is window geometry
    (the options form, Reconfigure). A downgrade creates the window numbers
    again.
  - Card: the house Climate control uses the house Climate switch when the
    card acts through the hub (a card showing some rooms still toggles
    their windows' hidden Climate mode aliases), and "House settings"
    opens the house device page. Bundle rebuilt.
  - Goldens, truth table and house replay unchanged (no replay reads a
    number entity).

## L0031 · 2026-09-29 · get_profile reads the stored layers; house times on the hub (C6, C7, P5 flip)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins `tests/test_get_profile.py::*` (the
  response shapes for no scope, the house, a floor, an area and a window by
  window key or Mode select entity; the errors; a read-only user may call
  it), `tests/test_house_settings.py::test_house_times_reach_every_window_without_a_reload`
  and `tests/simulation/test_house_settings.py::test_house_end_time_change_moves_the_close`
  (the house end time re-arms every window's close, no reload).
  Behavior-tier test body changed without changing its id:
  `tests/test_entity_surface_v2.py::test_live_house_upgrade` (the hub now
  gains 14 house-setting rows: 5 switches, 6 numbers, 3 times).
- **Mutations re-targeted:** added M93 (`layers.py` `profile_values`: a
  floor's stored values are read from the area of that id and vice versa).
  Killed by the entity tier (`--mutations M93 --jobs 3`).
- **Contract change:** C6 (a new read service) and C7 (the plan's house
  time entities)
- **Reason:** P5 flip follow-up for the P6 card, which read the stored
  layers from the admin-only diagnostics.
  - `adaptive_cover.get_profile(scope?: house|floor|area|window, id?)`,
    response only (`SupportsResponse.ONLY`), read-only, callable by any
    user. No scope: `{house: {values, temperature_unit}, floors: {id:
    values}, areas: {id: values}}`. `house`: `{scope, id: null, values,
    temperature_unit}` (every house-level setting, the five toggles
    included). `floor` / `area` + id: `{scope, id, values}` (sparse; `{}`
    when the profile stores nothing). `window` + a window key or its Mode
    select entity: `{scope, id: window_key, title, area_id, floor_id,
    overrides: {values, legacy}, settings, provenance}`, `settings` being
    every setting the window acts on and `provenance` each one's source
    (`window`, `legacy`, `area`, `floor`, `house`, `default`). Unknown ids
    and missing ids are `ServiceValidationError`s. The service lives in
    `profile_service.py`; `__init__.py` only registers it.
  - The hub gains the plan's house time entities (CONFIG): End time, Quiet
    hours start, Quiet hours end (`house_settings.HouseSettingTime`,
    `time.py`), stored as "HH:MM:SS" in the house profile like the hub
    numbers; a change reaches every window at once, without a reload.
  - Goldens, truth table and house replay unchanged.

## L0033 · 2026-09-29 · One house entry with window subentries; the "Consolidate" repair (C8, P7)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none retired. New pins:
  `tests/test_house_subentries.py::*` (a fresh install creates the house
  entry 2.1 with the window as its `window` subentry: key = subentry_id,
  entities on the subentry, one device per window with `via_device_id` to
  the house device and the cover's area; "Add window" adds one and leaves
  the other windows running; the config flow adds one to a 2.x house and
  ends with `window_added`; a cover in use is refused; a 1.x house answers
  `consolidate_first`; Reconfigure rebuilds that window alone and stores an
  exception sparsely; deleting a subentry removes that window alone; a
  broken window gets a `window_setup_failed_*` issue while the house runs;
  `add_entry`, `change_settings` and `get_forecast` reach subentry windows;
  the house options are the house settings),
  `tests/test_consolidation.py::*` (the live snapshot through the repair
  fix flow: every entity row, registry id, entity_id, unique_id, name,
  area, device, Mode/hold, override and resolved setting unchanged, rows
  and devices on the house subentry, the subentry storing the entry's
  data and options verbatim, the dry run changing nothing, a backup
  confirmation, a multi-cover window blocking; a crash after window k at
  two points, then a restart, resumes and a second run changes nothing;
  the card's discovery attributes and rows), and
  `tests/replay/test_house_replay.py::test_house_replay_consolidated[*]`
  (the 90 house-replay cases through a house consolidated at 00:30: the
  same goldens, byte for byte).
  Behavior-tier test bodies changed without changing ids:
  `tests/test_config_flow.py::*`, `tests/test_window_setup_form.py::*` and
  `tests/test_one_cover_per_window.py::*` start from a 1.x hub (autouse
  `legacy_model`): they pin the window-entry flows, which a fresh install
  no longer takes (it creates the house with subentries);
  `tests/test_entity_surface_v2.py::TestMigration::test_newer_major_version_is_refused`
  uses major 3 (2 is the house now);
  `tests/test_migration_1_3.py::test_live_house_migrates_to_1_3` expects
  the `consolidate_house` issue as the house's only issue (no split);
  `tests/test_translations.py::test_flow_strings_cover_every_form` also
  walks the window subentry forms (add per cover type, reconfigure) and
  the house options; `tests/simulation/test_regressions.py::test_regression_unload_cancels_arrival_poll`
  unloads `house.entries[0]` (the window entry, or the house);
  `tests/simulation/test_shadow_settings.py::*` pin `model="legacy"` (a
  house from before P5). Test helpers: `WindowHandle` finds a window in
  the window entries (enabled) or the house's subentries and its rows by
  unique_id prefix, and reads a subentry window's settings from the
  house's diagnostics; SimHouse gets `model="legacy"|"house"`,
  `ADAPTIVE_COVER_SIM_MODEL` and `consolidate()`; the live-house loader
  moved to `tests/live_house.py`. Implementation tier:
  `tests/settings/test_round_trip.py::test_real_flows_round_trip[*]`
  starts from a 1.x hub too.
- **Mutations re-targeted:** re-anchored (offsets only, descriptions
  unchanged): M40, M41, M42, M43, M47, M52, M54, M56, M58, M59, M64, M71,
  M83, M91. Added M100 (`consolidate.py` `async_reparent_window`: an entity
  row moves to the house without its subentry link, so HA drops it when
  the device moves), M101 (`consolidate.py` `_async_add_subentry`: the
  subentry loses the window's overrides; an edit made since the P5 flip is
  lost), M102 (`house.py` `HouseRuntime.async_sync`: the listener rebuilds
  every window; the plan's M49) and M103 (`consolidate.py`
  `async_reparent_window`: the device stays on the window entry; the plan's
  M50). `--mutations M100,M101,M102,M103 --jobs 3`: 4/4 killed (the
  entity tier; the control run passed). The re-anchored M54 (area copy)
  and M59 (one-cover guard), whose functions changed around them:
  `--mutations M54,M59 --jobs 2`: 2/2 killed.
- **Contract change:** C8 (entries become house + subentries)
- **Reason:** plan P7 and ADR 0001, as amended by ADR 0006 (proposed):
  - Two config models until P8. A window is a window entry (1.x) or a
    `window` subentry of the house entry (the hub, 2.x) storing the entry's
    data and options verbatim; `windows.WindowEntry` reads both, and its
    key (the old entry_id, or a new window's subentry_id) is the unique_id
    prefix, the override-store key and the card binding key.
  - The house runtime (`house.py`) runs one coordinator per subentry,
    isolated (a failure is a repair issue and a retry), adds each
    window's entities with `config_subentry_id`, and its update listener
    rebuilds only the subentry that changed.
  - Consolidation is the `consolidate_house` repair: a dry run that
    asserts every window resolves the same settings, a backup
    confirmation, a snapshot in `.storage`, then per window: unload, add
    the subentry, move the entity rows, then the device (HA drops the
    entities a moving device leaves behind), verify, remove the entry.
    Resumable at every step; the house is 2.x before the first move.
  - Goldens, truth table and the house replay unchanged; the replay also
    runs byte-identical through a consolidated house.

## L0032 · 2026-09-29 · Season hysteresis: temp_hysteresis (C3, C6, C7)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none; new pins `tests/engine/test_season.py::*` (the
  sticky rule on both thresholds in both directions, the band edges, a jump
  across the band, the outside condition, missing thresholds, a missing
  reading leaving no memory, and hysteresis 0 deciding exactly as the plain
  rule for every previous season), `tests/simulation/test_season_hysteresis.py::*`
  (a °F house whose indoor reading wobbles 71.9 <-> 72.1 °F flips the
  season and the shade with every reading today and holds with 1 °F set on
  the hub, without a reload; a °C house with 0.5 °C; the first decision
  after a restart uses the plain rule) and
  `tests/test_units_and_defaults.py::test_threshold_hysteresis_is_unit_aware_everywhere[*]`
  (0-3 °C step 0.5 / 0-5 °F step 0.1, default 0, on the setup form, the
  options form, the hub number, change_settings and set_profile).
  Behavior-tier test bodies changed without changing their ids:
  `tests/test_entity_surface_v2.py::test_live_house_upgrade` (the hub gains
  15 house-setting rows: 5 switches, 7 numbers, 3 times),
  `tests/test_migration_1_3.py::test_migration_only_adds_keys[*]` (1.3 also
  writes the new option's runtime fallback, 0) and
  `tests/settings/test_house_lift.py::test_house_profile` (the lifted house
  stores `temp_hysteresis: 0`); implementation tier:
  `tests/test_shadow_settings.py::test_live_house_lifts_into_house_floor_and_area_profiles`
  (the same) and `tests/settings/test_spec.py` (the plan table row).
  `tests/contract/spec_parity.json` regenerated: the new option on the
  setup form's climate exceptions, the options form's climate section,
  change_settings / add_entry (0-3 °C, 0-5 °F) and the house numbers.
- **Mutations re-targeted:** M34 re-anchored (description unchanged): the
  season comparison moved from `calculation.ClimateCoverData.is_summer`
  to `engine/season.py` `decide_season`. Added M110 (`engine/season.py`
  `_margin`: the hysteresis is applied in the wrong direction) and M111
  (`coordinator.py` `_climate_data`: the previous season is ignored, every
  decision uses the plain rule). `--mutations M34,M110,M111 --jobs 3`: 3/3
  killed. The other patches are regenerated for line offsets only.
- **Contract change:** C3 (a new spec row on every generated surface), C6
  (a new recurring setting: house, with an area override) and C7 (a new
  house number on the hub)
- **Reason:** owner request. With the indoor temperature hovering at a
  threshold (72 °F heating in the house) the season flipped with every
  reading and the shades followed.
  - `temp_hysteresis` (HA's temperature unit; default 0 = off): once
    winter, the season stays winter until the temperature reaches low + h;
    once summer, until it falls to high - h; the intermediate band is left
    only h past a threshold (below low - h, above high + h). The rule is
    pure (`engine/season.decide_season(inputs, previous) -> Season`): the
    previous season is an input and the new one the output. Each window's
    coordinator keeps the last season in memory only: after a restart or
    reload, and after a decision without a temperature reading, the first
    decision uses the plain rule (not restored, by design).
  - The adapter (`ClimateCoverData.season`) decides the season once per
    refresh, so the position, the reason, the Control method and the
    forecast agree on it.
  - Hysteresis 0 decides exactly as before whatever the previous season:
    goldens, truth table and house replay unchanged.
  - Card: the house and room sheets list the setting (the house number,
    unit-aware range); bundle rebuilt.

## L0040 · 2026-09-29 · A late cover is positioned when it appears; registered covers are not "missing" (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none. New pin:
  `tests/simulation/test_device_failures.py::test_regression_late_cover_positioned_when_it_appears`
- **Mutations re-targeted:** none; M120 added (the first-state decision removed).
- **Contract change:** C5
- **Reason:** at the 2026-09-29 19:16 boot the windows set up before Zigbee created their covers: each logged "no such entity (renamed or removed?)" and skipped its command until the next sun update. A cover that is in the entity registry but has no state yet is now waited for quietly (debug), and a cover's first state triggers a normal decision (every gate still applies). A cover that is not in the registry at all (renamed or removed) is still skipped and reported once. No pinned output changed.

## L0050 · 2026-09-29 · The house is the only runtime: legacy path removed, migration 3.1, the consolidate_first nag (C7, C8, P8)
- **Removed:**
  - `tests/test_consolidation.py::*` (the P7 consolidation fix flow: v2.1 has none; a house consolidates on v2.0.x)
  - `tests/test_migration_1_3.py::*` (config entry migration 1.3 and the split repair: window entries no longer run or migrate)
  - `tests/test_shadow_settings.py::*` (migration 1.4, the lift at setup reading the switch states, adoption at setup)
  - `tests/simulation/test_shadow_settings.py::*` (a SimHouse in the legacy model from before P5)
  - `tests/test_one_page_options.py::*` (the per-window options flow: a window subentry has Reconfigure)
  - `tests/replay/test_house_replay.py::test_house_replay_consolidated[*]` (the replay through a consolidation at 00:30; `test_house_replay[*]` now runs every window as v2.1 holds it)
  - `tests/test_entity_surface_v2.py::test_live_house_upgrade`
  - `tests/test_entity_surface_v2.py::TestMigration::test_migration_applies_surface_to_legacy_rows`
  - `tests/test_entity_surface_v2.py::TestMigration::test_migration_keeps_user_choices`
  - `tests/test_entity_surface_v2.py::TestMigration::test_regression_default_alias_is_not_a_user_choice`
  - `tests/test_entity_surface_v2.py::TestMigration::test_migration_is_idempotent`
  - `tests/test_entity_surface_v2.py::TestPositionAttributes::test_multi_cover_entry_lists_every_cover`
  - `tests/test_entity_surfaces.py::TestConditionalEntityCreation::test_covers_basic_mode_switch_set`
  - `tests/test_entity_surfaces.py::TestConditionalEntityCreation::test_climate_with_all_aux_entities_full_switch_set`
  - `tests/test_entity_surfaces.py::TestConditionalEntityCreation::test_climate_without_aux_entities_climate_switch_only`
  - `tests/test_mode_select.py::TestRestore::test_first_boot_restores_from_the_toggle_control_switch`
  - `tests/test_mode_select.py::TestRestore::test_old_option_names_map_to_the_new_modes[*]`
  - `tests/test_mode_select.py::TestSwitchAliases::*`
  - `tests/test_layered_settings.py::test_invalid_layers_leave_the_window_on_its_options`
  - `tests/test_window_setup_form.py::test_reconfigure_of_the_house_entry_aborts`
  - implementation tier, listed for the record:
    `tests/settings/test_shadow.py::test_toggle_switches_match_the_switch_platform[*]`
    and `tests/runtime/test_mode.py::test_restored_mode[*]` (re-parametrized
    without the switch argument: 15 cases -> 10)
- **Renamed:**
  - `tests/test_house_subentries.py::test_the_config_flow_adds_a_window_to_the_house` -> `tests/test_house_subentries.py::test_the_integration_has_one_config_entry`
  - `tests/test_hub.py::test_hub_auto_bootstrapped_once` -> `tests/test_hub.py::test_the_house_is_the_only_hub`
  - `tests/test_window_setup_form.py::test_reconfigure_shows_the_one_time_settings_only` -> `tests/test_window_setup_form.py::test_reconfigure_shows_the_window_setup_and_its_exceptions`
  - `tests/test_layered_settings.py::test_options_form_stores_recurring_edits_as_sparse_overrides` -> `tests/test_layered_settings.py::test_reconfigure_stores_recurring_edits_as_sparse_overrides`
  - `tests/test_layered_settings.py::test_options_form_one_time_edit_goes_to_the_options` -> `tests/test_layered_settings.py::test_reconfigure_one_time_edit_goes_to_the_geometry`
  - `tests/test_layered_settings.py::test_options_form_shows_what_the_window_acts_on` -> `tests/test_layered_settings.py::test_reconfigure_shows_what_the_window_acts_on`
  - `tests/test_one_cover_per_window.py::test_options_form_shows_the_window_cover` -> `tests/test_one_cover_per_window.py::test_reconfigure_shows_the_window_cover`
  - `tests/test_one_cover_per_window.py::test_options_form_refuses_a_cover_another_window_drives` -> `tests/test_one_cover_per_window.py::test_reconfigure_refuses_a_cover_another_window_drives`
  - `tests/test_one_cover_per_window.py::test_options_form_moves_the_window_to_another_cover` -> `tests/test_one_cover_per_window.py::test_reconfigure_moves_the_window_to_another_cover`
  - `tests/test_one_cover_per_window.py::test_options_form_keeps_its_own_cover` -> `tests/test_one_cover_per_window.py::test_reconfigure_keeps_its_own_cover`
- **Replacements:**
  - `tests/test_upgrade_2_1.py::*` (new; on the live house as v2.0 consolidated it, `tests/fixtures/consolidated_v2_0`, generated by v2.0 code and loaded by `tests/consolidated_house.py`): the first start on v2.1 migrates the house to 3.1 with every kept entity row (entity_id, unique_id, name, area, device, visibility, category, subentry), every device (name, area, subentry, via), each window's resolved settings and provenance, its Mode and a running hold unchanged; the subentries store the window record, the 60 switch alias rows are gone, the house options keep only the layers, the snapshot is written once; a reload changes nothing; a migration that stopped part way finishes; a 1.x house shows the non-fixable `consolidate_first` issue, every entry fails to set up with its message and nothing is written; a house consolidated part way stays 2.1 until the entry is gone; a window v2.0 never ran refuses the migration without the nag. They replace the consolidation, migration 1.3 / 1.4 and live-house surface upgrade tests.
  - `tests/settings/test_window_record.py::*` (new): the record's keys, round trip, flat view, the v2.0 reader and its refusals.
  - `tests/replay/test_house_replay.py::test_house_replay[*]`: each live window now runs as a 2.1 house migrated to 3.1 (its lifted layers, its registry rows on the subentry, the Mode from the Toggle Control switch): the same goldens byte for byte.
  - `tests/test_init.py::test_a_1x_window_entry_refuses_to_set_up`, `tests/test_mode_select.py::TestNoSwitches::test_a_window_has_no_switch_entities`, `tests/test_mode_select.py::TestRestore::test_an_old_toggle_control_state_is_not_read`, `tests/test_mode_select.py::TestRestore::test_a_restored_off_does_not_move_at_startup`, `tests/test_entity_surfaces.py::TestConditionalEntityCreation::test_a_cover_brings_the_return_button_and_no_switch`, `tests/test_entity_surfaces.py::TestConditionalEntityCreation::test_climate_adds_no_window_switch`, `tests/test_layered_settings.py::test_invalid_layers_stop_the_window_until_fixed`, `tests/test_translations.py::test_issue_and_exception_strings_cover_the_code`, `tests/test_entity_surface_v2.py::TestPositionAttributes::test_window_identity` (no `cover_entities`), `tests/test_entity_surface_v2.py::TestFreshSurface::*` (the surface on new rows), `tests/test_house_settings.py::test_house_settings_are_hub_entities` (windows have no switch or number rows).
  - Behavior-tier test bodies changed without changing ids: every root-tier test that built window config entries now builds a 3.1 house with window subentries (`tests/house_model.py`: `mock_house`, `mock_window_entry` whose window key is the house's entry_id, the house lifted from the windows so each acts on exactly its options); the flow tests drive the first-window config flow and "Add window" / "Change window" (`tests/window_form.py`); `TestMigration::test_newer_minor_version_loads_unchanged` (a 3.2 house), `::test_newer_major_version_is_refused` (4.1), `::test_user_reenabled_entity_stays_enabled` (a reload of the house); SimHouse is house-only (no `model=`, no `consolidate()`, a `window_keys=` argument; `toggle()` maps the old window switch keys to the Mode or the house's switches, `switch()` reads them; teardown removes the house entry); the simulation and characterization bodies read the Mode and the house switches instead of the window switches. Implementation tier: `tests/settings/test_shadow.py`, `tests/settings/test_round_trip.py` read the record helpers.
- **Mutations re-targeted:** retired M51 (`runtime/mode.py` `restored_mode`: the Toggle Control fallback is gone), M71 (`shadow.py` `_switch_state`: the lift at setup is gone), M100, M101 and M103 (`consolidate.py`: the consolidation lives in v2.0.x only). Re-anchored with unchanged descriptions: M39 (`layers.window_record_after`: the one-time edits merge into the window's geometry), M90 (`layers.effective_settings`: the window's overrides come from its record), M102 (`house.HouseRuntime.async_sync`), and by offsets only M40, M41, M42, M43, M47, M48, M52, M54, M56, M58, M59, M64, M70, M83, M91, M92, M93. Added M130 (`upgrade.async_migrate_house`: migrates with window entries left), M131 (`upgrade._is_alias_row`: the switch alias rows are kept), M132 (`upgrade.house_options_3_1`: the hub's leftovers are kept), M133 (`window_record.record_from_v2_0`: a migrated window loses its overrides), M134 (`window_record.GEOMETRY_KEYS`: the record drops max_elevation), M135 (`upgrade.async_check_consolidate_issue`: no nag), M136 (`upgrade.async_migrate_house`: the house stays at major 2), M137 (`windows.WindowEntry.name`: the device takes the title), M138 (`house.HouseRuntime.async_sync`: an overrides-only change rebuilds the window), M139 (`layers.new_window_record`: a new window gets no overrides), M140 (`layers.initial_house_options`: a fresh house stores nothing). `--mutations M130,M131,M132,M133,M134,M135,M136,M137,M138,M139,M140,M39,M90,M102,M54,M59,M56 --jobs 3` (after the merge of integ/v2.0.0): 17/17 killed, control run passed. M39 by the simulation tier; M90, M102 and M138 by the simulation and entity tiers; the rest by the entity tier (M130-M137 by `tests/test_upgrade_2_1.py`).
- **Contract change:** C7 (the six per-window switch aliases and their registry rows are removed; the Mode select no longer reads the Toggle Control switch), C8 (the window subentries store the window record; the house entry is 3.1)
- **Reason:** plan P8 and ADR 0007 (proposed):
  - The house entry is the only config entry that runs (`single_config_entry`). Window entries (1.x) and a house that still has them are refused with the `consolidate_first` message and the non-fixable `consolidate_first` repair issue (consolidate on v2.0.x first); nothing is written to them.
  - A consolidated house (2.1) migrates at its first start to 3.1: a snapshot (`.storage/adaptive_cover.v2_0_snapshot`), each subentry rewritten to the window record `{window_key?, name, cover_entity_id, cover_type, geometry, overrides}`, the switch alias rows removed, the house options cut to the layers. The major bump makes v2.0.x refuse the house.
  - Removed: the legacy window-entry runtime (`windows.py` legacy view, the hub bootstrap, the per-window options flow and the window-entry reconfigure and import steps), the split repair, `consolidate.py`, `repairs.py`, `migration.py`, `shadow.py` (lift and adoption at setup, switch-state reading), the switch aliases, the `group` dual-write (the runtime derives `[cover]` from the record), the legacy flat keys, `hass.data[DOMAIN]` (the coordinators are found through the house's `runtime_data`), the Toggle Control restore fallback and the pre-flip Mode option names, `cover_entities`, `is_lifted`/`house_not_lifted`, the `model=legacy` simulation parametrization and the `test-house-model` task.
  - New windows get their overrides when they are created (`layers.new_window_record`, `layers.initial_house_options`), as v2.0 adopted them at their first setup.
  - `spec_parity.json` regenerated: the per-window options form (`options.init.*`) is gone; the first-window config flow (`setup.first.*`, the add form without "Copy from"), the house options form (`options.house.*`; the 34 keys it shares with the old options form have the same descriptors) and the Reconfigure form's exceptions sections (`setup.reconfigure.exceptions_*`, fields pre-filled with what the window acts on) are pinned (with `temp_hysteresis`, merged from v1.21.0, on each of them).
  - Goldens and the truth table unchanged; the house replay byte-identical through the 2.1 -> 3.1 migration.

## L0060 · 2026-09-30 · v2.1 upgrades a v1.19.x house in one start (C8, ADR 0008)
- **Removed:**
  - `tests/test_upgrade_2_1.py::test_a_1x_house_shows_the_nag_and_changes_nothing` (a 1.x house no longer gets the nag: it upgrades; a house older than 1.2 stops with the upgrade_stopped repair instead)
  - `tests/test_upgrade_2_1.py::test_a_house_consolidated_part_way_stays_on_2_0` (a window entry left by v2.0.x is now moved at the first start)
- **Renamed:** none
- **Replacements:**
  - `tests/test_upgrade_from_1_19.py::*` (new; on the live house as v1.19.x holds it, `tests/v1_19_house.py`: the v2.0 consolidation fixture put back into 15 window entries and a lifted hub at 1.5, the edited window holding its edit in the flat option only): `test_live_house_upgrades_from_1_19_in_one_start` (one start: 3.1, a subentry per window keyed by its old entry_id, every entity and device registry id, entity_id, unique_id, name, area, device, visibility and category unchanged, the 60 switch alias rows removed, the disabled "SE" entries left, each window's resolved settings and provenance equal to what v2.0 showed for the same house, the Mode and a running hold kept, the v1.19.x edit kept, the v1 snapshot written before anything moved, every phase logged, the notification), `test_the_upgraded_house_restarts_unchanged`, `test_a_crash_part_way_resumes_at_the_next_start` (a crash between a window's row moves and its device move; the next start finishes with the same result), `test_a_failed_verification_removes_nothing` (a device that does not move: every entry, row, device and placement back as v1.19.x left it, versions unchanged, the `upgrade_stopped` repair), `test_a_row_lost_while_moving_asks_for_the_backup` (`upgrade_stopped_restore_backup`), `test_a_house_at_1_2_is_brought_to_1_5_then_moved` (1.3, the lift and 1.5 run by the upgrade; settings equal to v2.0's), `test_a_house_older_than_1_2_stops_and_changes_nothing`, `test_a_window_entry_enabled_after_the_upgrade_gets_the_nag` (ADR 0007's nag for a 3.x house), `test_window_entries_of_a_disabled_house_get_the_nag` (no enabled house to move them into), `test_an_unexpected_error_while_moving_is_undone` (Home Assistant raises mid-move: undone, nothing removed), `test_a_switch_turned_off_in_v1_19_stays_off` (a window acts on its restored switch state after the upgrade; every live switch is at its default, so the house fixture alone cannot show it).
  - `tests/test_upgrade_2_1.py::test_a_house_consolidated_part_way_on_2_0_finishes_at_the_first_start` (new): a window entry v2.0.x left next to a 2.1 house is moved, then the house migrates; the other subentries become their records as before.
  - `tests/replay/test_house_replay.py::test_house_replay[*]`: each live window now starts as v1.19.x holds it (a 1.5 hub with its lift, the window as its own 1.5 entry, its switches restoring their live states) and is moved into the house at setup: the same goldens byte for byte. `tests/replay/test_house_replay.py::test_house_replay_through_v2_0[*]` (new): every window on the summer solstice through the v2.0.x path (a 2.1 house, then migration 3.1), same goldens.
  - Test bodies changed without changing ids: `tests/test_translations.py::test_issue_and_exception_strings_cover_the_code` (the `upgrade_stopped` issues and exception).
- **Mutations re-targeted:** M130 re-anchored with its description unchanged (`upgrade.async_migrate_house` now checks `legacy_window_entries` directly: `needs_consolidation` is the nag's list, empty for a house below 3.x). Offsets only: M131, M132, M135, M136, M56. Added M150 (`consolidate._async_consolidate`: the verification is skipped), M151 (an old entry is removed before its rows move), M152 (`async_reparent_window`: the device moves before its rows), M153 (the house becomes 2.1 before the moves are verified), M154 (a stopped upgrade does not undo the moves), M155 (`_plan_window`: a window edited in v1.19.x is not adopted again), M156 (`_switch_state`: the toggles ignore the restored switch states), M157 (`_async_add_subentry`: a resumed upgrade adds a second subentry), M158 (no snapshot), M159 (no notification), M160 (`async_undo` leaves the subentry), M161 (`async_bring_to_1_5`: no lift), M162 (`OLDEST_MINOR`: entries older than 1.2 are moved). M150 was re-anchored once more (unchanged description) when the move phase started undoing any error. `run_mutations.py --jobs 4 --first-kill --mutations M56,M130,M131,M132,M135,M136,M150-M162`: 18/19 killed, control passed; M156 survived (every live switch sits at its default), so `test_a_switch_turned_off_in_v1_19_stays_off` was added. Rerun `--mutations M150,M154,M156,M159`: 4/4 killed, but that control failed once in the entity tier under load (1 of 1633 tests; the full suite then passed in both environments), so the four were confirmed again on the upgrade tests (`--tiers entity --pytest-args "... -k upgrade_from_1_19"`): 4/4 killed, control passed. All caught by the entity tier (`tests/test_upgrade_from_1_19.py`, M130-M136 by `tests/test_upgrade_2_1.py`).
- **Contract change:** C8 (a house below 3.x with window entries is moved into the house at its first start; the `upgrade_stopped` repair; the nag only for window entries next to a 3.x house or with no house)
- **Reason:** owner decision 2026-09-30 (ADR 0008, proposed): the live house goes from v1.19.1 to v2.1 in one release and one restart, with no click.
  - `consolidate.py` (the v2.0 move logic as an upgrade step): 1.x schema -> plan -> snapshot `.storage/adaptive_cover.v1_snapshot` -> move (rows before the device) -> verify (rows, devices, resolved settings and provenance through the v2.1 read path) -> the house becomes 2.1, the window entries are removed last -> migration 3.1 (unchanged). Nothing is removed and no version changes before the verification passes; a failure undoes the moves (v1.19.x runs the house as before) and raises `upgrade_stopped`; a crash resumes.
  - v1.19.x acts on the flat options and the switch states, not the layers: the plan compares with those, and a window whose overrides disagree (an edit v1.19.x wrote to the flat option) is adopted again, so it keeps acting on the same values.
  - Window entries no longer raise at setup while the house moves them (they return False, no log); `consolidate_first` stays for window entries next to a 3.x house or with no house.
  - Goldens and the truth table unchanged; the house replay byte-identical through both upgrade paths.

## L0080 · 2026-09-30 · A move under way at a restart or reload is not a manual move (C5)
- **Removed:** none
- **Renamed:** none
- **Replacements:** none. New pins:
  `tests/simulation/test_restart_mid_travel.py::test_regression_restart_mid_travel_not_manual[zigbee_after_ha_start]`,
  `tests/simulation/test_restart_mid_travel.py::test_regression_restart_mid_travel_not_manual[zigbee_before_ha_start]`,
  `tests/simulation/test_restart_mid_travel.py::test_regression_restart_mid_travel_not_manual[cover_moving_at_setup]`,
  `tests/simulation/test_restart_mid_travel.py::test_regression_restart_mid_travel_not_manual[motor_carries_on]`,
  `tests/simulation/test_restart_mid_travel.py::test_manual_move_right_after_restart_still_latches[remote_right_after_restart]`,
  `tests/simulation/test_restart_mid_travel.py::test_manual_move_right_after_restart_still_latches[against_the_move_under_way]`,
  `tests/simulation/test_restart_mid_travel.py::test_manual_move_right_after_restart_still_latches[after_a_stale_motion_state]`,
  and the harness mechanism `tests/simulation/test_harness_smoke.py::test_restart_mid_travel_mechanics`
  (new SimHouse APIs: `stop_motor`, `device_reports`, `restart(covers_late=True)`).
- **Mutations re-targeted:** none re-targeted; M09, M10, M43, M47, M57, M58, M64, M111 and M120 re-anchored by offsets only. Added M170 (`CommandTracker.first_sight`: a cover first seen moving has nothing under way), M171 (`CommandTracker.note_report`: an inherited travel never expires), M172 (`CommandTracker.note_report`: motion either way continues it), M173 (`CommandTracker.classify_report`: its landing inside our travel window is foreign), M174 (`async_check_cover_state_change`: a report on its way is a motion start), M175 (`async_handle_cover_state_change`: its landing goes to the landing check), M176 (`async_handle_cover_state_change`: its landing does not decide again), M177 (`__init__`: the cover is not looked at at setup), M178 (a cover back from unavailable is not looked at), M179 (a cover's first state is not looked at), M180 (`CommandTracker.release`: a user-id change keeps the inherited travel). `run_mutations.py --jobs 4 --xdist 2 --first-kill --mutations M170-M180,M09,M10,M57,M64,M43,M47,M58,M111,M120`: 20/20 killed, control run passed; M180 by the entity tier (`tests/runtime/test_command_tracker.py`), M09 by characterization, the rest by the simulation tier.
- **Contract change:** C5
- **Reason:** house, 2026-09-30 07:23, Den southwest: the window told the shade 5 -> 97 at sunrise, ZHA reported `opening` (still at 5) and Home Assistant restarted for an upgrade seconds later, which cut the move short. After the restart ZHA reported `opening` again (its restored state; the cover had held HA's `unavailable` placeholder) and then `open` at 5. The new coordinator had not sent the command, so the landing read as a person's move ("manual change detected") and the window went on Hold for 2 h. A cover the coordinator first sees `opening`/`closing` (at setup, or its first report after it had no state or was unknown/unavailable) is now finishing a move of unknown provenance: its reports in that direction and its landing, for at most `TARGET_TIMEOUT`, are never manual; the landing makes the window decide again (every gate applies), and a landing inside our own travel window ends that move while ours keeps travelling. Motion the other way, a user-id change, and anything after `TARGET_TIMEOUT` are judged as before. A time-based startup grace was rejected: it would hide a person who moves a shade at rest right after a restart. No pinned output changed.
