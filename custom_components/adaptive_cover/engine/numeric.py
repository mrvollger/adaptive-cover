"""Scalar stand-ins for the two numpy calls the integration used (P2, ADR 0005).

numpy only ever saw single values here, so these helpers reproduce its
scalar results exactly (``tests/engine/test_numeric.py`` checks them
against numpy on dense grids):

- :func:`clip` is ``np.clip`` on one value.
- :func:`interp` is ``np.interp`` on one x.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import overload


@overload
def clip(value: int, lower: int, upper: int | None) -> int: ...


@overload
def clip(value: float, lower: float, upper: float | None) -> float: ...


def clip(value: float, lower: float, upper: float | None) -> float:
    """Limit ``value`` to ``[lower, upper]``, like ``np.clip`` on a scalar.

    Parameters
    ----------
    value
        The value to limit.
    lower
        The lower bound. It is applied first, as in numpy, so a ``lower``
        above ``upper`` gives ``upper``.
    upper
        The upper bound, or None for no upper bound.

    Returns
    -------
    float
        The limited value. NaN passes through. As with numpy's type
        promotion, the result is a float when any argument is a float and
        an int when all of them are ints (so "45" prints as "45", not
        "45.0", in decision traces).

    """
    result = lower if value < lower else value
    if upper is not None and result > upper:
        result = upper
    if isinstance(value, float) or isinstance(lower, float) or isinstance(upper, float):
        return float(result)
    return result


def interp(x: float, xp: Sequence[float], fp: Sequence[float]) -> float:
    """Piecewise-linear interpolation of one point, like ``np.interp(x, xp, fp)``.

    Parameters
    ----------
    x
        The point to evaluate.
    xp
        The x-coordinates of the data points. numpy requires them to be
        increasing; the result for other orders is numpy's result too,
        because the search below is numpy's.
    fp
        The y-coordinates, same length as ``xp``.

    Returns
    -------
    float
        ``fp[0]`` left of ``xp[0]``, ``fp[-1]`` right of ``xp[-1]``,
        ``fp[j]`` exactly at a data point, else
        ``slope * (x - xp[j]) + fp[j]``, the same float operations as
        numpy's compiled loop.

    Raises
    ------
    ValueError
        If ``xp`` is empty or ``xp`` and ``fp`` differ in length.

    """
    xs = [float(v) for v in xp]
    ys = [float(v) for v in fp]
    if not xs:
        raise ValueError("array of sample points is empty")
    if len(xs) != len(ys):
        raise ValueError("fp and xp are not of the same length.")
    key = float(x)
    if len(xs) == 1:
        if key < xs[0]:
            return ys[0]
        return ys[-1] if key > xs[0] else ys[0]
    j = _search(key, xs)
    if j == -1:
        return ys[0]
    if j == len(xs):
        return ys[-1]
    if j == len(xs) - 1 or xs[j] == key:
        return ys[j]
    slope = _divide(ys[j + 1] - ys[j], xs[j + 1] - xs[j])
    result = slope * (key - xs[j]) + ys[j]
    if result != result:  # NaN: try from the other end, as numpy does
        result = slope * (key - xs[j + 1]) + ys[j + 1]
        if result != result and ys[j] == ys[j + 1]:
            result = ys[j]
    return result


def _divide(numerator: float, denominator: float) -> float:
    """IEEE division, as in numpy's C loop: x / 0 is +-inf or NaN, not an error.

    Only reachable with unsorted sample points (a repeated knot is never
    interpolated across when ``xp`` is increasing).
    """
    if denominator != 0:
        return numerator / denominator
    if numerator != numerator or numerator == 0:
        return math.nan
    return math.copysign(math.inf, numerator) * math.copysign(1.0, denominator)


def _search(key: float, arr: list[float]) -> int:
    """Return j with ``arr[j] <= key < arr[j + 1]``, as numpy finds it.

    A port of ``binary_search_with_guess`` in numpy's ``compiled_base.c``
    for the one call ``np.interp`` makes per x (guess 0, which numpy
    raises to 1). The comparisons are numpy's, in numpy's order, so
    unsorted ``arr`` and NaN give numpy's answer too. Returns -1 left of
    the range and ``len(arr)`` right of it.
    """
    length = len(arr)
    if key > arr[-1]:
        return length
    if key < arr[0]:
        return -1
    if length <= 4:  # numpy scans short arrays linearly
        i = 1
        while i < length and key >= arr[i]:
            i += 1
        return i - 1
    # Neighbours of the guess (1) first; key < arr[0] was handled above.
    if key < arr[1]:
        return 0
    if key < arr[2]:
        return 1
    if key < arr[3]:
        return 2
    imin, imax = 3, length
    if length > 10 and key < arr[9]:  # numpy's LIKELY_IN_CACHE_SIZE window
        imax = 9
    while imin < imax:
        imid = imin + ((imax - imin) >> 1)
        if key >= arr[imid]:
            imin = imid + 1
        else:
            imax = imid
    return imin - 1
