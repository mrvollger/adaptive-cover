# Contributing to Adaptive Cover

This repository is [mrvollger/adaptive-cover](https://github.com/mrvollger/adaptive-cover), a fork of [basbruss/adaptive-cover](https://github.com/basbruss/adaptive-cover). Report bugs and request features in [GitHub issues](https://github.com/mrvollger/adaptive-cover/issues). Propose changes as a pull request against `main`.

Read these first:

- [`agents.md`](agents.md): how the integration works today (architecture, data flow, manual-override rules).
- [`docs/refactor_plan.md`](docs/refactor_plan.md): where the code is going, phase by phase.
- [`docs/adr/`](docs/adr/README.md): the design decisions that the plan depends on.

## Contents

- [Development setup](#development-setup)
- [Project rules](#project-rules)
- [Test tiers](#test-tiers)
- [Regression tests](#regression-tests)
- [Adding a simulation scenario](#adding-a-simulation-scenario)
- [Adding a mutation](#adding-a-mutation)
- [The behavior-tier ledger](#the-behavior-tier-ledger)
- [Before you open a pull request](#before-you-open-a-pull-request)
- [Releases](#releases)
- [English-only policy](#english-only-policy)
- [License](#license)

## Development setup

The Python environment is managed with [pixi](https://pixi.sh). `pixi.toml` and `pixi.lock` pin Python, Home Assistant and the test tools.

```bash
pixi install          # create the environment from pixi.lock
pixi run test         # the full pytest suite, in parallel (pytest -n auto)
pixi run lint         # ruff lint and format checks
pixi run typecheck    # pyright (standard mode, no baseline; strict on engine/, runtime/ and the pure settings/ modules)
pixi run mutations    # the mutation kill matrix (tests/mutation_set/)
```

- Run one tier or one file with `pixi run pytest <path>`, for example `pixi run pytest tests/simulation -q`.
- Add a dependency with `pixi add <package>`. Do not `pip install` into the pixi environment.
- The minimum supported Home Assistant version is 2026.8. It is set in `hacs.json` and in the `pytest-homeassistant-custom-component` pin. Change both together.

### The Lovelace card

The card source is in [`card/`](card/) (TypeScript, Node). The built bundle is committed as `custom_components/adaptive_cover/www/adaptive-cover-card.js`, because HACS installs the integration directory as it is.

```bash
cd card
npm ci
npm test              # vitest
npm run typecheck     # tsc --noEmit
npm run lint          # eslint + prettier --check
npm run build         # writes card/dist/adaptive-cover-card.js
cp dist/adaptive-cover-card.js ../custom_components/adaptive_cover/www/
```

When you change the card source, commit the rebuilt bundle in the same PR.

### Trying a change in a real Home Assistant

Copy `custom_components/adaptive_cover/` into `/config/custom_components/` on a test instance and restart Home Assistant. See "Deploying Without HACS" in [`agents.md`](agents.md). Test on a spare instance or take a backup first.

## Project rules

- **The engine is pure.** `custom_components/adaptive_cover/engine/` has no `homeassistant` imports, no wall-clock reads and no entity access. `tests/engine/test_purity.py` enforces this. The engine is frozen during the refactor: the solar and glare algorithm does not change.
- **Time is an input.** Never call `datetime.now()` or `utcnow()` in logic. Pass the time in. Outside `runtime/clock.py` nothing reads the wall clock: code uses the coordinator's `clock`, and `tests/engine/test_purity.py` fails on any other `now()`, `utcnow()`, `today()` or `time.time()`. Tests freeze time with `freezer`, or inject a clock through `coordinator.default_clock`.
- **No new dependencies.** The manifest requires only `astral`. `tests/engine/test_purity.py` fails on pandas, numpy or pytz, and on any third-party import that Home Assistant does not provide (ADR 0005).
- **Tests use public surfaces.** New tests must not read `hass.data`, coordinator attributes or private attributes. Use entity states, registries, services and the SimHouse helpers (`house.eid(...)`, `house.sensor_attr(...)`).
- **Frozen behavior stays frozen.** The refactor contract ([ADR 0004](docs/adr/0004-refactor-contract-v2.md)) lists what must not change without a ledger entry: outbound cover calls, manual-override semantics, unique_ids and entity_ids, Position attributes, and service names and response schemas.
- **Commits explain why.** Write the reason in the commit message, not only the change. Use a feature branch for any non-trivial change.

## Test tiers

| Tier | Path | What it pins |
|---|---|---|
| Engine | `tests/engine/` | Pure `evaluate()` and geometry, including dense property sweeps. `test_purity.py` is a structural guard. |
| Runtime | `tests/runtime/` | The components split out of the coordinator (P4), called directly with fakes and no `hass` fixture. Implementation tier: later P4 steps may reshape them. `test_no_hass.py` keeps them free of Home Assistant. |
| Characterization | `tests/characterization/` | The climate truth table (`climate_truth_table.json`, 216 combinations), the golden day schedules (`goldens/*.txt`) and the outbound service calls (`test_service_calls.py`). |
| Simulation | `tests/simulation/` | Full-day replays of the real integration against fake shades, a real astral sun and a stepped frozen clock (SimHouse). |
| Entity surface | root `tests/test_*.py` | Config flow, Add window and Change window, the house options, services, entities, the hub, restore behavior and the v2.1 upgrade, through a real house entry (`tests/house_model.py` builds one with window subentries). |
| House replay | `tests/replay/` | The real house configs on 6 dates (DST start and end, both equinoxes, both solstices) with scripted weather and manual moves. Pins the outbound command timeline. |
| Contract | `tests/contract/` | The behavior-tier id list and the ledger check. See [the behavior-tier ledger](#the-behavior-tier-ledger). |
| Mutation | `tests/mutation_set/` | Not a test tier. It checks that the tiers above catch deliberate bugs. See [adding a mutation](#adding-a-mutation). |
| Card | `card/tests/` | vitest for the Lovelace card. |

### Changing a pinned output

The truth table, the goldens and the house replay are review artifacts. If a change is **not** meant to change behavior, they must stay byte-identical. If it is meant to change behavior:

1. Regenerate the artifact.
   - Truth table: `PYTHONPATH=. pixi run python tests/characterization/generate_truth_table.py`
   - Goldens: `UPDATE_GOLDENS=1 pixi run pytest tests/characterization/test_golden_days.py -q`
   - House replay: follow the update instructions in `tests/replay/`.
   - Settings surfaces (`tests/contract/spec_parity.json`): `PYTHONPATH=. pixi run python tests/contract/generate_spec_parity.py`
2. Read the diff. Every changed line must be one you intended.
3. Commit the regenerated files with the code change, and add a ledger entry that explains the diff.

## Regression tests

- Every fixed defect gets a test named `test_regression_<slug>`, for example `test_regression_target_latch_tolerance`. The docstring says what broke, and names the commit or issue when there is one.
- Each defect fix is its own commit, so it can be reviewed and reverted alone.
- Put the test in the tier closest to the defect. Engine defects go in `tests/engine/test_regression_fixes.py`. Integration defects go in the matching root test file, or in `tests/test_regression_fixes.py`.
- A defect in coordinator-level behavior (gates, schedules, manual-override detection, end-of-day close) also gets a simulation scenario that pins the symptom as a user would see it (see `tests/simulation/test_symptoms.py` and `test_regressions.py`).

## Adding a simulation scenario

The full harness API is in [`tests/simulation/README.md`](tests/simulation/README.md). The short version:

1. Pick the file by topic, for example `test_manual_override_behavior.py`, `test_gates_and_windows.py` or `test_lifecycle.py`. The README's "File tour" helps.
2. Build the house with `SimHouse.create(hass, freezer, date=..., covers=[...], options={...})`. Each cover gets its own window (one cover per window), a subentry of one house entry. Add `climate={...}` for climate mode and `start_at="13:00"` for a mid-day start.
3. Drive time with `house.advance_to("HH:MM")`, and inputs with `house.user_moves(...)`, `house.set_temperature(...)`, `house.set_options(...)` or `house.restart(...)`.
4. Assert on what a person would observe: `house.auto_moves(...)`, `house.moves(...)`, `house.position(...)` and entity states through `house.eid(...)` / `house.sensor_attr(...)`. Never hard-code entity_ids.
5. End with `await house.teardown()`.

The harness README's example:

```python
from custom_components.adaptive_cover.const import CONF_END_TIME, CONF_RETURN_SUNSET

from .harness import SimHouse


async def test_my_scenario(hass, freezer):
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        covers=["cover.shade"],
        options={CONF_END_TIME: "20:00:00", CONF_RETURN_SUNSET: True},
    )
    await house.advance_to("14:00")
    await house.user_moves("cover.shade", 100, via="remote")  # or "dashboard"
    await house.advance_to("16:00")
    assert house.auto_moves("cover.shade", since="14:00") == []
    await house.teardown()
```

A scenario should fail when the behavior breaks. Before you commit it, break the code on purpose (or apply the matching mutation) and check that the scenario fails.

## Adding a mutation

A mutation is a small, deliberate bug. The mutation set proves that the test tiers catch real regressions. The kill bar is **100%**: a mutation that no test catches means a test is missing.

1. Add a `Mutation(...)` entry to `MUTATIONS` in [`tests/mutation_set/make_patches.py`](tests/mutation_set/make_patches.py):
   - `id`: the next free `M##`. The plan reserves M44 and M47 to M51 for specific phases (see [`docs/refactor_plan.md`](docs/refactor_plan.md)).
   - `slug`, `file` and `function`: where the bug goes.
   - `description`: one line that says what the bug does. Once merged, the description does not change.
   - `old` and `new`: an exact text replacement. `old` must occur exactly once in the current file.
2. Regenerate the patches and the manifest: `pixi run python tests/mutation_set/make_patches.py`.
3. Check that every committed patch is current and still applies: `pixi run python tests/mutation_set/make_patches.py --check`. CI runs this check, and a patch that no longer applies fails CI.
4. Run the new mutation: `pixi run python tests/mutation_set/run_mutations.py --mutations <id>`. It must be caught. Without `--jobs`, the runner applies patches in your working tree and refuses to start if a target file has uncommitted edits, so commit first.
5. If nothing catches it, add the missing test (a simulation scenario is best for coordinator behavior), then run the mutation again.

**When you move code** (for example in the P4 coordinator split), re-anchor the affected mutations in the same PR: update `old` and `new` to the new location, regenerate, and run `--check`. The description must not change; the reviewer checks this.

## The behavior-tier ledger

The behavior tier is the set of tests that reach the integration only through its public seams: `evaluate()`, the config surface, the entity surface and the service surface. These tests must survive the refactor unchanged. The files are in [`tests/contract/`](tests/contract/):

- `behavior_tier_ids.txt`: the ids of every behavior-tier test.
- `ledger.md`: one entry per deliberate change to the contract.
- `check_behavior_tier.py`: fails CI when an id disappears from `behavior_tier_ids.txt` without a ledger entry.

Rules:

- When you add a behavior-tier test, add its id to `behavior_tier_ids.txt`.
- When you remove or rename one, or when a golden, the truth table or the house replay changes, add a ledger entry in the same PR. The entry says:
  - what changed and why (cite the contract change, for example "C3", or the defect);
  - which tests it retires and which tests replace them;
  - which mutations it re-targets;
  - which pinned outputs changed, and why each diff is correct.

The rationale is in [ADR 0004](docs/adr/0004-refactor-contract-v2.md).

## Before you open a pull request

- [ ] `pixi run lint`, `pixi run typecheck` and `pixi run test` pass.
- [ ] The goldens, the truth table and the house replay are unchanged, or the PR has a ledger entry for each diff.
- [ ] Each fixed defect has a `test_regression_<slug>` and its own commit.
- [ ] If you changed the engine, settings or runtime code: `pixi run mutations` shows 100% killed, and `make_patches.py --check` passes.
- [ ] If you changed the card: vitest, typecheck and lint pass, and the rebuilt bundle is committed.
- [ ] If you changed `strings.json`: `translations/en.json` has the same change.
- [ ] If the change affects architecture or the dev workflow: `agents.md` is updated. A new design decision gets an ADR.

CI must be green before a PR merges.

## Releases

A release is a tag push. HACS shows an update when a new GitHub release exists.

1. On `main`, set `version` in `custom_components/adaptive_cover/manifest.json` to the new version (for example `1.14.0`) and commit.
2. Tag that commit and push the tag:

   ```bash
   git tag v1.14.0
   git push origin v1.14.0
   ```

3. The release workflow checks that the manifest version equals the tag, runs the checks and publishes the GitHub release. If the versions differ, the workflow fails and nothing is published.

Do not create releases by hand with `gh release create`. Version numbers follow the phases in [`docs/refactor_plan.md`](docs/refactor_plan.md). To roll back, downgrade in HACS.

## English-only policy

The integration is English-only by choice (since 2026-09-28). `strings.json` is the source text, and `translations/en.json` must match it; CI checks this. Do not add other translation files: nothing keeps them in sync, and Home Assistant falls back to English. The same applies to the card.

## License

The project is under the [MIT License](LICENSE). By contributing, you agree that your contributions are licensed under it. The card in `card/` keeps its own MIT [license file](card/LICENSE).
