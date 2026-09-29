#!/usr/bin/env python3
"""Guard the behavior tier against silent test removals.

The behavior tier (tests/refactor_roadmap.json, ``behavior_tier``) is the
set of tests that touch the integration only through the Refactor Contract
seams. Its node ids are recorded in ``behavior_tier_ids.txt``. A behavior
test may only disappear (deleted, renamed, re-parametrized) together with a
ledger entry in ``ledger.md`` that names it.

    python tests/contract/check_behavior_tier.py            # check (CI)
    python tests/contract/check_behavior_tier.py --base origin/main
    python tests/contract/check_behavior_tier.py --update   # record new ids

Check mode collects the current tests (``pytest --collect-only -q``),
selects the behavior tier with RULES below, and compares it with the
recorded ids (from the working tree, or from ``--base REF`` so a PR cannot
hide a removal by also editing the ids file):
- ids that disappeared and are not named in the ledger -> FAIL (exit 1);
- ids that disappeared and are in the ledger -> reported, OK;
- new ids -> reported, OK (run --update to record them);
- test files that no rule classifies -> reported, OK (add a rule).

``--update`` rewrites behavior_tier_ids.txt from the current collection. It
refuses while unledgered removals exist unless ``--force`` is given (use
that only for bulk re-seeding, e.g. after merging pre-contract branches).

Pure stdlib; pytest is only run as a subprocess.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONTRACT_DIR.parents[1]
IDS_FILE = CONTRACT_DIR / "behavior_tier_ids.txt"
LEDGER_FILE = CONTRACT_DIR / "ledger.md"
IDS_REL = "tests/contract/behavior_tier_ids.txt"

BEHAVIOR = "behavior"
IMPLEMENTATION = "implementation"
TOOLING = "tooling"

# ------------------------------------------------------------------ rules
# The roadmap's behavior_tier definition, as code. Patterns match pytest
# node ids; ``*`` is the only wildcard (it matches anything, including "/"
# and "::"), everything else is literal (so "[param]" ids need no escaping).
# First match wins, so narrow patterns come before broad ones.
RULES: list[tuple[str, str]] = [
    # Structural guard and tooling: never behavior (roadmap: test_purity
    # "stays as a structural guard (not behavior, never a false positive)").
    ("tests/engine/test_purity.py::*", TOOLING),
    ("tests/contract/*", TOOLING),
    ("tests/mutation_set/*", TOOLING),
    # SimHouse drives a real entry through HA surfaces.
    ("tests/simulation/*", BEHAVIOR),
    # Goldens, truth table, outbound service calls.
    ("tests/characterization/test_golden_days.py::*", BEHAVIOR),
    ("tests/characterization/test_climate_truth_table.py::*", BEHAVIOR),
    ("tests/characterization/test_service_calls.py::*", BEHAVIOR),
    ("tests/characterization/test_coordinator_gating.py::*", IMPLEMENTATION),
    # P2: numpy-equivalence of engine.numeric's private helpers (clip,
    # interp), not a contract seam; a later phase may move or rename them.
    ("tests/engine/test_numeric.py::*", IMPLEMENTATION),
    # evaluate() / documented geometry functions with models.py dataclasses.
    ("tests/engine/*", BEHAVIOR),
    # Root entity-surface tests: only the named classes / halves.
    ("tests/test_live_tunables.py::TestNumberEntities::*", BEHAVIOR),
    ("tests/test_live_tunables.py::TestGateVisibility::*", BEHAVIOR),
    ("tests/test_live_tunables.py::*", IMPLEMENTATION),
    ("tests/test_smoothing_and_privacy.py::TestQuietHours::*", IMPLEMENTATION),
    ("tests/test_smoothing_and_privacy.py::TestMoveBudget::*", IMPLEMENTATION),
    ("tests/test_smoothing_and_privacy.py::*", BEHAVIOR),
    # SunData public-API regressions (roadmap: they stay behavior-tier).
    ("tests/test_regression_fixes.py::*", BEHAVIOR),
    ("tests/test_service_calls.py::*", BEHAVIOR),
    ("tests/test_hub.py::*", BEHAVIOR),
    ("tests/test_provenance.py::*", BEHAVIOR),
    ("tests/test_change_settings.py::*", BEHAVIOR),
    ("tests/test_night_born_entries.py::*", BEHAVIOR),
    ("tests/test_add_entry.py::*", BEHAVIOR),
    ("tests/test_init.py::*", BEHAVIOR),
    ("tests/test_one_page_options.py::*", BEHAVIOR),
    ("tests/test_config_flow.py::*", BEHAVIOR),
    ("tests/test_forecast_and_trace.py::*", BEHAVIOR),
    ("tests/test_entity_surfaces.py::*", BEHAVIOR),  # wp9
    ("tests/test_hub_behavior.py::*", BEHAVIOR),  # wp10
    # Post-roadmap file (v1.13.5): config-surface defaults + control-method
    # sensor through hass.states -> contract seams (2) and (3).
    ("tests/test_units_and_defaults.py::*", BEHAVIOR),
    # P0 additions: whole-house replay pins the outbound command timeline;
    # translations are part of the UI surface; the snapshot guard only checks
    # the fixture is sanitized, so it is tooling.
    ("tests/replay/test_house_replay.py::*", BEHAVIOR),
    ("tests/replay/test_house_snapshot.py::*", TOOLING),
    ("tests/test_translations.py::*", BEHAVIOR),
    ("tests/test_entity_surface_v2.py::*", BEHAVIOR),  # P1 entity surface (C1)
    # P5 layered settings: `resolve` is a contract v2 seam (ADR 0004).
    # Precedence, provenance, the lift's rules and the P5 guarantee on the
    # live snapshot (resolve(w) == legacy_flat(w)) are behavior; the purity
    # guard is a structural check like test_purity.
    ("tests/settings/test_settings_purity.py::*", TOOLING),
    ("tests/settings/test_resolve.py::*", BEHAVIOR),
    ("tests/settings/test_lift.py::*", BEHAVIOR),
    ("tests/settings/test_house_lift.py::*", BEHAVIOR),
    # Implementation tier: a refactor may freely break these.
    # P3: the option spec's own tests (its table shape changes in P5); the
    # surfaces it generates are pinned by the behavior tier and by
    # tests/contract/spec_parity.json.
    ("tests/settings/*", IMPLEMENTATION),
    ("tests/test_coordinator.py::*", IMPLEMENTATION),
    ("tests/test_calculation.py::*", IMPLEMENTATION),
    ("tests/test_button.py::*", IMPLEMENTATION),
    ("tests/test_helpers.py::*", IMPLEMENTATION),
    # P2 clock seam: injects through coordinator.default_clock, which P4
    # moves with the coordinator split.
    ("tests/test_clock_seam.py::*", IMPLEMENTATION),
    # P2 stdlib time helpers (day_steps, nearest_index, localize_standard):
    # edge cases of private helpers; the SunData contract pins (277/289/301
    # points, astral values) are behavior tier in test_regression_fixes.py.
    ("tests/test_time_helpers.py::*", IMPLEMENTATION),
    # P4 coordinator split: unit tests of the runtime components with fakes.
    # Later P4 PRs reshape the components (one cover per window, a typed
    # event queue), so these are implementation tier; the no-hass guard is
    # a structural check like test_purity.
    ("tests/runtime/test_no_hass.py::*", TOOLING),
    ("tests/runtime/*", IMPLEMENTATION),
]


def pattern_regex(pattern: str) -> re.Pattern[str]:
    """Compile a node-id pattern where only ``*`` is a wildcard."""
    return re.compile(
        "".join(
            ".*" if part == "*" else re.escape(part)
            for part in re.split(r"(\*)", pattern)
        )
        + r"\Z"
    )


_COMPILED_RULES = [(pattern_regex(p), tier) for p, tier in RULES]


def classify(node_id: str) -> str | None:
    """Return the tier of a node id, or None when no rule matches."""
    for regex, tier in _COMPILED_RULES:
        if regex.match(node_id):
            return tier
    return None


def select_behavior(node_ids: list[str]) -> tuple[list[str], list[str]]:
    """Split node ids into (sorted behavior-tier ids, unclassified ids)."""
    behavior, unclassified = [], []
    for node_id in node_ids:
        tier = classify(node_id)
        if tier == BEHAVIOR:
            behavior.append(node_id)
        elif tier is None:
            unclassified.append(node_id)
    return sorted(set(behavior)), sorted(set(unclassified))


# ----------------------------------------------------------------- ledger

LEDGER_HEADING_RE = re.compile(r"^##\s+(L\d{4})\b(.*)$")
LEDGER_FIELD_RE = re.compile(
    r"^-\s+\**\s*(removed|renamed|replacements|mutations re-targeted|"
    r"contract change|reason)\s*:?\**\s*:?\s*(.*)$",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
BACKTICK_RE = re.compile(r"`([^`]+)`")
RENAME_RE = re.compile(r"`([^`]+)`\s*(?:->|→)\s*`([^`]+)`")


@dataclass
class LedgerEntry:
    """One intentional contract change recorded in ledger.md."""

    entry_id: str
    date: str | None
    title: str
    removed: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    replacements: list[str] = field(default_factory=list)
    mutations: str = ""
    contract_change: str = ""
    reason: str = ""


@dataclass
class Ledger:
    """Parsed ledger: entries plus format errors."""

    entries: list[LedgerEntry]
    errors: list[str]

    def retired_patterns(self) -> list[str]:
        """Every removed id/pattern plus the old side of every rename."""
        out = []
        for entry in self.entries:
            out.extend(entry.removed)
            out.extend(old for old, _ in entry.renamed)
        return out

    def covers(self) -> LedgerMatcher:
        """Return a matcher answering 'is this removed id ledgered?'."""
        return LedgerMatcher(self.retired_patterns())


class LedgerMatcher:
    """Exact ids plus ``*`` patterns from the ledger's retired lists."""

    def __init__(self, patterns: list[str]) -> None:
        self.exact = {p for p in patterns if "*" not in p}
        self.globs = [pattern_regex(p) for p in patterns if "*" in p]

    def __call__(self, node_id: str) -> bool:
        return node_id in self.exact or any(g.match(node_id) for g in self.globs)


def parse_ledger(text: str) -> Ledger:
    """Parse ledger.md. HTML comments (the format example) are ignored."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    entries: list[LedgerEntry] = []
    errors: list[str] = []
    current: LedgerEntry | None = None
    current_field: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        heading = LEDGER_HEADING_RE.match(line)
        if heading:
            date = DATE_RE.search(heading.group(2))
            title = DATE_RE.sub("", heading.group(2)).strip(" -—·|:")
            current = LedgerEntry(heading.group(1), date and date.group(1), title)
            entries.append(current)
            current_field = None
            continue
        if line.startswith("## ") or line.startswith("# "):
            current, current_field = None, None
            continue
        if current is None:
            continue
        field_match = LEDGER_FIELD_RE.match(line)
        if field_match:
            current_field = field_match.group(1).lower()
            _add_to_field(current, current_field, field_match.group(2))
        elif line.startswith((" ", "\t")) and current_field and line.strip():
            _add_to_field(current, current_field, line.strip().lstrip("-* "))
    seen: set[str] = set()
    for entry in entries:
        where = f"ledger {entry.entry_id}"
        if entry.entry_id in seen:
            errors.append(f"{where}: duplicate entry id")
        seen.add(entry.entry_id)
        if entry.date is None:
            errors.append(f"{where}: heading has no YYYY-MM-DD date")
        else:
            try:
                dt.date.fromisoformat(entry.date)
            except ValueError:
                errors.append(f"{where}: invalid date {entry.date}")
        if not entry.reason:
            errors.append(f"{where}: missing 'Reason'")
        # An entry must either retire tests or record a named contract
        # change (C1..C8) that only adds or re-anchors pins.
        names_change = entry.contract_change.strip().lower() not in ("", "none")
        if not entry.removed and not entry.renamed and not names_change:
            errors.append(
                f"{where}: names no removed or renamed test ids and no contract change"
            )
        for node_id in [*entry.removed, *(o for o, _ in entry.renamed)]:
            if "::" not in node_id and "*" not in node_id:
                errors.append(f"{where}: {node_id!r} is not a pytest node id")
    return Ledger(entries, errors)


def _add_to_field(entry: LedgerEntry, name: str, value: str) -> None:
    value = value.strip()
    if not value:
        return
    if name == "removed":
        entry.removed.extend(BACKTICK_RE.findall(value))
    elif name == "renamed":
        entry.renamed.extend(RENAME_RE.findall(value))
    elif name == "replacements":
        entry.replacements.extend(BACKTICK_RE.findall(value))
    elif name == "mutations re-targeted":
        entry.mutations = f"{entry.mutations} {value}".strip()
    elif name == "contract change":
        entry.contract_change = f"{entry.contract_change} {value}".strip()
    elif name == "reason":
        entry.reason = f"{entry.reason} {value}".strip()


# ------------------------------------------------------------- comparison


@dataclass
class TierDiff:
    """Result of comparing the recorded tier with the current one."""

    added: list[str]
    removed_ledgered: list[str]
    removed_unledgered: list[str]

    @property
    def ok(self) -> bool:
        """True when no behavior test vanished without a ledger entry."""
        return not self.removed_unledgered


def compare(recorded: list[str], current: list[str], ledger: Ledger) -> TierDiff:
    """Diff recorded vs current behavior-tier ids against the ledger."""
    recorded_set, current_set = set(recorded), set(current)
    covered = ledger.covers()
    removed = sorted(recorded_set - current_set)
    return TierDiff(
        added=sorted(current_set - recorded_set),
        removed_ledgered=[r for r in removed if covered(r)],
        removed_unledgered=[r for r in removed if not covered(r)],
    )


def parse_ids(text: str) -> list[str]:
    """Parse behavior_tier_ids.txt (``#`` comments and blanks ignored)."""
    return sorted(
        {
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    )


def format_ids(ids: list[str]) -> str:
    """Render behavior_tier_ids.txt content."""
    header = (
        "# Behavior-tier pytest node ids (tests/refactor_roadmap.json "
        "behavior_tier).\n"
        "# GENERATED by `python tests/contract/check_behavior_tier.py "
        "--update`; do not edit by hand.\n"
        "# Removing an id requires an entry in tests/contract/ledger.md.\n"
    )
    return header + "".join(f"{i}\n" for i in sorted(set(ids)))


# ------------------------------------------------------------- collection


def collect_node_ids(repo_root: Path = REPO_ROOT) -> list[str]:
    """Collect every test node id under tests/ with pytest --collect-only.

    Raises
    ------
    RuntimeError
        If collection fails (import errors etc.).
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:xdist",
            "tests",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, 5):
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
        raise RuntimeError(
            f"pytest --collect-only failed (exit {proc.returncode}):\n{tail}"
        )
    return parse_collect_output(proc.stdout)


def parse_collect_output(stdout: str) -> list[str]:
    """Extract node ids from ``pytest --collect-only -q`` output."""
    ids = []
    for line in stdout.splitlines():
        if not line.strip():
            break  # the id list ends at the first blank line
        if line.startswith("tests/") and "::" in line:
            ids.append(line.strip())
    return ids


def _recorded_ids(base: str | None) -> list[str]:
    if base is None:
        if not IDS_FILE.exists():
            raise FileNotFoundError(
                f"{IDS_FILE} does not exist; run with --update to create it"
            )
        return parse_ids(IDS_FILE.read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["git", "show", f"{base}:{IDS_REL}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FileNotFoundError(
            f"cannot read {IDS_REL} at {base}: {proc.stderr.strip()}"
        )
    return parse_ids(proc.stdout)


# -------------------------------------------------------------------- CLI


def _print_list(title: str, items: list[str], limit: int | None) -> None:
    if not items:
        return
    print(f"{title} ({len(items)}):")
    shown = items if limit is None else items[:limit]
    for item in shown:
        print(f"  {item}")
    if len(shown) < len(items):
        print(f"  ... and {len(items) - len(shown)} more (use --verbose)")


def _files(node_ids: list[str]) -> list[str]:
    return sorted({n.split("::", 1)[0] for n in node_ids})


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite behavior_tier_ids.txt from the current collection",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="with --update: write even if unledgered removals exist",
    )
    parser.add_argument(
        "--base",
        metavar="REF",
        help="compare against behavior_tier_ids.txt at this git ref "
        "(e.g. origin/main) instead of the working-tree file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="list every added / ledgered id (default: first 20)",
    )
    args = parser.parse_args(argv)
    limit = None if args.verbose else 20

    ledger = parse_ledger(LEDGER_FILE.read_text(encoding="utf-8"))
    try:
        current_all = collect_node_ids()
    except RuntimeError as err:
        print(f"ERROR: {err}")
        return 2
    current, unclassified = select_behavior(current_all)

    try:
        recorded = _recorded_ids(args.base)
    except FileNotFoundError as err:
        if not args.update:
            print(f"ERROR: {err}")
            return 2
        recorded = []
    diff = compare(recorded, current, ledger)

    print(
        f"Behavior tier: {len(current)} ids now, {len(recorded)} recorded"
        + (f" at {args.base}" if args.base else "")
        + f"; {len(current_all)} tests collected in total."
    )
    _print_list("New behavior-tier ids", diff.added, limit)
    _print_list("Removed, covered by the ledger", diff.removed_ledgered, limit)
    _print_list(
        "Unclassified test files (add a rule to RULES in "
        "tests/contract/check_behavior_tier.py)",
        _files(unclassified),
        None,
    )
    for error in ledger.errors:
        print(f"LEDGER ERROR: {error}")
    if diff.removed_unledgered:
        print(
            f"UNLEDGERED REMOVALS ({len(diff.removed_unledgered)}): these "
            "behavior-tier tests disappeared without a ledger entry in "
            "tests/contract/ledger.md:"
        )
        for node_id in diff.removed_unledgered:
            print(f"  {node_id}")

    if args.update:
        if (diff.removed_unledgered or ledger.errors) and not args.force:
            print(
                "Refusing to --update: add ledger entries (or fix the "
                "ledger) first, or pass --force to re-seed anyway."
            )
            return 1
        IDS_FILE.write_text(format_ids(current), encoding="utf-8")
        print(f"Wrote {len(current)} ids to {IDS_FILE.relative_to(REPO_ROOT)}")
        return 0

    if diff.removed_unledgered or ledger.errors:
        return 1
    if diff.added:
        print("OK (run with --update to record the new ids).")
    else:
        print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
