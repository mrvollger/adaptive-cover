#!/usr/bin/env python3
"""Mutation kill-matrix runner: copy -> apply -> pytest tiers -> discard.

For each mutation patch in this directory (see manifest.json), the runner
makes an isolated copy of the repo in a temp dir, applies the patch there
with ``git apply``, runs each configured pytest tier inside the copy,
records caught (any test failed) / missed per tier, deletes the copy, and
writes a JSON report. The kill-rate is thereby a reproducible number, not an
anecdote.

Isolation and safety:
- the caller's working tree is NEVER modified. At start the runner snapshots
  the working tree (tracked + untracked-not-ignored files, as ``git ls-files
  -co --exclude-standard`` lists them, minus the bulky non-Python dirs in
  COPY_EXCLUDE) into a private template dir; every mutation (and the control
  run) gets its own copy of that template. Uncommitted edits are therefore
  included, and you can keep editing while a run is in progress;
- every temp dir is removed on exit, including on Ctrl-C and errors;
- each pytest run has a hard timeout (a mutation that deadlocks the suite
  counts as caught, flagged with "timeout": true); timed-out runs are killed
  with their whole process group (xdist workers included);
- a CONTROL run of the unmutated snapshot runs alongside the mutations. If a
  tier fails without any mutation, its "kills" are meaningless, so the run
  reports it and exits 4 (skip with --no-control).

Parallelism:
- ``--jobs N`` runs N mutations at once, each in its own copy (default 1;
  0 = one per CPU).
- ``--xdist auto|off|N`` controls pytest-xdist inside each tier run.
  ``auto`` (default) uses ``-n auto`` when --jobs is 1, and splits the
  cores between jobs otherwise (``-n cpu//jobs``, or no xdist when that is
  below 2). Tiers too short to profit (characterization) never use xdist.
  If ``--pytest-args`` already has ``-n``, the runner adds nothing.
- Scheduling is longest-first, using per-mutation durations from a previous
  report (``--schedule-from``, default: the ``--report`` file if it exists);
  mutations without a recorded duration go first. Results are always
  reported in manifest order.

Usage (from the repo root):

    python tests/mutation_set/run_mutations.py                    # all, all tiers
    python tests/mutation_set/run_mutations.py --jobs 16          # parallel
    python tests/mutation_set/run_mutations.py --mutations M01,M15
    python tests/mutation_set/run_mutations.py --tiers simulation
    python tests/mutation_set/run_mutations.py --report /tmp/report.json
    python tests/mutation_set/run_mutations.py --pytest-args "-x -q"
    python tests/mutation_set/run_mutations.py --xdist off

Tiers (pytest target paths):
    simulation        tests/simulation
    characterization  tests/characterization
    engine            tests/engine
    entity            root-level tests/ (everything else except tests/contract)

Exit codes: 0 every mutation killed; 1 survivors or patches that no longer
apply; 2 bad arguments / snapshot failure; 4 the control run failed;
130 interrupted.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import contextlib
import datetime as dt
import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
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
        "--ignore=tests/contract",
    ],
}
# Whether a tier is long enough for pytest-xdist worker start-up to pay off
# (measured 2026-09-28: characterization is ~1 s serial, ~2 s under xdist).
TIER_XDIST: dict[str, bool] = {
    "simulation": True,
    "characterization": False,
    "engine": True,
    "entity": True,
}
DEFAULT_PYTEST_ARGS = ["-q", "-x", "-p", "no:cacheprovider"]

# Top-level paths never copied into the per-mutation sandboxes: large and
# irrelevant to pytest. Everything else git knows about is copied.
COPY_EXCLUDE = ("node_modules", "card", "notebooks", "images", ".claude")
SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache"}

CONTROL_ID = "CONTROL"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_print_lock = threading.Lock()
_active_procs: set[subprocess.Popen] = set()
_procs_lock = threading.Lock()
_stop = threading.Event()


def _say(text: str) -> None:
    with _print_lock:
        print(text, flush=True)


def _git(
    *args: str,
    cwd: Path,
    check: bool = True,
    env: dict | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
        env=env,
        input=stdin,
    )


# ---------------------------------------------------------------- snapshot


def snapshot_files(repo_root: Path = REPO_ROOT) -> list[str]:
    """List the repo-relative files that make up a sandbox copy.

    Tracked plus untracked-but-not-ignored files, minus COPY_EXCLUDE and
    cache dirs; files deleted in the working tree are skipped.
    """
    out = _git(
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        cwd=repo_root,
    ).stdout
    files = []
    for rel in sorted(set(filter(None, out.split("\0")))):
        parts = Path(rel).parts
        if parts[0] in COPY_EXCLUDE or SKIP_DIR_NAMES.intersection(parts):
            continue
        src = repo_root / rel
        if os.path.lexists(src) and not src.is_dir():
            files.append(rel)
    return files


def make_template(dest: Path, repo_root: Path = REPO_ROOT) -> int:
    """Copy the working-tree snapshot into ``dest``; return the file count."""
    files = snapshot_files(repo_root)
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, target, follow_symlinks=False)
    return len(files)


def _sandbox_env(sandbox: Path, workroot: Path) -> dict[str, str]:
    """Environment for git/pytest inside a sandbox.

    The sandbox root goes first on PYTHONPATH (and any entry pointing at the
    caller's checkout is dropped), so ``custom_components`` — a namespace
    package — can only resolve to the mutated copy. GIT_CEILING_DIRECTORIES
    stops git from discovering an enclosing repository, so ``git apply``
    works as a plain patch tool on the copy.
    """
    env = dict(os.environ)
    caller = str(REPO_ROOT)
    kept = [
        p
        for p in env.get("PYTHONPATH", "").split(os.pathsep)
        if p and os.path.abspath(p) != caller
    ]
    env["PYTHONPATH"] = os.pathsep.join([str(sandbox), *kept])
    env["GIT_CEILING_DIRECTORIES"] = str(workroot.resolve())
    return env


# ------------------------------------------------------------------ pytest


def _has_xdist() -> bool:
    return importlib.util.find_spec("xdist") is not None


def resolve_xdist(
    mode: str,
    jobs: int,
    cpu_count: int,
    pytest_args: list[str],
    available: bool,
) -> list[str]:
    """Return the ``-n`` args to add for an xdist-eligible tier.

    ``mode`` is "auto", "off" or an integer string. Nothing is added when
    xdist is unavailable, disabled, or already configured in pytest_args.
    """
    if mode == "off" or not available:
        return []
    if any(
        a in ("-n", "--numprocesses") or a.startswith(("-n", "--numprocesses="))
        for a in pytest_args
    ):
        return []
    if mode == "auto":
        if jobs == 1:
            return ["-n", "auto"]
        per_job = cpu_count // jobs
        return ["-n", str(per_job)] if per_job >= 2 else []
    workers = int(mode)
    return ["-n", str(workers)] if workers >= 2 else []


def _kill_group(proc: subprocess.Popen) -> None:
    """SIGKILL a still-running pytest and its xdist workers (its session)."""
    if proc.poll() is not None:
        return  # already reaped: its pgid may belong to someone else now
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)


def _run_tier(
    cwd: Path,
    env: dict,
    paths: list[str],
    pytest_args: list[str],
    timeout: int,
) -> dict:
    cmd = [sys.executable, "-m", "pytest", *paths, *pytest_args]
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    with _procs_lock:
        _active_procs.add(proc)
    try:
        try:
            stdout, _ = proc.communicate(timeout=timeout)
            exit_code: int | None = proc.returncode
            timed_out = False
            tail = ANSI_RE.sub("", "\n".join(stdout.splitlines()[-3:]))
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            proc.communicate()
            exit_code = None
            timed_out = True
            tail = f"TIMEOUT after {timeout}s"
    finally:
        with _procs_lock:
            _active_procs.discard(proc)
    return {
        # timeout counts as caught: the mutation visibly broke the suite
        "caught": timed_out or exit_code != 0,
        "exit_code": exit_code,
        "timeout": timed_out,
        "seconds": round(time.monotonic() - started, 1),
        "tail": tail,
    }


# ------------------------------------------------------------ one mutation


def _run_one(
    entry: dict | None,
    patch_text: str | None,
    template: Path,
    workroot: Path,
    tier_plan: dict,
    pytest_args: list[str],
    timeout: int,
) -> dict:
    """Copy the template, apply ``patch_text`` (entry None = control), run tiers.

    The copy is always deleted before returning.
    """
    started = time.monotonic()
    name = entry["id"] if entry else CONTROL_ID
    sandbox = Path(tempfile.mkdtemp(prefix=f"{name}-", dir=workroot))
    try:
        shutil.copytree(template, sandbox, symlinks=True, dirs_exist_ok=True)
        env = _sandbox_env(sandbox, workroot)
        result: dict = dict(entry) if entry else {"id": CONTROL_ID}
        if entry is not None:
            if patch_text is None:
                detail = f"missing patch file {entry['patch']}"
            else:
                check = _git(
                    "apply",
                    "--check",
                    cwd=sandbox,
                    check=False,
                    env=env,
                    stdin=patch_text,
                )
                detail = (
                    check.stderr.strip() or f"git apply exited {check.returncode}"
                    if check.returncode
                    else ""
                )
            if detail:
                result["error"] = "patch-does-not-apply"
                result["detail"] = detail
                result["seconds"] = round(time.monotonic() - started, 1)
                return result
            _git("apply", cwd=sandbox, env=env, stdin=patch_text)
        tier_results: dict[str, dict] = {}
        for tier, (paths, extra) in tier_plan.items():
            if _stop.is_set():
                raise KeyboardInterrupt
            tier_results[tier] = _run_tier(
                sandbox, env, paths, [*pytest_args, *extra], timeout
            )
        result["tiers"] = tier_results
        result["caught_by"] = [t for t, r in tier_results.items() if r["caught"]]
        result["missed_by"] = [t for t, r in tier_results.items() if not r["caught"]]
        result["seconds"] = round(time.monotonic() - started, 1)
        return result
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def _format_result(result: dict, done: int, total: int) -> str:
    head = f"[{done:>2}/{total}] {result['id']}"
    if result["id"] != CONTROL_ID:
        head += f" {result['function']}: {result['description']}"
    else:
        head += " unmutated snapshot"
    lines = [f"{head}  ({result.get('seconds', 0)}s)"]
    if "error" in result:
        lines.append(f"    ERROR {result['error']}: {result['detail']}")
        return "\n".join(lines)
    for tier, tier_result in result["tiers"].items():
        if result["id"] == CONTROL_ID:
            verdict = "FAILED" if tier_result["caught"] else "passed"
        else:
            verdict = "CAUGHT" if tier_result["caught"] else "missed"
        lines.append(f"    {tier}: {verdict} ({tier_result['seconds']}s)")
    return "\n".join(lines)


# -------------------------------------------------------------------- main


def previous_durations(path: str | Path | None) -> dict[str, float]:
    """Per-mutation seconds from an earlier report ({} if unusable).

    Uses each result's total ``seconds`` or, for reports written before that
    field existed, the sum of its tier ``seconds``.
    """
    if not path:
        return {}
    try:
        results = json.loads(Path(path).read_text()).get("results") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(results, dict):
        return {}
    durations: dict[str, float] = {}
    for mutation_id, result in results.items():
        if not isinstance(result, dict):
            continue
        seconds = result.get("seconds")
        if seconds is None:
            tiers = result.get("tiers") or {}
            seconds = sum(t.get("seconds") or 0 for t in tiers.values())
        durations[mutation_id] = float(seconds)
    return durations


def schedule(manifest: list[dict], durations: dict[str, float]) -> list[dict]:
    """Order mutations longest-first; unknown durations first (stable)."""
    return sorted(manifest, key=lambda e: -durations.get(e["id"], float("inf")))


def _read_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _parse_xdist(value: str) -> str:
    value = value.strip().lower()
    if value in ("auto", "off"):
        return value
    try:
        if int(value) >= 0:
            return str(int(value))
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("expected auto, off or a worker count")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=1,
        help="mutations run in parallel, each in its own repo copy "
        "(default 1; 0 = one per CPU)",
    )
    parser.add_argument(
        "--xdist",
        type=_parse_xdist,
        default="auto",
        help="pytest-xdist workers per tier run: auto (default; -n auto "
        "when --jobs 1, else cpu//jobs), off, or a number",
    )
    parser.add_argument(
        "--no-control",
        action="store_true",
        help="skip the control run of the unmutated snapshot",
    )
    parser.add_argument(
        "--workdir",
        help="parent dir for the temp sandboxes (default: system temp dir)",
    )
    parser.add_argument(
        "--schedule-from",
        metavar="REPORT",
        help="earlier report whose per-mutation durations order the run "
        "longest-first (default: the --report file, if it exists)",
    )
    args = parser.parse_args(argv)

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
    if args.jobs < 0:
        parser.error("--jobs must be >= 0")
    cpu_count = os.cpu_count() or 1
    jobs = args.jobs or cpu_count
    xdist_available = _has_xdist()
    xdist_args = resolve_xdist(
        args.xdist, jobs, cpu_count, pytest_args, xdist_available
    )
    tier_plan = {
        tier: (TIERS[tier], xdist_args if TIER_XDIST[tier] else [])
        for tier in tier_names
    }

    started_at = dt.datetime.now(dt.UTC)
    wall_start = time.monotonic()
    timing = {
        "started": started_at.isoformat(timespec="seconds"),
        "jobs": jobs,
        "cpu_count": cpu_count,
        "xdist": {
            tier: " ".join(extra) or None for tier, (_, extra) in tier_plan.items()
        },
    }
    _say(
        f"Running {len(manifest)} mutation(s) x {len(tier_names)} tier(s), "
        f"jobs={jobs}, xdist={args.xdist} "
        f"({'available' if xdist_available else 'not installed'}) -> "
        + ", ".join(f"{t}: {v or 'serial'}" for t, v in timing["xdist"].items())
    )

    workroot = Path(
        tempfile.mkdtemp(prefix="adaptive-cover-mutations-", dir=args.workdir)
    )
    results: dict[str, dict] = {}
    control: dict | None = None
    aborted = False
    try:
        template = workroot / "_template"
        template.mkdir()
        try:
            count = make_template(template)
        except (subprocess.CalledProcessError, OSError) as err:
            _say(f"FATAL: could not snapshot the working tree: {err}")
            aborted = True
            return 2
        _say(f"Snapshot: {count} files -> {workroot}")

        # Patches are read once, now, like the source snapshot.
        patches = {e["id"]: _read_or_none(MUTATION_DIR / e["patch"]) for e in manifest}
        durations = previous_durations(args.schedule_from or args.report)
        timing["scheduled_longest_first"] = bool(durations)
        # The control runs every tier to completion: always among the longest.
        tasks: list[dict | None] = [] if args.no_control else [None]
        tasks += schedule(manifest, durations)
        total = len(tasks)
        done = 0
        pool = cf.ThreadPoolExecutor(max_workers=jobs)
        try:
            futures = {
                pool.submit(
                    _run_one,
                    entry,
                    patches[entry["id"]] if entry else None,
                    template,
                    workroot,
                    tier_plan,
                    pytest_args,
                    args.timeout,
                ): entry
                for entry in tasks
            }
            for future in cf.as_completed(futures):
                try:
                    result = future.result()
                except Exception as err:  # noqa: BLE001 - report, keep going
                    entry = futures[future]
                    result = {**(entry or {"id": CONTROL_ID})}
                    result["error"] = "runner-error"
                    result["detail"] = repr(err)
                done += 1
                _say(_format_result(result, done, total))
                if result["id"] == CONTROL_ID:
                    control = result
                else:
                    results[result["id"]] = result
        except KeyboardInterrupt:
            aborted = True
            _stop.set()
            with _procs_lock:
                for proc in list(_active_procs):
                    _kill_group(proc)
            _say("\nInterrupted: killing test runs and cleaning up ...")
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
    except KeyboardInterrupt:  # during the snapshot, before the pool exists
        aborted = True
    finally:
        shutil.rmtree(workroot, ignore_errors=True)
        timing["wall_seconds"] = round(time.monotonic() - wall_start, 1)
        ordered = {e["id"]: results[e["id"]] for e in manifest if e["id"] in results}
        _write_report(
            args.report,
            tier_names,
            ordered,
            aborted=aborted,
            timing=timing,
            control=control,
        )

    ran = [r for r in ordered.values() if "tiers" in r]
    killed = [r for r in ran if r["caught_by"]]
    survivors = sorted(r["id"] for r in ran if not r["caught_by"])
    errors = sorted(r["id"] for r in ordered.values() if "error" in r)
    _say(
        f"\nKill rate: {len(killed)}/{len(ran)}"
        + (f"  SURVIVORS: {survivors}" if survivors else "")
        + (f"  ERRORS (stale patch / runner): {errors}" if errors else "")
    )
    _say(f"Wall time: {timing['wall_seconds']}s (jobs={jobs})")
    _say(f"Report: {args.report}")
    if aborted:
        return 130
    if control_failed := _control_failures(control):
        _say(
            f"CONTROL FAILED: the unmutated snapshot fails {control_failed}; "
            "kills there are not trustworthy. Fix the suite first."
        )
        return 4
    return 1 if survivors or errors else 0


def _control_failures(control: dict | None) -> list[str] | None:
    """Tiers the unmutated control run failed (None if no control ran)."""
    if control is None:
        return None
    if "error" in control:
        return [f"runner: {control['detail']}"]
    return control["caught_by"]


def _write_report(
    path: str,
    tiers: list[str],
    results: dict,
    *,
    aborted: bool,
    timing: dict,
    control: dict | None,
) -> None:
    report = {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "tiers": tiers,
        "aborted": aborted,
        "timing": timing,
        "control": control,
        "results": results,
        "summary": {
            "run": len([r for r in results.values() if "tiers" in r]),
            "killed": len([r for r in results.values() if r.get("caught_by")]),
            "survivors": sorted(
                r["id"] for r in results.values() if "tiers" in r and not r["caught_by"]
            ),
            "errors": sorted(r["id"] for r in results.values() if "error" in r),
            "control_failed": _control_failures(control),
        },
    }
    Path(path).write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    sys.exit(main())
