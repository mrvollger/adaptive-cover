# ADR 0007: The house is the only runtime in v2.1: the window record, the nag and version 3

- **Status:** Proposed (P8 branch; the owner accepts it at merge)
- **Date:** 2026-09-29
- **Delivered in:** P8 (v2.1.0)
- **Amends:** [ADR 0001](0001-house-entry-and-window-subentries.md) (the window subentry's data shape; the house's version after P8) and [ADR 0006](0006-window-subentries-in-v2.md) (it deferred the reshape to P8). The rest of both stands.
- **Amended by:** [ADR 0008](0008-upgrade-from-1-19-in-one-start.md) (2026-09-30): v2.1 moves a v1.19.x house's window entries into the house at its first start, so "No consolidation in v2.1" no longer holds; the nag stays for window entries next to a 3.x house or with no house.
- **Source:** [`docs/refactor_plan.md`](../refactor_plan.md), "P8", "Migration of the live house"; Home Assistant 2026.8.0 and 2026.9.4 (`config_entries.py`)

## Context

P8 removes the legacy path: window config entries as runtime sources, the per-window switch aliases, the `group` dual-write, the legacy flat keys in window data, the `model=legacy` simulation parametrization and the `hass.data[DOMAIN]` coordinator index. Three questions have no answer in the plan or in ADR 0001 and 0006:

- **Where does an unconsolidated house go?** The plan says "a repair nags until it is". v2.1 no longer has the window-entry runtime, and the consolidation needs it: its dry run resolves each window entry as it runs today, and the entries must be at 1.5 (migrations 1.2 to 1.5, the P5 lift reading the switch states). Keeping the consolidation in v2.1 keeps most of the legacy path.
- **What exactly does a window subentry store?** ADR 0001 names `{window_key, cover_entity_id, cover_type, geometry, overrides}`. The live house has a window whose title was renamed without its name ("Leanne's door", named "Leanne's west"): its device carries the name, not the title.
- **What does a downgrade do with the new shape?** A minor version bump leaves the house at 2.x, and Home Assistant loads a newer minor as is: v2.0.x would load subentries it cannot read (no `data`, no `options`) and run windows with no settings.

## Decision

- **No consolidation in v2.1.** A house with enabled window entries (a 1.x house, or a consolidation that stopped part way) does not run: every entry fails to set up with the `consolidate_first` message, and the non-fixable `consolidate_first` repair issue says what to do (install v2.0.x, fix its "Move your windows into the house" repair, update again). v2.1 writes nothing to such a house, so v2.0.x finds every entry as it left it. Disabled window entries drive nothing and do not count; one enabled again fails the same way (the house keeps running).
- **The window record** (`settings/window_record.py`): `{window_key?, name, cover_entity_id, cover_type, geometry, overrides: {values, legacy}}`. `name` is ADR 0001's shape plus the name, which the window's device and entities carry and which can differ from the subentry title. `geometry` holds the window-home options of the spec (the one-time settings); the copies of the recurring settings, `group` and `mode` are not stored. The runtime reads a flat view (`WindowRecord.options`: the geometry plus `cover_entity_id` and `group = [cover]`), computed, never stored.
- **Migration 2.1 -> 3.1** (`upgrade.py`, at the first start of a consolidated house): write a snapshot once (`.storage/adaptive_cover.v2_0_snapshot`: the house entry with its subentries and the registry rows it removes), rewrite every window subentry as a record, remove the switch alias rows (and any window number row left), keep only `house`, `floors`, `areas` and `temperature_unit` in the house options, then set the version. A subentry already rewritten is skipped, so a migration that stopped part way finishes at the next start. The migration is refused, with nothing written, while window entries are left, or when a window has no layered settings of its own (it never ran on v2.0; the record would lose its settings) or drives several covers.
- **Version 3.** The migrated house is 3.1, not 2.2: v2.0.x (flow version 2) then refuses it instead of running windows it cannot read. The rollback is the Home Assistant backup, as after the consolidation.
- **New windows get their overrides at creation.** The lift and the adoption at setup are gone. A fresh install lifts its first window into the house options (`layers.initial_house_options`); every later window is adopted against the house when it is created (`layers.new_window_record`), exactly as v2.0 adopted it at its first setup.
- **The Mode select restores only itself.** The fallback to the Toggle Control switch's last state (and the mapping of the pre-flip option names) served the first boot after the P5 flip; every house on v2.1 ran v2.0.x, where the select stored its own state.
- **`single_config_entry`.** The manifest declares it: "Add integration" runs only while there is no entry (a fresh install), and windows are added with "Add window".

## Consequences

- The live house must be consolidated on v2.0.x before it installs v2.1; v2.1 then migrates it at its first start with every unique_id, entity_id, name, area, device, Mode and hold, and every resolved setting unchanged (`tests/test_upgrade_2_1.py`, on the house as v2.0 consolidated it: `tests/fixtures/consolidated_v2_0`).
- The house replay runs through that path (a 2.1 house migrated to 3.1) and matches the goldens byte for byte.
- The 60 switch alias entities of the live house are removed; no automation, script or dashboard references them (`tests/fixtures/house_snapshot/consumers.json`).
- The disabled "SE" window entries stay as they are; they can be deleted.
- Mutations M130 to M140 guard the migration, the nag, the record and the creation-time overrides; M51, M71 and M100 to M103 are retired with the code they guarded.

## Alternatives considered

- **Keep the consolidation in v2.1.** Rejected: it needs the 1.x migrations, the lift from switch states and a resolve of window entries; that is most of the legacy path P8 removes.
- **Minor bump to 2.2.** Rejected: v2.0.x would load the house and fail every window.
- **Store the name only as the subentry title.** Rejected: the live house has a window whose title and name differ; its device would be renamed.
- **Adopt new windows at setup, as v2.0 did.** Rejected: it writes to the subentry during setup and needs the "not adopted yet" state the record no longer has.
