# ADR 0001: One house entry with window subentries

- **Status:** Accepted
- **Date:** 2026-09-28
- **Delivered in:** P7 (v2.0.0); legacy path removed in P8 (v2.1.0)
- **Source:** [`docs/refactor_plan.md`](../refactor_plan.md), "Config model", "P7", "Migration of the live house"; owner decision 3

## Context

- Today each window is its own config entry. The live house has 15 window entries and one hub entry ("Adaptive Cover All").
- Recurring settings (thresholds, override duration, weather entity and more) are copied into every entry. To change one, you edit 15 entries.
- There is no layer between "one window" and "the whole house", so HA floors and areas cannot carry settings.
- The house loads 318 entities. Most of them are per-window switches and numbers.
- HA 2026.8 supports config subentries (`ConfigSubentryFlow`), `via_device_id` and `config_subentry_id` in the device and entity registries.

## Decision

- The hub entry becomes the single **house entry**. It keeps its entry_id. It is VERSION 2 after consolidation.
- House options hold `{house: {...}, floors: {floor_id: {sparse}}, areas: {area_id: {sparse}}, unit_system}`.
- Each window is a config **subentry** of type `window`:
  - `unique_id` is the cover's entity-registry id, so the same cover cannot be added twice (see [ADR 0002](0002-one-cover-per-window.md)).
  - `data` is `{window_key, cover_entity_id, cover_type, geometry: {...}, overrides: {sparse}}`.
- **`window_key`** is the old entry_id for a migrated window and the subentry_id for a new one. It is the unique_id prefix, the override-store key and the card binding key. **No unique_id or override state is ever re-keyed.**
- `entry.runtime_data` holds a `HouseRuntime`. `hass.data[DOMAIN]` goes away, except for the override store.
- The update listener compares `entry.subentries`. A changed window is rebuilt alone. A house-profile change re-resolves every window in place, with no reload.
- Each window sets up in isolation. A failing window raises a repair issue, and the rest of the house keeps running.
- Consolidation of the live house is a **user-triggered repair fix flow**. It needs a backup less than 24 h old, writes a snapshot, shows a pure preview that asserts `resolve(new) == resolve(old)` for every window, and then moves each legacy entry. Progress is recorded, so the run can resume after a crash.
- P8 removes the legacy path and sets `single_config_entry` in the manifest.

## Consequences

- One place controls every shade, and settings can live at house, floor or area level ([ADR 0003](0003-settings-precedence.md)).
- Entity unique_ids, entity_ids, restore state, history, override state and card bindings (`entry_id` = `window_key`) survive the migration.
- v2.0 must load both legacy entries and subentries until P8. The simulation suite runs under both `model=legacy` and `model=house` until then.
- VERSION 2 makes older code refuse the entry. After consolidation, the rollback is to restore the backup.
- One entry is one failure domain. Per-window setup isolation and per-window repair issues contain that risk.
- The migration is the riskiest step. CI rehearses it on the sanitized live-snapshot fixture, with crash injection after window *k* and an idempotency check.
- New mutations guard the design: M49 (the listener reloads every window) and M50 (consolidation leaves an entity or device unmoved).
- The code depends on the HA 2026.8+ registry API. It uses only `via_device_id`, `config_subentry_id` and `async_get_device_by_identifier(config_entry_id=)`.

## Alternatives considered

- **Keep one entry per window with a separate hub.** Rejected: no settings layers, and the hub stays a second model of the house.
- **Re-key override state to new ids.** Rejected: using the old entry_id as `window_key` makes re-keying unnecessary.
- **Make subentries optional.** Rejected: two config models would persist indefinitely.
