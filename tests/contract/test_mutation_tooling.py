"""Tests for the mutation tooling: make_patches --check and runner helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MUTATION_DIR = Path(__file__).resolve().parents[1] / "mutation_set"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"_mutation_tooling_{name}", MUTATION_DIR / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


mp = _load("make_patches")
rm = _load("run_mutations")

SOURCE = "def gate(a, b):\n    return a >= b\n\n\ndef other():\n    return 1\n"


@pytest.fixture
def fake_repo(tmp_path):
    """A tiny repo root with one source file and an empty patch dir."""
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text(SOURCE)
    out = tmp_path / "out"
    out.mkdir()
    mutations = [
        mp.Mutation(
            "M01",
            "ge_to_gt",
            "pkg/mod.py",
            "gate",
            "ge -> gt",
            "    return a >= b",
            "    return a > b",
        ),
        mp.Mutation(
            "M02",
            "one_to_two",
            "pkg/mod.py",
            "other",
            "1 -> 2",
            "    return 1",
            "    return 2",
        ),
    ]
    return root, out, mutations


def test_write_then_check_is_clean(fake_repo):
    root, out, mutations = fake_repo
    assert mp.write(out, root, mutations) == []
    assert sorted(p.name for p in out.iterdir()) == [
        "M01_ge_to_gt.patch",
        "M02_one_to_two.patch",
        "manifest.json",
    ]
    assert "+    return a > b" in (out / "M01_ge_to_gt.patch").read_text()
    assert mp.check(out, root, mutations) == []


def test_check_reports_non_applying_mutation(fake_repo):
    root, out, mutations = fake_repo
    mp.write(out, root, mutations)
    (root / "pkg" / "mod.py").write_text(SOURCE.replace("a >= b", "b <= a"))
    problems = mp.check(out, root, mutations)
    assert any(p.startswith("M01:") and "found 0" in p for p in problems)
    # M02's target text is intact; only its line offsets could move
    assert not any(p.startswith("M02:") for p in problems)


def test_check_reports_stale_missing_and_orphaned_files(fake_repo):
    root, out, mutations = fake_repo
    mp.write(out, root, mutations)
    stale = out / "M01_ge_to_gt.patch"
    stale.write_text(stale.read_text() + "\n")
    (out / "M02_one_to_two.patch").unlink()
    (out / "M99_leftover.patch").write_text("old\n")
    problems = mp.check(out, root, mutations)
    assert "M01_ge_to_gt.patch: stale" in " ".join(problems)
    assert any(p.startswith("M02_one_to_two.patch: missing") for p in problems)
    assert any(p.startswith("M99_leftover.patch: orphaned") for p in problems)


def test_check_reports_ambiguous_target_and_writes_nothing(fake_repo):
    root, out, mutations = fake_repo
    (root / "pkg" / "mod.py").write_text(SOURCE + "    return a >= b\n")
    errors = mp.write(out, root, mutations)
    assert any("found 2" in e for e in errors)
    assert list(out.iterdir()) == []  # all-or-nothing


def test_write_removes_orphans(fake_repo):
    root, out, mutations = fake_repo
    (out / "M77_gone.patch").write_text("old\n")
    (out / "notes.txt").write_text("keep me\n")
    assert mp.write(out, root, mutations) == []
    assert not (out / "M77_gone.patch").exists()
    assert (out / "notes.txt").exists()


@pytest.mark.parametrize(
    ("mode", "jobs", "cpus", "args", "available", "expected"),
    [
        ("auto", 1, 16, [], True, ["-n", "auto"]),
        ("auto", 4, 16, [], True, ["-n", "4"]),
        ("auto", 16, 16, [], True, []),
        ("auto", 1, 16, [], False, []),
        ("off", 1, 16, [], True, []),
        ("3", 8, 16, [], True, ["-n", "3"]),
        ("1", 1, 16, [], True, []),
        ("auto", 1, 16, ["-q", "-n", "2"], True, []),
        ("auto", 1, 16, ["--numprocesses=2"], True, []),
    ],
)
def test_resolve_xdist(mode, jobs, cpus, args, available, expected):
    assert rm.resolve_xdist(mode, jobs, cpus, args, available) == expected


def test_previous_durations_reads_old_and_new_report_formats(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        '{"results": {'
        '"M01": {"seconds": 12.5, "tiers": {"engine": {"seconds": 1}}},'
        '"M02": {"tiers": {"engine": {"seconds": 2}, "entity": {"seconds": 3}}},'
        '"M03": {"error": "patch-does-not-apply"}}}'
    )
    assert rm.previous_durations(report) == {"M01": 12.5, "M02": 5.0, "M03": 0.0}
    assert rm.previous_durations(tmp_path / "missing.json") == {}
    (tmp_path / "bad.json").write_text("not json")
    assert rm.previous_durations(tmp_path / "bad.json") == {}
    assert rm.previous_durations(None) == {}


def test_schedule_longest_first_unknown_first_stable():
    manifest = [{"id": f"M0{i}"} for i in range(1, 6)]
    durations = {"M01": 5.0, "M02": 50.0, "M04": 5.0, "M05": 20.0}
    order = [e["id"] for e in rm.schedule(manifest, durations)]
    assert order == ["M03", "M02", "M05", "M01", "M04"]


def test_runner_entity_tier_skips_tooling_tests():
    assert "--ignore=tests/contract" in rm.TIERS["entity"]
