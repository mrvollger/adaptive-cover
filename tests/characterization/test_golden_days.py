"""Characterization: full-day schedules of the current implementation.

Compare rendered schedules against committed goldens. To regenerate after an
INTENDED behavior change:

    UPDATE_GOLDENS=1 python -m pytest tests/characterization/test_golden_days.py -q

and include the golden diff in the PR - it is the review artifact.
"""

import difflib
import os

import pytest

from .golden_lib import GOLDENS_DIR, SCENARIOS, golden_path, render_scenario

UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_golden_day(scenario):
    rendered = render_scenario(scenario)
    path = golden_path(scenario)
    if UPDATE:
        GOLDENS_DIR.mkdir(exist_ok=True)
        path.write_text(rendered)
        pytest.skip(f"updated {path.name}")
    assert path.exists(), (
        f"Missing golden {path.name}; run with UPDATE_GOLDENS=1 to create it"
    )
    expected = path.read_text()
    if rendered != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                rendered.splitlines(),
                fromfile=f"goldens/{path.name}",
                tofile="rendered",
                lineterm="",
                n=2,
            )
        )
        pytest.fail(f"Schedule changed for {scenario.name}:\n{diff}")
