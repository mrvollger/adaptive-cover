"""House-replay goldens: the 15 live windows on 6 dates, byte for byte.

Each case replays one live window entry (from the sanitized snapshot in
``tests/fixtures/house_snapshot/``) through the real integration for one
scripted local day and compares the rendered outbound command timeline and
position-sensor trace against ``goldens/<window>__<date>.txt``. See
``house_replay.py`` for the script and the rendering.

To regenerate after an INTENDED behavior change:

    UPDATE_GOLDENS=1 python -m pytest tests/replay -q -n auto

and ship the golden diff with a contract-ledger entry: it is the review
artifact that proves (or explains) equivalence with the live house.
"""

from __future__ import annotations

import difflib
import os

import pytest

from .house_replay import (
    DATES,
    GOLDENS_DIR,
    golden_path,
    load_windows,
    render,
    run_replay,
)

UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"

WINDOWS = load_windows()
CASES = [(window, label) for window in WINDOWS for label in DATES]


def test_snapshot_has_the_fifteen_live_windows():
    """The replay covers every live window, and nothing else."""
    assert len(WINDOWS) == 15
    assert len({w.slug for w in WINDOWS}) == 15
    assert len({w.cover for w in WINDOWS}) == 15


@pytest.mark.parametrize(
    ("window", "label"),
    CASES,
    ids=[f"{window.slug}-{label}" for window, label in CASES],
)
async def test_house_replay(hass, freezer, window, label):
    replay = await run_replay(hass, freezer, window, label)
    rendered = render(replay)
    path = golden_path(window, label)
    if UPDATE:
        GOLDENS_DIR.mkdir(exist_ok=True)
        path.write_text(rendered)
        pytest.skip(f"updated {path.name}")
    assert path.exists(), (
        f"Missing golden {path.name}; run with UPDATE_GOLDENS=1 to create it"
    )
    _assert_matches_golden(rendered, window, label)


def _assert_matches_golden(rendered: str, window, label: str) -> None:
    path = golden_path(window, label)
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
        pytest.fail(f"House replay changed for {window.title} on {label}:\n{diff}")


@pytest.mark.parametrize(
    ("window", "label"),
    CASES,
    ids=[f"{window.slug}-{label}" for window, label in CASES],
)
async def test_house_replay_consolidated(hass, freezer, window, label):
    """The same day through a house consolidated at 00:30 (P7): same golden.

    The window entry becomes a subentry of the house entry (the repair
    fix flow), keeping its key and entities; every outbound command and
    sensor sample must match the legacy golden byte for byte.
    """
    replay = await run_replay(hass, freezer, window, label, consolidated=True)
    assert golden_path(window, label).exists()
    _assert_matches_golden(render(replay), window, label)
