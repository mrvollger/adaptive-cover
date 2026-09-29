# Contract tooling

This directory and `tests/mutation_set/` hold the checks that keep the
refactor honest (`docs/refactor_plan.md`, "Refactor contract"). All tools
are plain Python (stdlib only) and run from the repo root.

## The behavior tier and the ledger

The behavior tier is the set of tests that touch the integration only
through the contract seams (`tests/refactor_roadmap.json`,
`behavior_tier`). `RULES` in `check_behavior_tier.py` encode that
definition as node-id patterns. `behavior_tier_ids.txt` records the node
ids that the rules select today.

| File | Purpose |
|---|---|
| `check_behavior_tier.py` | Selects the tier, compares it with the record, reads the ledger |
| `behavior_tier_ids.txt` | Recorded tier ids. Generated, do not edit by hand |
| `ledger.md` | One entry per intentional contract change |

```bash
python tests/contract/check_behavior_tier.py                  # check
python tests/contract/check_behavior_tier.py --base origin/main
python tests/contract/check_behavior_tier.py --update         # record ids
```

The check:
- fails (exit 1) if a recorded id is gone and no ledger entry names it;
- reports ids that are gone but ledgered;
- reports new ids (not an error; run `--update` to record them);
- reports test files that no rule classifies (not an error; add a rule).

In CI, use `--base <target branch>`. Then a PR that deletes a test and
also deletes its line from `behavior_tier_ids.txt` still fails.

### When you add tests

Run `--update` and commit `behavior_tier_ids.txt` with the tests. If the
check says a file is unclassified, add a rule to `RULES` first:
`BEHAVIOR` if the test uses only contract seams (engine `evaluate()`, the
config surface, entities through `hass.states` and services, outbound
cover calls, SunData's public API), else `IMPLEMENTATION`.

### When you remove, rename or re-parametrize a behavior test

1. Add an entry at the end of `ledger.md` (the format is in the file).
   Name every retired id, the replacement tests, the mutations you
   re-targeted and the reason.
2. Run `check_behavior_tier.py --update`.
3. Commit the test change, the ledger entry and the ids file together.

`--update` refuses while an unledgered removal exists. `--force` skips
that guard. Use it only to re-seed the record in bulk, for example after
merging branches that predate the ledger.

## Settings-surface parity

`spec_parity.json` snapshots every settings surface: the setup wizard, the
options form, the `change_settings` and `add_entry` service schemas (plus
the options `add_entry` gives an entry without `copy_from`), the service
fields in `services.yaml`, and the number entities. For each option key it
records the kind, default, min, max, step and unit, and where the key
appears (surface, form or section, cover type, climate mode, HA
temperature unit). `generate_spec_parity.py` builds it by driving the code
that serves each surface; `test_spec_parity.py` fails when the code and the
snapshot disagree.

```bash
PYTHONPATH=. pixi run python tests/contract/generate_spec_parity.py
```

Regenerate only for an intended change. The JSON diff is the review
artifact, and it needs a ledger entry.

## Mutation set

`tests/mutation_set/make_patches.py` defines the mutations (M01 to M58; M44 and M47 to M51 are reserved by the plan, M53 is retired).
Each is an exact text replacement in production code. The script writes
one `M##_slug.patch` per mutation plus `manifest.json`.

```bash
python tests/mutation_set/make_patches.py          # regenerate patches
python tests/mutation_set/make_patches.py --check  # CI gate, writes nothing
```

`--check` exits 1 and lists each problem when a mutation no longer applies
(its target text is not found exactly once) or a committed patch file or
`manifest.json` differs from a fresh regeneration. A PR that moves
mutated code re-anchors the mutation in `make_patches.py` and regenerates
the patches in the same PR.

`tests/mutation_set/run_mutations.py` measures the kill matrix. It copies a
snapshot of the working tree (tracked and untracked files, not
`node_modules`, `card`, `notebooks`, `images`) into a temp dir per
mutation, applies the patch there, runs the pytest tiers and deletes the
copy. Your checkout is never changed.

| Flag | Meaning |
|---|---|
| `--jobs N` | Run N mutations at once (default 1; 0 = one per CPU) |
| `--xdist auto\|off\|N` | pytest-xdist per tier run. `auto`: `-n auto` with `--jobs 1`, else `-n cpu//jobs` when that is 2 or more |
| `--mutations M01,M15` | Run only these mutations |
| `--tiers simulation,engine` | Run only these tiers |
| `--report PATH` | JSON report (default `tests/mutation_set/mutation_report.json`) |
| `--schedule-from PATH` | Earlier report used to start the longest mutations first (default: `--report` if it exists) |
| `--no-control` | Skip the control run of the unmutated snapshot |
| `--timeout S` | Hard limit per tier run (default 1800 s) |

```bash
python tests/mutation_set/run_mutations.py --jobs 16 --report /tmp/mutations.json
```

The report keeps the old format (`results`, `summary`) and adds `timing`
(wall time, jobs, xdist per tier), a total `seconds` per mutation, and
`control`. If the control run fails a tier, the runner exits 4, because
kills in that tier mean nothing. Other exit codes: 0 all killed, 1
survivors or patches that do not apply, 130 interrupted.

`baseline_report.json` is the recorded kill-matrix baseline. The runner
never writes it.

The tooling tests (`tests/contract/test_*.py`) are excluded from the
runner's `entity` tier and from the behavior tier.
