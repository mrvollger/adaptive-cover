# ADR 0005: Drop pandas, numpy and pytz

- **Status:** Accepted
- **Date:** 2026-09-28
- **Delivered in:** P2 (v1.15.x)
- **Source:** [`docs/refactor_plan.md`](../refactor_plan.md), "P2", "Backend layout"; [`docs/refactor_baseline_review.md`](../refactor_baseline_review.md), baseline "Dependencies" and item 13; goal G4

## Context

- `manifest.json` requires `astral` and `pandas`. `numpy` and `pytz` are imported but not declared; they arrive only as transitive dependencies.
- pandas builds the solar table for a day (`sun.py`, `calculation.py`): one point every 5 minutes, and a nearest-point lookup. `helpers.py` uses it to parse durations. 6 test files also import it.
- numpy does scalar trigonometry, `interp` and `clip` in the engine and the adapters. None of it is vectorized work that needs numpy.
- pytz supplies time zones and UTC in `coordinator.py`. HA's `dt_util` already does this.
- The same code calls the wall clock directly: 19 `now()` / `utcnow()` calls outside `engine/`, and 1,025 `utcnow()` DeprecationWarnings per test run (`calculation.py`).

## Decision

- **Remove pandas.** A UTC 5-minute stepper builds the day: 289 points (the end is inclusive), and 277 or 301 points on DST days. `bisect` replaces the nearest-point lookup.
- **Replace numpy** with `math`. Wrap values in `float()`. A small interpolation helper (about 10 lines) replaces `np.interp`.
- **Replace pytz** with `homeassistant.util.dt` (`dt_util`).
- **Add a `Clock` protocol.** No `now()` or `utcnow()` calls remain outside `runtime/clock.py`.
- SunData's pandas types become `SolarDay`, with the same values. This is contract change C2 ([ADR 0004](0004-refactor-contract-v2.md)), pinned by an API test.
- Move the test fakes off pandas.
- `manifest.requirements` keeps only `astral`, or becomes `[]` if astral comes through HA's sun helper.
- Bring `engine/` to 0 pyright-strict errors in the same phase.

## Consequences

- A lighter install on HA, and no undeclared imports.
- Time becomes an injected input everywhere, which removes the autouse wall-clock mock from the tests and the DeprecationWarnings from the run.
- The replacements must reproduce numpy's float results exactly. The goldens and the house replay must stay byte-identical; any diff needs a ledger entry.
- A test pins the DST point counts (277 and 301).
- Mutations M36 and M37 (interpolation) are re-anchored onto the new helper in the same PR.
- `SolarDay` replaces a public SunData type. Callers inside the integration change in the same phase; the ledger records C2.
