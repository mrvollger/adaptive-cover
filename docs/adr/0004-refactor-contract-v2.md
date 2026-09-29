# ADR 0004: Refactor contract v2, behavior-tier ledger and mutation gate

- **Status:** Accepted
- **Date:** 2026-09-28
- **Delivered in:** P0 (v1.14.0); applies to every release after that
- **Source:** [`docs/refactor_plan.md`](../refactor_plan.md), "Phases" (release gate), "Refactor contract", "Testability and maintainability"; [`docs/refactor_baseline_review.md`](../refactor_baseline_review.md), items 8 and 9

## Context

- The refactor replaces the 1,937-line coordinator, the config model and most of the entity surface. The house must behave the same the whole time.
- Contract v1 is the "Refactor Contract seams" in `tests/refactor_roadmap.json` (`behavior_tier`): `evaluate()` and the engine models, the config surface, the entity surface, the service surface and SunData's public API. It was written for the engine extraction, not for a new config model.
- On 2026-09-28 the net had gaps: CI failed 49 of 49 runs, the mutation baseline was stale and ran serially in about 20 minutes outside CI, and nothing stopped a behavior test from disappearing silently.

## Decision

**Frozen (contract v2).** These do not change without a ledger entry:

- `evaluate()` and the engine models;
- the goldens, the climate truth table and the house replay;
- what the SimHouse scenarios assert;
- outbound cover calls: target, value and timing;
- manual-override semantics;
- the unique_ids and entity_ids of kept entities, and the hub entity_ids;
- the Position sensor attributes (new ones may be added);
- service names and response schemas (input fields may be added).

**Changed on purpose.** Each planned change (C1 to C8 in the plan) is a ledger entry that names the tests it retires, their replacements and the mutations it re-targets.

**Artifacts.**

- `tests/contract/behavior_tier_ids.txt`: the ids of the behavior-tier tests.
- `tests/contract/ledger.md`: one entry per deliberate contract change or explained output diff.
- `tests/contract/check_behavior_tier.py`: fails when an id leaves `behavior_tier_ids.txt` without a ledger entry.
- `tests/mutation_set/`: one patch per mutation, `make_patches.py --check`, and `run_mutations.py --jobs N` (parallel worktrees).
- `tests/replay/`: house-replay goldens (the real configs on DST start and end, both equinoxes and both solstices) that pin the outbound command timeline.
- `refactor_roadmap.json` gets a `contract_v2` block with the seams evaluate, resolve, entity surface v2, services and SolarDay.

**Release gate.** Every release passes all of these:

- CI is green.
- The behavior tier passes.
- The mutation kill rate is 100%, and the simulation tier alone kills at least the P0 baseline set.
- `make_patches.py --check` passes.
- The goldens, the truth table and the house replay are byte-identical, or the PR carries a ledger entry that explains the diff.
- `behavior_tier_ids.txt` has no silent removals.

**Working rules.**

- A PR that moves code re-anchors its mutations in the same PR. The reviewer confirms that no mutation description changed.
- Each fixed defect gets a `test_regression_<slug>` and its own commit.
- Tests reach the system only through WindowHandle and public APIs, so a backend change does not touch them.
- Each new behavior adds a mutation. The kill bar stays at 100%.
- The deletion drill (remove the implementation-coupled tests; the behavior tier must still kill every mutation) runs once per phase.

## Consequences

- Every behavior change is visible in review as a ledger entry or a golden diff. None can slip in as a side effect.
- Backend rewrites (P4 split, P7 subentries) do not need test rewrites, because the tests use public seams.
- Each PR has extra upkeep: re-anchored patches, ledger entries and new mutations.
- Mutation runs cost CI time. The target is 6 minutes or less for the full matrix with `--jobs`, on PRs that touch the engine, settings or runtime, and nightly on main.
- A patch that no longer applies fails CI, so the mutation set cannot rot silently again.
