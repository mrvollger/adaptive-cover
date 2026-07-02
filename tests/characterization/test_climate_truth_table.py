"""Characterization: pin the climate-mode decision tree, combination by combination.

The committed ``climate_truth_table.json`` records what ``ClimateCoverState``
returns today for every combination of presence x temperature x weather x
blind type x sun validity x transparency. Any refactor of the climate logic
must either reproduce these outputs or regenerate the table in the same PR
(``PYTHONPATH=. python tests/characterization/generate_truth_table.py``) so
the behavior change is visible in review.
"""

import pytest

from .truth_table_lib import combo_key, evaluate_combo, iter_combos, load_table

_COMBOS = list(iter_combos())


@pytest.fixture(scope="module")
def truth_table():
    return load_table()


@pytest.mark.parametrize(
    "combo", _COMBOS, ids=[combo_key(*c) for c in _COMBOS]
)
def test_climate_state_matches_recorded_behavior(combo, truth_table):
    key = combo_key(*combo)
    assert key in truth_table, (
        f"No recorded row for {key}; regenerate the truth table"
    )
    assert evaluate_combo(*combo) == truth_table[key]


def test_table_has_no_orphan_rows(truth_table):
    """Every recorded row corresponds to a live combination."""
    live_keys = {combo_key(*c) for c in _COMBOS}
    assert set(truth_table) == live_keys
