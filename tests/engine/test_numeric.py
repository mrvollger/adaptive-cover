"""engine.numeric reproduces the numpy scalar calls it replaced (P2, ADR 0005).

numpy stays available in the test environment (pytest-homeassistant-custom-
component pins it), so it serves as the reference: every case compares the
helper with numpy bit for bit, and the printed form too, because decision
traces print these values.

Two numpy results depend on how numpy was compiled, not on numpy's
definition, and these tests accept both forms:

- The sign of a clipped zero: arm64 builds take max(-0.0, 0) as +0.0.
- ``np.interp``'s ``slope * (x - xp[j]) + fp[j]``: arm64 builds contract it
  into one fused multiply-add (one rounding instead of two), x86-64 builds
  do not. ``interp`` computes it unfused, like the C source and x86-64
  numpy, so it gives the same answer on every platform.
"""

from __future__ import annotations

import itertools
import math
import random

import pytest

from custom_components.adaptive_cover.engine.numeric import _search, clip, interp

np = pytest.importorskip("numpy")


def _same(ours: float, theirs: float) -> bool:
    """Equal floats, NaN equal to NaN (the sign of zero is not compared)."""
    if math.isnan(ours) or math.isnan(theirs):
        return math.isnan(ours) and math.isnan(theirs)
    return ours == theirs


VALUES = [-5, 0, 3, 45, 100, 105, -2.5, -0.0, 0.0, 37.5, 99.99, 100.0, 250.0]
BOUNDS = [(0, 100), (0, None), (0, 2.1), (0.0, 100), (10, 5), (-1.5, 1.5)]


@pytest.mark.parametrize(("lower", "upper"), BOUNDS)
@pytest.mark.parametrize("value", VALUES)
def test_clip_matches_numpy(value, lower, upper):
    ours = clip(value, lower, upper)
    theirs = np.clip(value, lower, upper)
    assert _same(float(ours), float(theirs))
    # Same printed form: "45" stays "45" and "45.0" stays "45.0" in traces.
    if ours != 0:  # the sign of a clipped zero is build-dependent (docstring)
        assert str(ours) == str(theirs)


def test_clip_nan_passes_through():
    assert math.isnan(clip(math.nan, 0, 100))
    assert math.isnan(float(np.clip(math.nan, 0, 100)))


def _interp_cases() -> list[tuple[float, list[float], list[float]]]:
    rng = random.Random(20260929)
    cases: list[tuple[float, list[float], list[float]]] = []
    # The integration's own use: an int state through int lists.
    for state in range(-5, 106):
        cases.append((state, [0, 100], [20, 80]))
        cases.append((state, [0, 100], [100, 0]))
        cases.append((state, [0, 25, 50, 75, 100], [0, 10, 40, 90, 100]))
        cases.append(
            (state, [0, 10, 20, 50, 60, 70, 80, 100], [5, 9, 30, 31, 60, 61, 90, 95])
        )
    # Random sorted, duplicate-knot and unsorted xp of every length 1..14.
    for length in range(1, 15):
        for _ in range(60):
            xp = sorted(rng.uniform(-50, 150) for _ in range(length))
            if length > 2 and rng.random() < 0.3:
                xp[1] = xp[2]  # a repeated knot
            if rng.random() < 0.25:
                rng.shuffle(xp)  # numpy's answer for unsorted input
            fp = [rng.uniform(-100, 200) for _ in range(length)]
            for x in [rng.uniform(-80, 180) for _ in range(6)] + xp[:3]:
                cases.append((x, xp, fp))
            cases.append((math.nan, xp, fp))
    return cases


def _unfused_and_fused(x: float, xp: list[float], fp: list[float]):
    """The interval formula with two roundings and with one (FMA)."""
    xs = [float(v) for v in xp]
    ys = [float(v) for v in fp]
    j = _search(float(x), xs)
    slope = (ys[j + 1] - ys[j]) / (xs[j + 1] - xs[j])
    unfused = slope * (float(x) - xs[j]) + ys[j]
    return unfused, math.fma(slope, float(x) - xs[j], ys[j])


def test_interp_matches_numpy_bit_for_bit():
    mismatches = []
    for x, xp, fp in _interp_cases():
        ours = interp(x, xp, fp)
        theirs = float(np.interp(x, xp, fp))
        if _same(ours, theirs):
            continue
        # Only the FMA-contracted numpy builds may differ, and only in the
        # interval formula: same interval, same operands, one rounding.
        unfused, fused = _unfused_and_fused(x, xp, fp)
        if not (_same(ours, unfused) and _same(theirs, fused)):
            mismatches.append((x, xp, fp, ours, theirs))
    assert not mismatches, mismatches[:5]


def test_interp_is_unfused_on_every_platform():
    """0.6 * 37 + 20: 42.2 unfused; arm64 numpy's FMA gives 42.199999999999996."""
    assert interp(37, [0, 100], [20, 80]) == 42.2
    assert float(np.interp(37, [0, 100], [20, 80])) in (42.2, 42.199999999999996)


def test_interp_returns_float_like_numpy():
    assert type(interp(37, [0, 100], [20, 80])) is float
    assert type(interp(0, [0, 100], [20, 80])) is float
    assert str(interp(50, [0, 100], [20, 80])) == str(np.interp(50, [0, 100], [20, 80]))


@pytest.mark.parametrize(
    ("xp", "fp"),
    [([], []), ([0, 100], [20])],
)
def test_interp_rejects_bad_tables_like_numpy(xp, fp):
    with pytest.raises(ValueError):
        np.interp(1, xp, fp)
    with pytest.raises(ValueError):
        interp(1, xp, fp)


def test_interp_endpoints_and_knots():
    xp, fp = [0, 50, 100], [20, 30, 80]
    for x, expected in itertools.chain(
        [(-1, 20.0), (0, 20.0), (50, 30.0), (100, 80.0), (101, 80.0)],
        [(25, 25.0), (75, 55.0)],
    ):
        assert interp(x, xp, fp) == expected
