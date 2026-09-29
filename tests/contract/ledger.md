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

## L0010 · 2026-09-29 · An unreadable time entity no longer stops the window (C5)
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

## L0011 · 2026-09-29 · An end-time entity at 00:00 means the coming midnight (C5)
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

## L0012 · 2026-09-29 · The fixed start time feeds the start-after-end check (C5)
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

## L0013 · 2026-09-29 · The delta gate uses the same snap positions as the other gates (C5)
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

## L0014 · 2026-09-29 · The Control method sensor returns to intermediate (C5)
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
