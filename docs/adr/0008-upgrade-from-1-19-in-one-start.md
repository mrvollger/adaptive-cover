# ADR 0008: v2.1 upgrades a v1.19.x house in one start

- **Status:** Proposed (owner decision 2026-09-30; the owner accepts it at merge)
- **Date:** 2026-09-30
- **Delivered in:** v2.1.0
- **Amends:** [ADR 0007](0007-house-only-in-v2-1.md) ("No consolidation in v2.1"; the `consolidate_first` nag now covers only what the upgrade cannot take). The rest of ADR 0007 stands, and so do [ADR 0006](0006-window-subentries-in-v2.md)'s move order and snapshot.
- **Source:** owner decision 2026-09-30 ("one release, one restart"); [`docs/refactor_plan.md`](../refactor_plan.md), "Migration of the live house"; Home Assistant 2026.8.0 and 2026.9.4 (`config_entries.py`, `helpers/device_registry.py`, `helpers/entity_registry.py`)

## Context

ADR 0007 made v2.1 refuse a house that still has window entries: the owner had to install v2.0.x, fix its "Move your windows into the house" repair, then update to v2.1. The live house runs v1.19.x (15 window entries at 1.5, the hub at 1.5 holding the lifted layers). v1.20, v1.21 and v2.0 were never released to it. The owner decided on 2026-09-30 to go from v1.19.x to v2.1 in one release and one restart, with no click.

Two facts shape the move:

- **v1.19.x does not act on the layers.** Its runtime reads each window's flat options and its switches (Climate Mode, Outside Temperature, Lux, Irradiance, Manual Override); the layers are a shadow, compared at setup (the `settings_differ` repair). An edit made in v1.19.x (options form, `change_settings`) writes only the flat option, so a window's stored overrides can disagree with what it acts on.
- **v2.1 has no window-entry runtime and no v2.0 consolidation code** (P8 removed `consolidate.py`, `repairs.py`, `migration.py`, `shadow.py`). Only the parts the move needs come back, as an upgrade step with no UI.

## Decision

- **The house's migration runs the whole upgrade** (`consolidate.async_upgrade_house`, from `upgrade.async_migrate` when the house is below 3.x and enabled window entries exist; the live house, or a consolidation v2.0.x stopped part way). Each phase is logged at INFO:
  1. **1.x schema.** Window entries and the hub are brought to 1.5 with the steps v1.19.x runs itself (1.3 fallbacks and the cover's registry id as unique_id; the lift of the windows into the hub's layers, reading the switch states, when the hub holds none; 1.5 hidden aliases). Entries older than 1.2 stop the upgrade (install v1.19.x first).
  2. **Plan** (nothing written). Each window's record, what it acts on in v1.19.x (flat options and switch states, `read_toggles`) and what the record resolves to under the house layers at the window's area. A window whose stored overrides no longer give what it acts on is **adopted again** (`settings.shadow.adopt`): it keeps acting on the values it acts on today, and the notification names it. A window with several covers, a house without layers, or a window that still resolves other values stops the upgrade.
  3. **Snapshot** `.storage/adaptive_cover.v1_snapshot` (entries, entity and device rows, override store), written once.
  4. **Move**, per window: add the subentry (the 3.1 record; the window key is the old entry_id), move the entity rows to the house and the subentry, then the device (with `via_device_id` = the house device). The subentry is written in the 3.1 shape directly, so phase 5 reads it through the v2.1 read path.
  5. **Verify**, before anything is removed: every row exists and sits on the house and its subentry, nothing is left on the window entry, the device hangs off the house device, and `layers.effective_settings` of the subentry equals the planned values and provenance.
  6. **Commit**: the house becomes 2.1, the window entries are removed (last), then migration 2.1 -> 3.1 (ADR 0007) runs unchanged.
- **No version changes and nothing is removed before phase 5 passes.** If a phase fails, the upgrade undoes its moves (rows back on their entries, devices back, subentries removed), so v1.19.x finds the house as it left it, and raises the non-fixable `upgrade_stopped` repair with the reason. If the undo cannot restore a row (Home Assistant removed it), the repair is `upgrade_stopped_restore_backup`: restore the backup taken before the update. The window entries do not set up in v2.1 (their setup returns False quietly; the house's repair explains a stop).
- **A crash resumes.** A restart part way undoes nothing: the next start runs the upgrade again, and phases 4-6 skip what is done (the subentry exists, rows and devices moved, entries removed). The snapshot keeps its first copy.
- **A notification** (`persistent_notification`, id `adaptive_cover_upgraded`) says the windows moved into one house entry, that nothing changed, where the snapshot is, which windows were adopted again, and which disabled entries were left.
- **ADR 0007's nag stays** for what the upgrade cannot take: enabled window entries next to a house that is 3.x already (an old entry enabled again), or with no house entry. Those entries fail with `consolidate_first`; nothing is written.

## Consequences

- The live house goes from v1.19.x to v2.1 in one restart: every entity_id, unique_id, entity and device registry id, name, area and device, each Mode and running hold, and each window's resolved settings and provenance unchanged; the 60 switch alias rows removed (P8). `tests/test_upgrade_from_1_19.py` pins it on the live house as v1.19.x holds it (`tests/v1_19_house.py`, derived from `tests/fixtures/consolidated_v2_0`), with crash injection, a failed verification and a lost row.
- The house replay goldens run through this path (a 1.5 hub and window entry, the switches restoring their live states) byte for byte; `test_house_replay_through_v2_0` keeps the v2.0.x path replayed on one date.
- A window edited in v1.19.x keeps the edit (it is adopted again, not reverted to the layered value it disagreed with).
- The code that moves windows (the move order, the resumable checks, the snapshot, the switch-state reader) is back in v2.1 in `consolidate.py`, without the fix flow, the dry-run form or the window-entry runtime.
- Mutations M150-M162 guard the orchestration (verification, the move order, the version bump, the undo, the re-adoption, the switch states, resume, the snapshot, the notification, the lift, the oldest version). M130 is re-anchored.

## Alternatives considered

- **Keep ADR 0007 (install v2.0.x first).** Rejected by the owner: two releases, two restarts and a click.
- **Act on the stored layers for a window that disagrees (what the v1.20 flip did).** Rejected: the window would silently act on other values than it does today; "nothing changed" is the promise.
- **Stop the upgrade on any disagreement.** Rejected: v1.19.x writes every edit that way, so most houses would never upgrade.
- **Bump the house to 2.x before the first move (v2.0.x's order).** Rejected: a stopped upgrade would leave a house v1.19.x refuses and v2.1 cannot finish; the house stays 1.x until the moves are verified.
- **Write v2.0-shape subentries, then let migration 3.1 rewrite them.** Rejected: the verification could not read them through the v2.1 read path.
