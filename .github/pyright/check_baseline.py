#!/usr/bin/env python3
"""Run pyright and fail only on errors that are not in the committed baseline.

Pyright has no baseline mode, so this wrapper adds one. The baseline
(``baseline.json`` next to this file) counts errors per
``(file, rule, first line of the message)``. Line and column numbers are not
part of the key, so moving or reformatting code does not invalidate it.

- A key whose count goes UP fails the run and prints the new errors.
- A key whose count goes DOWN only prints a note; shrink the baseline with
  ``--write`` so the fixed errors cannot come back unnoticed.
- Paths in ``ZERO_ERROR_PATHS`` get no baseline at all: any error there
  fails the run, and ``--write`` refuses to record one. They are the
  directories pyproject.toml lists under ``strict`` (P2: ``engine/``).

Pyright settings live in ``[tool.pyright]`` in pyproject.toml. Messages
depend on the pyright version and on the installed Home Assistant, so
regenerate the baseline after bumping either (``pixi run typecheck-baseline``).

Usage (from anywhere in the repo, inside the pixi env):

    python .github/pyright/check_baseline.py          # check
    python .github/pyright/check_baseline.py --write  # rewrite the baseline
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).resolve().with_name("baseline.json")
# Checked in strict mode (pyproject.toml [tool.pyright] strict) with no
# baseline: these must stay at zero errors.
ZERO_ERROR_PATHS = ("custom_components/adaptive_cover/engine/",)

Key = tuple[str, str, str]


def run_pyright() -> tuple[str, list[dict]]:
    """Run pyright on the configured include paths; return (version, errors)."""
    exe = shutil.which("pyright")
    if exe is None:
        sys.exit("pyright not found on PATH; run via `pixi run typecheck`.")
    proc = subprocess.run(
        [exe, "--outputjson"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    # Exit code 0 = clean, 1 = diagnostics reported; anything else is fatal.
    if proc.returncode not in (0, 1):
        sys.stderr.write(proc.stdout + proc.stderr)
        sys.exit(proc.returncode)
    report = json.loads(proc.stdout)
    errors = [d for d in report["generalDiagnostics"] if d["severity"] == "error"]
    return report.get("version", "unknown"), errors


def key_of(diag: dict) -> Key:
    """Position-independent identity of a diagnostic."""
    path = Path(diag["file"]).resolve()
    try:
        file = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        file = path.as_posix()
    message = diag["message"].strip().splitlines()[0].strip()
    return file, diag.get("rule", ""), message


def load_baseline() -> Counter[Key]:
    """Read the committed baseline (missing file = empty baseline)."""
    if not BASELINE.exists():
        return Counter()
    data = json.loads(BASELINE.read_text())
    return Counter(
        {(e["file"], e["rule"], e["message"]): e["count"] for e in data["errors"]}
    )


def write_baseline(version: str, counts: Counter[Key]) -> None:
    """Write the baseline sorted by file, rule, message for stable diffs."""
    entries = [
        {"file": f, "rule": r, "message": m, "count": n}
        for (f, r, m), n in sorted(counts.items())
    ]
    payload = {
        "pyright": version,
        "total": sum(counts.values()),
        "errors": entries,
    }
    BASELINE.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    """Check (default) or rewrite (--write) the pyright baseline."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write", action="store_true", help="rewrite the baseline from this run"
    )
    args = parser.parse_args()

    version, errors = run_pyright()
    current = Counter(key_of(d) for d in errors)

    zero_error = [d for d in errors if key_of(d)[0].startswith(ZERO_ERROR_PATHS)]
    if zero_error:
        print(
            f"FAIL: {len(zero_error)} pyright error(s) in a zero-error path "
            f"({', '.join(ZERO_ERROR_PATHS)}); these cannot be baselined:"
        )
        for diag in zero_error:
            file, rule, message = key_of(diag)
            line = diag["range"]["start"]["line"] + 1
            col = diag["range"]["start"]["character"] + 1
            rule_txt = f" ({rule})" if rule else ""
            print(f"  {file}:{line}:{col}: {message}{rule_txt}")
            print(f"::error file={file},line={line},col={col}::{message}{rule_txt}")
        return 1

    if args.write:
        write_baseline(version, current)
        rel = BASELINE.relative_to(REPO_ROOT)
        print(f"Wrote {rel}: {sum(current.values())} errors (pyright {version}).")
        return 0

    baseline = load_baseline()
    new_keys = {k: n - baseline[k] for k, n in current.items() if n > baseline[k]}
    fixed = sum(max(n - current[k], 0) for k, n in baseline.items())

    print(
        f"pyright {version}: {sum(current.values())} errors, "
        f"{sum(baseline.values())} in baseline."
    )
    if fixed:
        print(
            f"note: {fixed} baseline error(s) are fixed; shrink the baseline "
            "with `pixi run typecheck-baseline`."
        )
    if not new_keys:
        print("OK: no new pyright errors.")
        return 0

    print(f"FAIL: {sum(new_keys.values())} new pyright error(s):")
    for key, extra in sorted(new_keys.items()):
        file, rule, message = key
        rule_txt = f" ({rule})" if rule else ""
        print(
            f"\n{file}: {message}{rule_txt}\n"
            f"  {current[key]} now, {baseline[key]} in baseline "
            f"(+{extra}); occurrences:"
        )
        for diag in errors:
            if key_of(diag) != key:
                continue
            line = diag["range"]["start"]["line"] + 1
            col = diag["range"]["start"]["character"] + 1
            print(f"  {file}:{line}:{col}")
            # GitHub annotation so the error shows on the PR diff.
            print(f"::error file={file},line={line},col={col}::{message}{rule_txt}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
