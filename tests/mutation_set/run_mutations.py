#!/usr/bin/env python3
"""Mutation kill-matrix runner: apply -> pytest tiers -> revert, per patch.

For each mutation patch in this directory (see manifest.json), the runner
applies the patch with ``git apply``, runs each configured pytest tier,
records caught (any test failed) / missed per tier, reverse-applies the
patch, and writes a JSON report. The kill-rate is thereby a reproducible
number, not an anecdote.

Safety:
- refuses to start if the working tree already has modifications to any
  mutation target file (it would corrupt apply/revert);
- NEVER leaves a mutation applied on exit: revert runs in ``finally`` and
  a failed revert aborts the whole run loudly;
- each pytest run has a hard timeout (a mutation that deadlocks the suite
  counts as caught, flagged with "timeout": true).

Usage (from the repo root):

    python tests/mutation_set/run_mutations.py                    # all, all tiers
    python tests/mutation_set/run_mutations.py --mutations M01,M15
    python tests/mutation_set/run_mutations.py --tiers simulation
    python tests/mutation_set/run_mutations.py --report /tmp/report.json
    python tests/mutation_set/run_mutations.py --pytest-args "-x -q"

Tiers (pytest target paths):
    simulation        tests/simulation
    characterization  tests/characterization
    engine            tests/engine
    entity            root-level tests/ (everything else)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

MUTATION_DIR = Path(__file__).resolve().parent
REPO_ROOT = MUTATION_DIR.parents[1]

TIERS: dict[str, list[str]] = {
    "simulation": ["tests/simulation"],
    "characterization": ["tests/characterization"],
    "engine": ["tests/engine"],
    "entity": [
        "tests",
        "--ignore=tests/simulation",
        "--ignore=tests/characterization",
        "--ignore=tests/engine",
    ],
}
DEFAULT_PYTEST_ARGS = ["-q", "-x", "-p", "no:cacheprovider"]


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
        check=check,
    )


def _tree_clean_for(files: set[str]) -> list[str]:
    """Return the target files that already have working-tree modifications."""
    out = _git("status", "--porcelain", "--", *sorted(files)).stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def _run_tier(paths: list[str], pytest_args: list[str], timeout: int) -> dict:
    cmd = [sys.executable, "-m", "pytest", *paths, *pytest_args]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout
        )
        exit_code: int | None = proc.returncode
        timed_out = False
        tail = "\n".join(proc.stdout.splitlines()[-3:])
    except subprocess.TimeoutExpired:
        exit_code = None
        timed_out = True
        tail = f"TIMEOUT after {timeout}s"
    return {
        # timeout counts as caught: the mutation visibly broke the suite
        "caught": timed_out or exit_code != 0,
        "exit_code": exit_code,
        "timeout": timed_out,
        "seconds": round(time.monotonic() - started, 1),
        "tail": tail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mutations",
        help="comma-separated mutation ids to run (default: all in manifest)",
    )
    parser.add_argument(
        "--tiers",
        help=f"comma-separated tiers to run (default: all of {list(TIERS)})",
    )
    parser.add_argument(
        "--report",
        default=str(MUTATION_DIR / "mutation_report.json"),
        help="path for the JSON kill-matrix report",
    )
    parser.add_argument(
        "--pytest-args",
        default=" ".join(DEFAULT_PYTEST_ARGS),
        help="arguments passed to every pytest run (quoted string)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="hard per-tier timeout in seconds (default 1800)",
    )
    args = parser.parse_args()

    manifest = json.loads((MUTATION_DIR / "manifest.json").read_text())
    if args.mutations:
        wanted = {m.strip() for m in args.mutations.split(",")}
        unknown = wanted - {entry["id"] for entry in manifest}
        if unknown:
            parser.error(f"unknown mutation ids: {sorted(unknown)}")
        manifest = [entry for entry in manifest if entry["id"] in wanted]

    tier_names = list(TIERS)
    if args.tiers:
        tier_names = [t.strip() for t in args.tiers.split(",")]
        unknown = set(tier_names) - set(TIERS)
        if unknown:
            parser.error(f"unknown tiers: {sorted(unknown)}")
    pytest_args = shlex.split(args.pytest_args)

    # Refuse to run over a dirty target: apply/revert would corrupt it.
    targets = {entry["file"] for entry in manifest}
    if dirty := _tree_clean_for(targets):
        print(
            "REFUSING to run: working tree already has modifications to "
            f"mutation target file(s): {dirty}", file=sys.stderr,
        )
        return 2

    results: dict[str, dict] = {}
    for entry in manifest:
        mutation_id = entry["id"]
        patch = MUTATION_DIR / entry["patch"]
        print(f"=== {mutation_id} {entry['function']}: {entry['description']}")
        check = _git("apply", "--check", str(patch), check=False)
        if check.returncode != 0:
            print(f"  patch does not apply (stale?): {check.stderr.strip()}")
            results[mutation_id] = {**entry, "error": "patch-does-not-apply"}
            continue
        _git("apply", str(patch))
        tier_results: dict[str, dict] = {}
        try:
            for tier in tier_names:
                tier_results[tier] = _run_tier(
                    TIERS[tier], pytest_args, args.timeout
                )
                verdict = "CAUGHT" if tier_results[tier]["caught"] else "missed"
                print(
                    f"  {tier}: {verdict} "
                    f"({tier_results[tier]['seconds']}s)"
                )
        finally:
            revert = _git("apply", "-R", str(patch), check=False)
            if revert.returncode != 0:
                print(
                    f"FATAL: could not revert {mutation_id}; the working "
                    f"tree still contains the mutation!\n{revert.stderr}",
                    file=sys.stderr,
                )
                _write_report(args.report, tier_names, results, aborted=True)
                raise SystemExit(3)
        results[mutation_id] = {
            **entry,
            "tiers": tier_results,
            "caught_by": [t for t, r in tier_results.items() if r["caught"]],
            "missed_by": [
                t for t, r in tier_results.items() if not r["caught"]
            ],
        }

    _write_report(args.report, tier_names, results, aborted=False)
    ran = [r for r in results.values() if "tiers" in r]
    killed = [r for r in ran if r["caught_by"]]
    survivors = sorted(r["id"] for r in ran if not r["caught_by"])
    print(
        f"\nKill rate: {len(killed)}/{len(ran)}"
        + (f"  SURVIVORS: {survivors}" if survivors else "")
    )
    print(f"Report: {args.report}")
    return 1 if survivors else 0


def _write_report(
    path: str, tiers: list[str], results: dict, *, aborted: bool
) -> None:
    report = {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "tiers": tiers,
        "aborted": aborted,
        "results": results,
        "summary": {
            "run": len([r for r in results.values() if "tiers" in r]),
            "killed": len(
                [r for r in results.values() if r.get("caught_by")]
            ),
            "survivors": sorted(
                r["id"]
                for r in results.values()
                if "tiers" in r and not r["caught_by"]
            ),
        },
    }
    Path(path).write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    sys.exit(main())
