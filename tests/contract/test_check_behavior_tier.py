"""Tests for the behavior-tier ledger checker (pure functions only)."""

from __future__ import annotations

import pytest

from tests.contract import check_behavior_tier as cbt

LEDGER_HEADER = """# Contract ledger

## Rules

- "Reason" is required.
- Removed: `tests/test_hub.py::test_not_an_entry`

<!--
## L0001 · 2026-10-14 · Example only
- **Removed:**
  - `tests/test_hub.py::test_example_only`
- **Reason:** example
-->

## Entries
"""


def _ledger(body: str = "") -> cbt.Ledger:
    return cbt.parse_ledger(LEDGER_HEADER + body)


@pytest.mark.parametrize(
    ("node_id", "tier"),
    [
        ("tests/simulation/test_lifecycle.py::test_restart", cbt.BEHAVIOR),
        ("tests/engine/test_overhang_glare.py::TestX::test_y[0.5-1]", cbt.BEHAVIOR),
        ("tests/engine/test_purity.py::test_engine_dir_exists", cbt.TOOLING),
        ("tests/contract/test_check_behavior_tier.py::test_x", cbt.TOOLING),
        (
            "tests/characterization/test_golden_days.py::test_golden[a|b]",
            cbt.BEHAVIOR,
        ),
        (
            "tests/characterization/test_coordinator_gating.py::test_gate",
            cbt.IMPLEMENTATION,
        ),
        (
            "tests/test_live_tunables.py::TestNumberEntities::test_n",
            cbt.BEHAVIOR,
        ),
        (
            "tests/test_live_tunables.py::TestModeSelect::test_m",
            cbt.IMPLEMENTATION,
        ),
        (
            "tests/test_smoothing_and_privacy.py::TestQuietHours::test_q",
            cbt.IMPLEMENTATION,
        ),
        ("tests/test_smoothing_and_privacy.py::test_privacy", cbt.BEHAVIOR),
        ("tests/test_coordinator.py::TestInverseState::test_a", cbt.IMPLEMENTATION),
        ("tests/test_brand_new_file.py::test_x", None),
        ("tests/characterization/test_new_thing.py::test_x", None),
    ],
)
def test_classify(node_id, tier):
    assert cbt.classify(node_id) == tier


def test_select_behavior_splits_and_sorts():
    behavior, unclassified = cbt.select_behavior(
        [
            "tests/simulation/test_b.py::test_2",
            "tests/test_helpers.py::test_get_domain",
            "tests/simulation/test_a.py::test_1",
            "tests/test_new.py::test_z",
            "tests/simulation/test_a.py::test_1",
        ]
    )
    assert behavior == [
        "tests/simulation/test_a.py::test_1",
        "tests/simulation/test_b.py::test_2",
    ]
    assert unclassified == ["tests/test_new.py::test_z"]


def test_pattern_brackets_are_literal_and_star_spans_separators():
    regex = cbt.pattern_regex("tests/a.py::test_x[1-2]")
    assert regex.match("tests/a.py::test_x[1-2]")
    assert not regex.match("tests/a.py::test_x1")
    assert not regex.match("tests/a.py::test_x[1-2]_suffix")
    assert cbt.pattern_regex("tests/sim/*").match("tests/sim/deep/t.py::C::t[p]")


def test_parse_ledger_ignores_comments_and_non_entry_sections():
    ledger = _ledger()
    assert ledger.entries == []
    assert ledger.errors == []
    assert not ledger.covers()("tests/test_hub.py::test_example_only")
    assert not ledger.covers()("tests/test_hub.py::test_not_an_entry")


def test_parse_ledger_entry_fields():
    ledger = _ledger(
        """
## L0001 — 2026-10-14 — Entity names (C1)
- **Removed:**
  - `tests/test_hub.py::test_gone`
  - `tests/test_entity_surfaces.py::TestLegacy::*`
- **Renamed:**
  - `tests/test_hub.py::test_old` -> `tests/test_hub.py::test_new`
- **Replacements:** `tests/test_hub.py::test_new`, `tests/test_hub.py::test_more`
- **Mutations re-targeted:** M40 re-anchored in sensor.py
- **Contract change:** C1
- **Reason:** P1 renames entities;
  the old tests pinned the old names.
"""
    )
    assert ledger.errors == []
    (entry,) = ledger.entries
    assert entry.entry_id == "L0001"
    assert entry.date == "2026-10-14"
    assert entry.title == "Entity names (C1)"
    assert entry.removed == [
        "tests/test_hub.py::test_gone",
        "tests/test_entity_surfaces.py::TestLegacy::*",
    ]
    assert entry.renamed == [
        ("tests/test_hub.py::test_old", "tests/test_hub.py::test_new")
    ]
    assert entry.replacements == [
        "tests/test_hub.py::test_new",
        "tests/test_hub.py::test_more",
    ]
    assert entry.mutations == "M40 re-anchored in sensor.py"
    assert entry.contract_change == "C1"
    assert entry.reason == ("P1 renames entities; the old tests pinned the old names.")


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        (
            "## L0001 · no date\n- Removed: `tests/a.py::t`\n- Reason: r\n",
            "no YYYY-MM-DD date",
        ),
        ("## L0001 · 2026-10-14\n- Removed: `tests/a.py::t`\n", "missing 'Reason'"),
        ("## L0001 · 2026-10-14\n- Reason: r\n", "names no removed or renamed"),
        (
            "## L0001 · 2026-10-14\n- Removed: `test_bare_name`\n- Reason: r\n",
            "is not a pytest node id",
        ),
        (
            "## L0001 · 2026-10-14\n- Removed: `tests/a.py::t`\n- Reason: r\n"
            "## L0001 · 2026-10-15\n- Removed: `tests/a.py::u`\n- Reason: r\n",
            "duplicate entry id",
        ),
        (
            "## L0001 · 2026-13-40\n- Removed: `tests/a.py::t`\n- Reason: r\n",
            "invalid date",
        ),
    ],
)
def test_parse_ledger_validation_errors(body, fragment):
    ledger = _ledger(body)
    assert any(fragment in error for error in ledger.errors), ledger.errors


RECORDED = [
    "tests/simulation/test_a.py::test_keep",
    "tests/simulation/test_a.py::test_removed",
    "tests/simulation/test_a.py::test_renamed_old",
    "tests/test_entity_surfaces.py::TestLegacy::test_one[x-1]",
]


def test_compare_unledgered_removal_fails():
    current = ["tests/simulation/test_a.py::test_keep"]
    diff = cbt.compare(RECORDED, current, _ledger())
    assert not diff.ok
    assert diff.removed_unledgered == RECORDED[1:]
    assert diff.removed_ledgered == []


def test_compare_ledgered_removals_rename_and_glob_pass():
    ledger = _ledger(
        """
## L0001 · 2026-10-14 · retire
- Removed: `tests/simulation/test_a.py::test_removed`
- Removed: `tests/test_entity_surfaces.py::TestLegacy::*`
- Renamed: `tests/simulation/test_a.py::test_renamed_old` -> `tests/simulation/test_a.py::test_renamed_new`
- Reason: intentional
"""
    )
    assert ledger.errors == []
    current = [
        "tests/simulation/test_a.py::test_keep",
        "tests/simulation/test_a.py::test_renamed_new",
        "tests/simulation/test_b.py::test_added",
    ]
    diff = cbt.compare(RECORDED, current, ledger)
    assert diff.ok
    assert diff.removed_unledgered == []
    assert diff.removed_ledgered == RECORDED[1:]
    assert diff.added == [
        "tests/simulation/test_a.py::test_renamed_new",
        "tests/simulation/test_b.py::test_added",
    ]


def test_compare_only_additions_is_ok():
    diff = cbt.compare(RECORDED[:1], RECORDED, _ledger())
    assert diff.ok
    assert diff.added == RECORDED[1:]


def test_ids_file_roundtrip():
    ids = ["tests/b.py::t", "tests/a.py::t[1]", "tests/a.py::t[1]"]
    text = cbt.format_ids(ids)
    assert text.startswith("#")
    assert cbt.parse_ids(text) == ["tests/a.py::t[1]", "tests/b.py::t"]


def test_parse_collect_output_stops_at_summary():
    stdout = (
        "tests/simulation/test_a.py::test_one\n"
        "tests/simulation/test_a.py::test_two[p-1]\n"
        "\n"
        "=== warnings summary ===\n"
        "tests/simulation/test_a.py::test_one\n"
        "1801 tests collected in 0.2s\n"
    )
    assert cbt.parse_collect_output(stdout) == [
        "tests/simulation/test_a.py::test_one",
        "tests/simulation/test_a.py::test_two[p-1]",
    ]


def test_committed_ledger_parses_cleanly():
    ledger = cbt.parse_ledger(cbt.LEDGER_FILE.read_text(encoding="utf-8"))
    assert ledger.errors == []


def test_contract_change_entry_without_removals_is_valid():
    """An entry may retire no tests when it records a named contract change."""
    ledger = _ledger(
        "## L0001 · 2026-10-14 · adds pins\n"
        "- **Removed:** none\n"
        "- **Contract change:** C1\n"
        "- **Reason:** additive surface change\n"
    )
    assert ledger.errors == []


def test_entry_without_removals_or_contract_change_is_invalid():
    ledger = _ledger(
        "## L0001 · 2026-10-14 · nothing\n"
        "- **Contract change:** none\n"
        "- **Reason:** r\n"
    )
    assert any("no contract change" in e for e in ledger.errors)
