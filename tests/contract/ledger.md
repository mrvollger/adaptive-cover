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

