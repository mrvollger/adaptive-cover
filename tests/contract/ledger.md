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


## L0004 · 2026-09-29 · One option spec generates every settings surface (C3)
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

## L0005 · 2026-09-29 · Window height and distance take up to 10 m everywhere (C3)
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

## L0006 · 2026-09-29 · delta_time accepts 0 on every surface (C3)
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

## L0007 · 2026-09-29 · Climate thresholds are unit-aware on every surface (C3)
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
