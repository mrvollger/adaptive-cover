# ADR 0003: Settings precedence and the one-time vs recurring rule

- **Status:** Accepted
- **Date:** 2026-09-28
- **Delivered in:** P5 (v1.18.0 shadow release, v1.18.1 flip); the room and floor sheets ship in P6
- **Source:** [`docs/refactor_plan.md`](../refactor_plan.md), "One-time vs recurring settings", "Config model", "Built-in defaults", "P5"; owner decisions 2 and 6

## Context

- Today each entry has one flat settings dictionary: `data` merged with `options`.
- The same recurring values are copied into 15 entries. The code has 3 hand-written schema copies and 5 default copies.
- The owner groups windows by HA **floors and areas**, not by custom zones (decision 6).
- The owner wants a 2-hour manual-override duration for every window, with a per-room override (decision 2).
- Some settings change often (thresholds, override duration). Others are set once per window (azimuth, height). Today both kinds sit in the same wizard.

## Decision

**Precedence.** A window's effective value for a key is the first value found in this order:

1. window override,
2. area,
3. floor,
4. house,
5. spec default.

- `settings/resolve.py` implements this as a pure function. It returns a frozen `WindowConfig` plus the provenance of each key. The card uses the provenance to show "inherited from ...".
- The area and floor are read live from the window device. That device's area is copied from the physical cover.
- Windows read the house's *stored* options, not its runtime state, so startup order does not matter.

**One-time vs recurring rule.** A setting you might change more than once lives at house level. A room or floor may override it. A window override exists only where the plan's "Narrower override" column allows it. One-time settings live only in the window setup form.

- One-time (window only): the cover, azimuth, FOV, height, distance, awning and slat geometry, overhang, elevation limits, blind spot, min/max position, inverse, interpolation, transparent blind, privacy opt-in, "ignore climate".
- Recurring with a window override: eye height, seat distance, default position, sunset position.
- Recurring without a window override: everything else (thresholds, sensors, override duration, start and end times, privacy timing, quiet hours, deltas).
- The full table is in [`docs/refactor_plan.md`](../refactor_plan.md#one-time-vs-recurring-settings).

**Enforcement.**

- Each spec `Opt` has `scope` and `overridable_at`. A spec test checks the table.
- Every recurring key can be reached from a house, floor or room sheet.
- The window form shows recurring keys only inside its collapsed *Exceptions* section.

**Moving the live house.** A lift migration computes the layers. The house gets the most common value. A floor or area gets any value that all its windows share. Anything left over stays as a window override. Before any default changes (P3), the migration writes every value an entry currently gets from code defaults into its options, so new defaults cannot move it.

## Consequences

- A threshold or override duration changes in one place for the whole house.
- Provenance explains every effective value in the UI.
- A precedence bug would silently change behavior. The guards:
  - `resolve(w) == legacy_flat(w)` for all 15 snapshot windows;
  - a property test: random options, then lift, then resolve, gives back the same options;
  - mutations M45 (area and floor precedence swapped) and M46 (the lift drops an outlier);
  - v1.18.0 is a shadow release: the runtime still acts on the legacy keys, raises a repair issue for any key that differs, and soaks for 7 days with no diff before the flip.
- Contract change C6 (options-over-data becomes layered `resolve()`) needs a ledger entry and re-anchors M39 ([ADR 0004](0004-refactor-contract-v2.md)).
- Window forms get shorter: a new window needs only a cover and an azimuth (plus the height for a blind).
