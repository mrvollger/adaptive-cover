# ADR 0006: Window subentries in v2.0: storage, versions and the move order

- **Status:** Proposed (P7 branch; the owner accepts it at merge)
- **Date:** 2026-09-29
- **Delivered in:** P7 (v2.0.0)
- **Amends:** [ADR 0001](0001-house-entry-and-window-subentries.md) (the subentry data shape, when the house becomes 2.x, the order of the registry moves). The rest of ADR 0001 stands.
- **Amended by:** [ADR 0007](0007-house-only-in-v2-1.md) (P8 reshapes the subentry data and makes the house 3.x).
- **Source:** [`docs/refactor_plan.md`](../refactor_plan.md), "P7", "Migration of the live house"; Home Assistant 2026.8.0 and 2026.9.4 (`config_entries.py`, `helpers/device_registry.py`, `helpers/entity_registry.py`)

## Context

Building P7 against the installed Home Assistant versions showed four places where ADR 0001 and the plan's migration steps do not fit the platform, or can be made safer:

- **A device that changes config entry takes its entities with it.** In 2026.8 and 2026.9 a device belongs to exactly one config entry and subentry. When `async_update_device(new_config_entry_id=…)` moves it, the entity registry removes every entity of that device that is still on the old entry (and, for a subentry change, still on the old subentry). The plan moves the device first and the entities second, which would delete every entity of the window.
- **A config entry's major version is the flow's version.** Home Assistant refuses an entry whose major version is above the flow handler's `VERSION`, and creates new entries at that version. A 2.x house therefore needs the flow at version 2, which would also stamp version 2 on new window entries.
- **Subentries have no options flow.** A subentry type offers "Add" (`user`) and "Reconfigure" only, in both versions.
- **The P8 data shape needs the legacy keys gone.** ADR 0001 stores `{window_key, cover_entity_id, cover_type, geometry, overrides}`. Until P8 removes the legacy flat keys and the `group` dual-write, a reshape would be a second, lossy migration inside the first.

## Decision

- **Storage.** A window subentry stores the window entry's data and options verbatim: `{"window_key": <old entry_id>, "data": {...}, "options": {...}}`. A new window has no `window_key`; its key is its subentry_id. `windows.WindowEntry` reads both kinds the same way, so every window resolves exactly the settings it resolved as an entry. P8 reshapes the data to ADR 0001's form when it removes the legacy keys.
- **Versions.** The flow's `VERSION` is 2 (`HOUSE_ENTRY_VERSION`). Window entries, and a hub that still has them, are created at 1.5 and stay 1.x. A fresh install creates the house at 2.1 with the first window as its subentry. The consolidation makes the house 2.1 **before** the first window moves, not after the last: an older version then refuses the house instead of running it without its windows.
- **Which model adds a window.** A 2.x house adds windows as subentries ("Add window", the `add_entry` service, and the config flow's user step, which adds one and ends with "window added"). A 1.x house keeps adding window entries, so a downgrade before the click keeps working; its "Add window" asks to consolidate first.
- **Move order.** Per window: unload the entry; add the subentry; move the entity rows to the house and the subentry; **then** move the device (with `via_device_id` = the house device); check that every row still exists and that nothing is left on the entry; only then remove the entry. A restart between the device move and the entry removal lets the entry recreate a device; the resumed run moves the entities to the device that already moved, and the duplicate goes with the entry.
- **Reconfigure is the whole form.** A window subentry's Reconfigure is the one-screen form with the window's one-time settings and, collapsed, its exceptions (its recurring values, stored sparsely as overrides). The house entry's options are the house settings.
- **Preconditions and snapshot.** The fix flow asks the owner to confirm a backup from the last 24 hours (Home Assistant has no stable API for "age of the last backup" in both versions). It refuses to start when the house has no layered settings, a window drives several covers, a window entry is not migrated or failed to load, or any window would resolve other settings. A window entry that is not loaded moves anyway. The snapshot goes to `.storage/adaptive_cover.v1_snapshot` (entries, registry rows, override store), written once; the dashboard JSON is not copied (cards bind by window key, which does not change).
- **Disabled window entries** are left as they are and listed in the dry run.
- **The hub's leftover geometry and `group`** stay until P8.

## Consequences

- Consolidation keeps every unique_id, entity_id, registry id, name, area, device and Mode/hold, and every resolved setting; the house replay runs byte-identical through a consolidated house (`tests/replay/test_house_replay.py::test_house_replay_consolidated`).
- Mutations M100 (an entity loses its subentry link) and M103 (the device stays on the entry) are caught by the row checks before the entry is removed; M101 (the subentry loses the window's overrides) by the settings comparison; M102 (the listener rebuilds every window) by the entity-surface tests.
- Every 1.x entry goes through `async_migrate_entry` at each start (the flow is at 2); it only runs the minor steps it still needs.
- The subentry data carries the legacy keys until P8, as window entries do today.
- After the click, the rollback is the backup (unchanged from ADR 0001); before it, a downgrade.

## Alternatives considered

- **Move the device first (the plan's order).** Rejected: Home Assistant deletes the entities.
- **Reshape the data now.** Rejected: two migrations in one click, and a downgrade story for keys P8 removes anyway.
- **Keep the flow at version 1 and store the house as 1.x.** Rejected: an older version would load the house without its windows and silently stop them.
- **A per-window options flow.** Not available for subentries in Home Assistant 2026.8 or 2026.9.
