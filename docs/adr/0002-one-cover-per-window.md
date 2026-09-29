# ADR 0002: One cover per window

- **Status:** Accepted
- **Date:** 2026-09-28
- **Delivered in:** P3 (v1.16.0); the `group` dual-write is removed in P8
- **Source:** [`docs/refactor_plan.md`](../refactor_plan.md), "Summary", "P3", "P4"; goal G3

## Context

- Today an entry stores its covers as a list (`group`, `CONF_ENTITIES`). One entry can drive several covers, and the same cover can be added to two entries.
- To handle several covers per entry, the coordinator keeps per-cover dictionaries, a `manual_list` and a reset-button loop. This is a large part of its complexity.
- Two entries that drive the same cover fight each other, and nothing stops a user from creating that setup.
- The geometry (azimuth, height, overhang) belongs to one opening. Covers on different openings need different geometry anyway.
- The live house has 3 disabled multi-cover "SE" entries. They make no decisions and are leftovers.

## Decision

- **One window = exactly one cover.** A cover belongs to at most one window.
- The cover selector uses `multiple=False`. The `add_entry` service takes `cover`.
- In the subentry model, the window's `unique_id` is the cover's entity-registry id, so adding a duplicate cover aborts.
- The window's name, type and area are read from the cover.
- Migration 1.3 (P3):
  - writes `cover_entity_id`,
  - still writes `group: [cover]`, so a downgrade keeps working (removed in P8),
  - sets the entry unique_id to the cover's registry id.
- An entry with more than one cover gets a fixable "split" repair issue.
- Several covers on one physical opening become several windows. *Copy from* makes the second one a one-screen setup. Grouping for control uses HA areas and floors (Mode, `hold`, Return to auto), not multi-cover entries.

## Consequences

- The P4 coordinator split builds every component for a single cover. The per-cover dictionaries, `manual_list` and the button loop go away.
- The override store collapses from a per-cover dictionary to one record per `window_key`.
- Conflicting control of one cover by two windows becomes impossible.
- Users with a multi-cover entry must split it through the repair flow.
- `group` and `cover_entity_id` are both written until P8. That is the price of a safe rollback.
- Mutation M44 (a duplicate cover is accepted) pins the guard. SimHouse `covers=[a, b]` creates two windows.

## Alternatives considered

- **Keep multi-cover entries.** Rejected: it keeps the per-cover state machinery in the coordinator and the duplicate-cover conflict.
